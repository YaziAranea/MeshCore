#include "ConfigSerializer.h"

bool ConfigSerializer::saveSerial(Stream& s) {
  Context context(&s, OP::WRITE);
  _context = &context;  // set the context for structure() call
  context.putText("{");   // root object
  _first = true;
  structure();
  context.putText("}");
  _context = NULL;
  return context.success;
}

#define TOK_ERROR     -1
#define TOK_EOF        0
#define TOK_KEY        1
#define TOK_VALUE      2
#define TOK_START_OBJ  3
#define TOK_END_OBJ    4
#define TOK_WHITESPACE 5

static bool is_whitespace(char c) {
  return c == ' ' || c == '\t' || c == '\r' || c == '\n';
}
static bool is_key_char(char c) {
  // saveSerial() already emits stable settings such as tone_8bit and
  // favorite_1.  Rejecting digits here made a freshly written prefs.json
  // fail on the next boot and left every setting after that key unloaded.
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
         (c >= '0' && c <= '9') || c == '_';
}
static bool is_value_char(char c) {
  return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || c == '-' || c == '.';
}

#define EXPECT_OPEN_BRACE   0
#define EXPECT_KEY          1
#define EXPECT_VAL_OR_OBJ   2
#define EXPECT_STRING_VAL   3
#define EXPECT_STRING_ESCAPE   4
#define EXPECT_COMMA_OR_CLOSE  5
#define EXPECT_COMMA_OR_KEY    6
#define EXPECT_COMMA_OR_KEY_OR_CLOSE  7

int ConfigSerializer::Context::readNext() {
  char c;
  if (pending) {
    c = pending;
    pending = 0;
  } else {
    if (_f->available() == 0) return TOK_EOF;

    int n = _f->read();
    if (n < 0) return TOK_EOF;
    c = (char)n;
  }

  switch (rd_mode) {
    case EXPECT_OPEN_BRACE:
      if (c == '{') { rd_mode = EXPECT_KEY; return TOK_START_OBJ; }
      if (is_whitespace(c)) return TOK_WHITESPACE;
      return TOK_ERROR;

    case EXPECT_COMMA_OR_KEY_OR_CLOSE:
      if (c == '}') { rd_mode = EXPECT_COMMA_OR_KEY_OR_CLOSE; return TOK_END_OBJ; }
    case EXPECT_COMMA_OR_KEY:
      if (c == ',') { rd_mode = EXPECT_KEY; return TOK_WHITESPACE; }
    case EXPECT_KEY:
      if (rd_len > 0 && c == ':') { rd_buf[rd_len] = 0; rd_len = 0; rd_mode = EXPECT_VAL_OR_OBJ; return TOK_KEY; }
      if (rd_len == 0 && is_whitespace(c)) return TOK_WHITESPACE;
      if (rd_len < CONFIG_MAX_KEYLEN-1 && is_key_char(c)) { rd_buf[rd_len++] = c; return TOK_WHITESPACE; }
      return TOK_ERROR;

    case EXPECT_VAL_OR_OBJ:
      if (rd_len == 0 && is_whitespace(c)) return TOK_WHITESPACE;
      if (rd_len == 0 && c == '"') { rd_mode = EXPECT_STRING_VAL; return TOK_WHITESPACE; }
      if (rd_len == 0 && c == '{') { rd_mode = EXPECT_KEY; return TOK_START_OBJ; }
      if (is_value_char(c) && rd_len < CONFIG_MAX_TOKEN_LEN-1) { rd_buf[rd_len++] = c; return TOK_WHITESPACE; }
      if (rd_len > 0 && (c == ',' || c == '}' || is_whitespace(c))) { pending = c; rd_buf[rd_len] = 0; rd_len = 0; rd_mode = EXPECT_COMMA_OR_CLOSE; return TOK_VALUE;  }
      return TOK_ERROR;

    case EXPECT_STRING_ESCAPE:
      if ((c == 'n') && rd_len < CONFIG_MAX_TOKEN_LEN-1) { rd_buf[rd_len++] = '\n'; rd_mode = EXPECT_STRING_VAL; return TOK_WHITESPACE; }
      if ((c == 'r') && rd_len < CONFIG_MAX_TOKEN_LEN-1) { rd_buf[rd_len++] = '\r'; rd_mode = EXPECT_STRING_VAL; return TOK_WHITESPACE; }
      if ((c == '"' || c == '\\' || c == '/') && rd_len < CONFIG_MAX_TOKEN_LEN-1) { rd_buf[rd_len++] = c; rd_mode = EXPECT_STRING_VAL; return TOK_WHITESPACE; }
      return TOK_ERROR;  // unsupport escape

    case EXPECT_STRING_VAL:
      if (c == '"') { rd_buf[rd_len] = 0; rd_len = 0; rd_mode = EXPECT_COMMA_OR_CLOSE; return TOK_VALUE; }
      if (c == '\\') { rd_mode = EXPECT_STRING_ESCAPE; return TOK_WHITESPACE; }
      if (rd_len < CONFIG_MAX_TOKEN_LEN-1) { rd_buf[rd_len++] = c; return TOK_WHITESPACE; }
      return TOK_ERROR;

    case EXPECT_COMMA_OR_CLOSE:
      if (c == ',') { rd_mode = EXPECT_KEY; return TOK_WHITESPACE; }
      if (c == '}') { rd_mode = EXPECT_COMMA_OR_KEY_OR_CLOSE; return TOK_END_OBJ; }
      if (is_whitespace(c)) return TOK_WHITESPACE;
      return TOK_ERROR;
  }
  return TOK_ERROR;   // unknown mode
}

bool ConfigSerializer::loadSerial(Stream& s) {
  Context context(&s, OP::READ);
  _context = &context;  // set the context for structure() call
  uint8_t sp = 0;   // object nesting stack pointer
  int next_tok = TOK_EOF;
  bool root_started = false;
  bool root_closed = false;

  // parse the Json file
  while ((next_tok = context.readNext()) > TOK_EOF) {
    if (next_tok == TOK_KEY) {
      if (!root_started || root_closed) {
        context.success = false;
        break;
      }
      context.setKey(sp, context.getToken());
    } else if (next_tok == TOK_VALUE) {
      if (!root_started || root_closed) {
        context.success = false;
        break;
      }
      _depth = 1;  // re-run the structure() hierarchy again (looking for specific key, at specific depth)
      structure();
    } else if (next_tok == TOK_START_OBJ) {
      if (!root_started) {
        if (sp != 0 || root_closed) {
          context.success = false;
          break;
        }
        root_started = true;
      } else if (root_closed || sp == 0) {
        context.success = false;
        break;
      }
      if (sp < CONFIG_MAX_DEPTH - 1) {
        sp++;
      } else {
        //Serial.printf("Error: max nesting reached"); // TODO: debug logging
        context.success = false;
        break;
      }
    } else if (next_tok == TOK_END_OBJ) {
      if (sp > 0) {
        sp--;
        if (sp == 0) {
          root_closed = true;
          break;
        }
      } else {
        //Serial.printf("Error: too many closing '}'"); // TODO: debug logging
        context.success = false;
        break;
      }
    }
  }

  // Once the one root object is closed, only whitespace is legal.  Without
  // this check an empty file, "{}garbage" or an interrupted trailing token
  // could be reported as a valid preferences generation and suppress .bak
  // recovery.
  if (root_closed && context.success) {
    while (s.available() > 0) {
      int value = s.read();
      if (value < 0) break;
      if (!is_whitespace((char)value)) {
        context.success = false;
        break;
      }
    }
  }

  if (!root_started || !root_closed || sp != 0 || next_tok == TOK_ERROR) {
    context.success = false;   // unmatched { }, or other parse error
  }
  _context = NULL;
  return context.success;
}

void ConfigSerializer::writeComma() {
  if (_first) {
    _first = false;
  } else {
    _context->putText(",");  // comma separated properties
  }
}

#include <Utils.h>

void ConfigSerializer::def(const char* key, void* value, size_t len) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":\"");
    static const char HEX_CHARS[] = "0123456789abcdef";
    const uint8_t* bytes = (const uint8_t*)value;
    for (size_t i = 0; i < len; ++i) {
      _context->putChar(HEX_CHARS[bytes[i] >> 4]);
      _context->putChar(HEX_CHARS[bytes[i] & 0x0F]);
    }
    _context->putText("\"");
  } else {
    if (_context->keyMatch(_depth, key)) {
      memset(value, 0, len);
      mesh::Utils::fromHex((uint8_t *)value, len, _context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, char* value, size_t max_len) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":\"");
    char c;
    while ((c = *value++) != 0) {  // TODO: handle UTF-8 encoding
      if (c == '"') {
        _context->putText("\\\"");
      } else if (c == '\\') {
        _context->putText("\\\\");
      } else if (c == '\n') {
        _context->putText("\\n");
      } else if (c == '\r') {
        _context->putText("\\r");
      } else {
        _context->putChar(c);
      }
    }
    _context->putText("\"");
  } else {
    if (_context->keyMatch(_depth, key)) {
      strncpy(value, _context->getToken(), max_len - 1);
      value[max_len - 1] = 0;
    }
  }
}

void ConfigSerializer::def(const char* key, int32_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue(value);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atol(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, uint32_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue(value);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atol(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, int16_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue((int32_t)value, 10);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atol(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, uint16_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue((uint32_t)value, 10);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atoi(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, uint8_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue((uint32_t)value, 10);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atoi(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, int8_t& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putValue((int32_t)value, 10);
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atoi(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, bool& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    _context->putText(value ? "true" : "false");
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = strcmp(_context->getToken(), "true") == 0 || atoi(_context->getToken()) != 0;  // 'true' or a non-zero number
    }
  }  
}

void ConfigSerializer::def(const char* key, double& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    if (value == 0.0) {
      _context->putText("0");  // shorter encoding
    } else {
      _context->putValue(value, 6);  // REVISIT: how many dec places?
    }
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = atof(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, float& value) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":");
    if (value == 0.0f) {
      _context->putText("0");  // shorter encoding
    } else {
      _context->putValue(value, 4);  // REVISIT: how many dec places?
    }
  } else {
    if (_context->keyMatch(_depth, key)) {
      value = (float) atof(_context->getToken());
    }
  }
}

void ConfigSerializer::def(const char* key, ConfigSerializer& sub_obj) {
  if (_context->op() == OP::WRITE) {
    writeComma();
    _context->putText(key);
    _context->putText(":{");
    sub_obj._context = _context;  // inherit the Context
    sub_obj._first = true;
    sub_obj.structure();   // recurse into sub object
    _context->putText("}");
  } else {
    if (_context->keyMatch(_depth, key)) {
      sub_obj._context = _context;  // inherit the Context
      sub_obj._depth = _depth + 1;
      sub_obj.structure();   // recurse into sub object
    }
  }
}
