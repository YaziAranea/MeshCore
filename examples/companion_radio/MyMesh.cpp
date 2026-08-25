#include "MyMesh.h"

#include <Arduino.h> // needed for PlatformIO
#include <Mesh.h>
#include "helpers/radiolib/RXPowerSaving.h"

#define CMD_APP_START                 1
#define CMD_SEND_TXT_MSG              2
#define CMD_SEND_CHANNEL_TXT_MSG      3
#define CMD_GET_CONTACTS              4 // with optional 'since' (for efficient sync)
#define CMD_GET_DEVICE_TIME           5
#define CMD_SET_DEVICE_TIME           6
#define CMD_SEND_SELF_ADVERT          7
#define CMD_SET_ADVERT_NAME           8
#define CMD_ADD_UPDATE_CONTACT        9
#define CMD_SYNC_NEXT_MESSAGE         10
#define CMD_SET_RADIO_PARAMS          11
#define CMD_SET_RADIO_TX_POWER        12
#define CMD_RESET_PATH                13
#define CMD_SET_ADVERT_LATLON         14
#define CMD_REMOVE_CONTACT            15
#define CMD_SHARE_CONTACT             16
#define CMD_EXPORT_CONTACT            17
#define CMD_IMPORT_CONTACT            18
#define CMD_REBOOT                    19
#define CMD_GET_BATT_AND_STORAGE      20   // was CMD_GET_BATTERY_VOLTAGE
#define CMD_SET_TUNING_PARAMS         21
#define CMD_DEVICE_QUERY              22
#define CMD_EXPORT_PRIVATE_KEY        23
#define CMD_IMPORT_PRIVATE_KEY        24
#define CMD_SEND_RAW_DATA             25
#define CMD_SEND_LOGIN                26
#define CMD_SEND_STATUS_REQ           27
#define CMD_HAS_CONNECTION            28
#define CMD_LOGOUT                    29 // 'Disconnect'
#define CMD_GET_CONTACT_BY_KEY        30
#define CMD_GET_CHANNEL               31
#define CMD_SET_CHANNEL               32
#define CMD_SIGN_START                33
#define CMD_SIGN_DATA                 34
#define CMD_SIGN_FINISH               35
#define CMD_SEND_TRACE_PATH           36
#define CMD_SET_DEVICE_PIN            37
#define CMD_SET_OTHER_PARAMS          38
#define CMD_SEND_TELEMETRY_REQ        39  // can deprecate this
#define CMD_GET_CUSTOM_VARS           40
#define CMD_SET_CUSTOM_VAR            41
#define CMD_GET_ADVERT_PATH           42
#define CMD_GET_TUNING_PARAMS         43
#define CMD_SET_PHONE_GPS             44   // reserved compatibility command; disabled in public SmartUI builds
// NOTE: CMD range 45..49 parked, potentially for WiFi operations
#define CMD_SEND_BINARY_REQ           50
#define CMD_FACTORY_RESET             51
#define CMD_SEND_PATH_DISCOVERY_REQ   52
#define CMD_SET_FLOOD_SCOPE_KEY       54   // v8+
#define CMD_SEND_CONTROL_DATA         55   // v8+
#define CMD_GET_STATS                 56   // v8+, second byte is stats type
#define CMD_SEND_ANON_REQ             57
#define CMD_SET_AUTOADD_CONFIG        58
#define CMD_GET_AUTOADD_CONFIG        59
#define CMD_GET_ALLOWED_REPEAT_FREQ   60
#define CMD_SET_PATH_HASH_MODE        61
#define CMD_SEND_CHANNEL_DATA         62
#define CMD_SET_DEFAULT_FLOOD_SCOPE   63
#define CMD_GET_DEFAULT_FLOOD_SCOPE   64
#define CMD_SEND_RAW_PACKET           65

// Stats sub-types for CMD_GET_STATS
#define STATS_TYPE_CORE               0
#define STATS_TYPE_RADIO              1
#define STATS_TYPE_PACKETS             2

#ifndef BOARD_LEDS_DEFAULT
#define BOARD_LEDS_DEFAULT 1
#endif

#ifndef DISABLE_LOW_BATTERY_SHUTDOWN
#define DISABLE_LOW_BATTERY_SHUTDOWN 0
#endif

#ifndef LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED
#define LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED (!DISABLE_LOW_BATTERY_SHUTDOWN)
#endif

#ifndef DEFAULT_NOTIFY_MODE
  #ifdef PIN_MSG_ALERT
    #define DEFAULT_NOTIFY_MODE NOTIFY_MODE_GPIO
  #else
    #define DEFAULT_NOTIFY_MODE NOTIFY_MODE_SILENT
  #endif
#endif

#ifndef DEFAULT_NOTIFY_GPIO_PIN
  #ifdef PIN_MSG_ALERT
    #define DEFAULT_NOTIFY_GPIO_PIN PIN_MSG_ALERT
  #else
    #define DEFAULT_NOTIFY_GPIO_PIN (-1)
  #endif
#endif

#ifndef UI_TONE_FALLBACK_TO_ALERT
#define UI_TONE_FALLBACK_TO_ALERT 1
#endif

#ifndef DEFAULT_NOTIFY_TONE_PIN
  #ifdef PIN_BUZZER
    #define DEFAULT_NOTIFY_TONE_PIN PIN_BUZZER
  #elif defined(PIN_MSG_TONE)
    #define DEFAULT_NOTIFY_TONE_PIN PIN_MSG_TONE
  #elif defined(PIN_MSG_ALERT) && UI_TONE_FALLBACK_TO_ALERT
    #define DEFAULT_NOTIFY_TONE_PIN PIN_MSG_ALERT
  #else
    #define DEFAULT_NOTIFY_TONE_PIN (-1)
  #endif
#endif

#ifndef DEFAULT_NOTIFY_VIBE_PIN
  #ifdef PIN_VIBRATION
    #define DEFAULT_NOTIFY_VIBE_PIN PIN_VIBRATION
  #else
    #define DEFAULT_NOTIFY_VIBE_PIN (-1)
  #endif
#endif

#ifndef DEFAULT_NOTIFY_TONE_ID
#define DEFAULT_NOTIFY_TONE_ID 0
#endif

#ifndef DEFAULT_NOTIFY_TONE_VOLUME
#define DEFAULT_NOTIFY_TONE_VOLUME 10
#endif

#ifndef DEFAULT_IMPORTANT_NOTIFY_MODE
  #ifdef PIN_MSG_ALERT
    #define DEFAULT_IMPORTANT_NOTIFY_MODE NOTIFY_MODE_ALL
  #elif defined(PIN_BUZZER) || defined(PIN_MSG_TONE)
    #define DEFAULT_IMPORTANT_NOTIFY_MODE NOTIFY_MODE_TONE
  #else
    #define DEFAULT_IMPORTANT_NOTIFY_MODE NOTIFY_MODE_SILENT
  #endif
#endif

#ifndef BLE_TIME_SYNC_ACCEPT_BACKWARD
  #define BLE_TIME_SYNC_ACCEPT_BACKWARD 0
#endif

#ifndef BLE_TIME_SYNC_MIN_UNIX
  #define BLE_TIME_SYNC_MIN_UNIX 1704067200UL
#endif

#ifndef BLE_TIME_SYNC_MAX_UNIX
  #define BLE_TIME_SYNC_MAX_UNIX 2208988800UL
#endif

#ifndef DEFAULT_NOTIFY_REPAIR_LEGACY
  #define DEFAULT_NOTIFY_REPAIR_LEGACY 0
#endif

#ifndef UI_MENTION_SHORT_NAME_AT_ONLY_CHARS
#define UI_MENTION_SHORT_NAME_AT_ONLY_CHARS 3
#endif

#ifndef UI_MENTION_REQUIRE_AT
#define UI_MENTION_REQUIRE_AT 0
#endif

#ifndef UI_MENTION_ALLOW_PLAIN_NODE_NAME
#define UI_MENTION_ALLOW_PLAIN_NODE_NAME 0
#endif

#ifndef UI_MENTION_ALLOW_PLAIN_FIRST_TOKEN
#define UI_MENTION_ALLOW_PLAIN_FIRST_TOKEN 1
#endif

#ifndef UI_MENTION_PLAIN_FIRST_TOKEN_MIN_CHARS
#define UI_MENTION_PLAIN_FIRST_TOKEN_MIN_CHARS 3
#endif

#ifndef UI_NOTIFY_ONLY_IMPORTANT_MESSAGES
#define UI_NOTIFY_ONLY_IMPORTANT_MESSAGES 0
#endif

static bool isValidAutoAdvertIntervalMins(uint16_t mins) {
  switch (mins) {
    case 0:
    case 15:
    case 30:
    case 60:
    case 120:
    case 180:
      return true;
    default:
      return false;
  }
}

static uint16_t nextAutoAdvertIntervalMins(uint16_t mins) {
  switch (mins) {
    case 0: return 15;
    case 15: return 30;
    case 30: return 60;
    case 60: return 120;
    case 120: return 180;
    default: return 0;
  }
}

static bool isUtf8Continuation(uint8_t c) {
  return (c & 0xC0) == 0x80;
}

static const char* readUtf8Codepoint(const char* p, uint32_t& cp) {
  const uint8_t* s = (const uint8_t*)p;
  uint8_t b0 = s[0];
  if (b0 == 0 || b0 < 0x80) {
    cp = b0;
    return p + (b0 ? 1 : 0);
  }
  if ((b0 & 0xE0) == 0xC0 && isUtf8Continuation(s[1])) {
    cp = ((uint32_t)(b0 & 0x1F) << 6) | (s[1] & 0x3F);
    return p + 2;
  }
  if ((b0 & 0xF0) == 0xE0 && isUtf8Continuation(s[1]) && isUtf8Continuation(s[2])) {
    cp = ((uint32_t)(b0 & 0x0F) << 12) | ((uint32_t)(s[1] & 0x3F) << 6) | (s[2] & 0x3F);
    return p + 3;
  }
  if ((b0 & 0xF8) == 0xF0 && isUtf8Continuation(s[1]) &&
      isUtf8Continuation(s[2]) && isUtf8Continuation(s[3])) {
    cp = ((uint32_t)(b0 & 0x07) << 18) | ((uint32_t)(s[1] & 0x3F) << 12) |
         ((uint32_t)(s[2] & 0x3F) << 6) | (s[3] & 0x3F);
    return p + 4;
  }
  cp = b0;
  return p + 1;
}

static uint32_t mentionLowerCodepoint(uint32_t cp) {
  if (cp >= 'A' && cp <= 'Z') return cp + ('a' - 'A');
  if (cp >= 0x0410 && cp <= 0x042F) return cp + 0x20;
  if (cp == 0x0401) return 0x0451;
  if (cp == 0x0404) return 0x0454;
  if (cp == 0x0406) return 0x0456;
  if (cp == 0x0407) return 0x0457;
  if (cp == 0x0490) return 0x0491;
  return cp;
}

static bool mentionWordCodepoint(uint32_t cp) {
  if (cp >= '0' && cp <= '9') return true;
  if (cp >= 'A' && cp <= 'Z') return true;
  if (cp >= 'a' && cp <= 'z') return true;
  if (cp == '_' || cp == '-') return true;
  if (cp >= 0x0410 && cp <= 0x044F) return true;
  return cp == 0x0401 || cp == 0x0451 || cp == 0x0404 || cp == 0x0454 ||
         cp == 0x0406 || cp == 0x0456 || cp == 0x0407 || cp == 0x0457 ||
         cp == 0x0490 || cp == 0x0491;
}

static bool mentionNameTokenCodepoint(uint32_t cp) {
  return mentionWordCodepoint(cp) && cp != '_' && cp != '-';
}

static size_t utf8CodepointCount(const char* s) {
  size_t count = 0;
  while (s && *s) {
    uint32_t cp;
    s = readUtf8Codepoint(s, cp);
    count++;
  }
  return count;
}

static size_t utf8NameFirstTokenCodepointCount(const char* node_name) {
  size_t count = 0;
  for (const char* n = node_name; n && *n;) {
    uint32_t cp;
    const char* next = readUtf8Codepoint(n, cp);
    if (!mentionNameTokenCodepoint(cp)) break;
    count++;
    n = next;
  }
  return count;
}

static bool utf8NameMatchesAt(const char* text, const char* node_name, const char** after_text) {
  const char* t = text;
  const char* n = node_name;
  while (*n) {
    if (!*t) return false;
    uint32_t tc, nc;
    t = readUtf8Codepoint(t, tc);
    n = readUtf8Codepoint(n, nc);
    if (mentionLowerCodepoint(tc) != mentionLowerCodepoint(nc)) return false;
  }
  if (after_text) *after_text = t;
  return true;
}

static bool utf8NameFirstTokenMatchesAt(const char* text, const char* node_name,
                                        const char** after_text) {
  const char* t = text;
  const char* n = node_name;
  size_t matched = 0;
  while (*n) {
    uint32_t nc;
    const char* next_n = readUtf8Codepoint(n, nc);
    if (!mentionNameTokenCodepoint(nc)) break;
    if (!*t) return false;
    uint32_t tc;
    t = readUtf8Codepoint(t, tc);
    if (mentionLowerCodepoint(tc) != mentionLowerCodepoint(nc)) return false;
    n = next_n;
    matched++;
  }
  if (matched < 2) return false;
  if (after_text) *after_text = t;
  return true;
}

static const char* channelMentionBodyText(const char* text) {
  const char* sep = text ? strstr(text, ": ") : NULL;
  return (sep && sep > text) ? sep + 2 : text;
}

static bool mentionMatchEndsAtBoundary(const char* after) {
  uint32_t after_cp = 0;
  if (after && *after) readUtf8Codepoint(after, after_cp);
  return !mentionWordCodepoint(after_cp);
}

static uint16_t mentionMatchRankAt(const char* text, const char* node_name, bool allow_first_token) {
  if (!text || !node_name || !*node_name) return 0;
  uint16_t best_rank = 0;
  const char* after = NULL;
  size_t name_chars = utf8CodepointCount(node_name);
  if (name_chars >= 2 && utf8NameMatchesAt(text, node_name, &after) &&
      mentionMatchEndsAtBoundary(after)) {
    best_rank = (uint16_t)(name_chars * 2 + 1);
  }
  size_t first_token_chars = utf8NameFirstTokenCodepointCount(node_name);
  if (allow_first_token && first_token_chars >= 2 &&
      utf8NameFirstTokenMatchesAt(text, node_name, &after) && mentionMatchEndsAtBoundary(after)) {
    uint16_t rank = (uint16_t)(first_token_chars * 2);
    if (rank > best_rank) best_rank = rank;
  }
  return best_rank;
}

static bool mentionCandidateBelongsToNode(MyMesh* mesh, const char* text, const char* node_name,
                                          bool allow_first_token) {
  uint16_t own_rank = mentionMatchRankAt(text, node_name, allow_first_token);
  if (own_rank == 0) return false;
  ContactsIterator contacts = mesh->startContactsIterator();
  ContactInfo contact;
  while (contacts.hasNext(mesh, contact)) {
    if (!contact.name[0]) continue;
    if (mentionMatchRankAt(text, contact.name, allow_first_token) > own_rank) return false;
  }
  NetworkStatusEntry recent[NETWORK_STATUS_TABLE_SIZE];
  int recent_count = mesh->getRecentNetworkStatus(recent, NETWORK_STATUS_TABLE_SIZE, 0xFFFFFFFFUL);
  for (int i = 0; i < recent_count; i++) {
    if (recent[i].type != ADV_TYPE_REPEATER && recent[i].type != ADV_TYPE_CHAT) continue;
    if (mentionMatchRankAt(text, recent[i].name, allow_first_token) > own_rank) return false;
  }
  return true;
}

static bool textMentionsNodeName(MyMesh* mesh, const char* text, const char* node_name) {
  if (!text || !node_name || !*node_name) return false;
  size_t name_chars = utf8CodepointCount(node_name);
  if (name_chars < 2) return false;
  size_t first_token_chars = utf8NameFirstTokenCodepointCount(node_name);
  bool at_only = UI_MENTION_REQUIRE_AT || name_chars <= UI_MENTION_SHORT_NAME_AT_ONLY_CHARS;
  bool plain_full_allowed = !at_only || UI_MENTION_ALLOW_PLAIN_NODE_NAME;
  bool plain_first_allowed = UI_MENTION_ALLOW_PLAIN_FIRST_TOKEN &&
                             first_token_chars >= UI_MENTION_PLAIN_FIRST_TOKEN_MIN_CHARS;
  bool prev_boundary = true;
  for (const char* p = text; *p;) {
    uint32_t cp;
    const char* next = readUtf8Codepoint(p, cp);
    if (cp == '@' && mentionCandidateBelongsToNode(mesh, next, node_name, true)) return true;
    if (prev_boundary) {
      if (plain_full_allowed && mentionCandidateBelongsToNode(mesh, p, node_name, false)) return true;
      if (plain_first_allowed && mentionCandidateBelongsToNode(mesh, p, node_name, true)) return true;
    }
    prev_boundary = !mentionWordCodepoint(cp);
    p = next;
  }
  return false;
}

#ifndef UI_FONT_PREF_MAX
  #if defined(UI_T096_PREMIUM_TFT)
    #define UI_FONT_PREF_MAX 19
  #elif (defined(HELTEC_T114_WITH_DISPLAY) && defined(ST7789)) || defined(HELTEC_LORA_V4_TFT)
    #define UI_FONT_PREF_MAX 14
  #else
    #define UI_FONT_PREF_MAX 5
  #endif
#endif

#define RESP_CODE_OK                  0
#define RESP_CODE_ERR                 1
#define RESP_CODE_CONTACTS_START      2  // first reply to CMD_GET_CONTACTS
#define RESP_CODE_CONTACT             3  // multiple of these (after CMD_GET_CONTACTS)
#define RESP_CODE_END_OF_CONTACTS     4  // last reply to CMD_GET_CONTACTS
#define RESP_CODE_SELF_INFO           5  // reply to CMD_APP_START
#define RESP_CODE_SENT                6  // reply to CMD_SEND_TXT_MSG
#define RESP_CODE_CONTACT_MSG_RECV    7  // a reply to CMD_SYNC_NEXT_MESSAGE (ver < 3)
#define RESP_CODE_CHANNEL_MSG_RECV    8  // a reply to CMD_SYNC_NEXT_MESSAGE (ver < 3)
#define RESP_CODE_CURR_TIME           9  // a reply to CMD_GET_DEVICE_TIME
#define RESP_CODE_NO_MORE_MESSAGES    10 // a reply to CMD_SYNC_NEXT_MESSAGE
#define RESP_CODE_EXPORT_CONTACT      11
#define RESP_CODE_BATT_AND_STORAGE    12 // a reply to a CMD_GET_BATT_AND_STORAGE
#define RESP_CODE_DEVICE_INFO         13 // a reply to CMD_DEVICE_QUERY
#define RESP_CODE_PRIVATE_KEY         14 // a reply to CMD_EXPORT_PRIVATE_KEY
#define RESP_CODE_DISABLED            15
#define RESP_CODE_CONTACT_MSG_RECV_V3 16 // a reply to CMD_SYNC_NEXT_MESSAGE (ver >= 3)
#define RESP_CODE_CHANNEL_MSG_RECV_V3 17 // a reply to CMD_SYNC_NEXT_MESSAGE (ver >= 3)
#define RESP_CODE_CHANNEL_INFO        18 // a reply to CMD_GET_CHANNEL
#define RESP_CODE_SIGN_START          19
#define RESP_CODE_SIGNATURE           20
#define RESP_CODE_CUSTOM_VARS         21
#define RESP_CODE_ADVERT_PATH         22
#define RESP_CODE_TUNING_PARAMS       23
#define RESP_CODE_STATS               24   // v8+, second byte is stats type
#define RESP_CODE_AUTOADD_CONFIG      25
#define RESP_ALLOWED_REPEAT_FREQ      26
#define RESP_CODE_CHANNEL_DATA_RECV   27
#define RESP_CODE_DEFAULT_FLOOD_SCOPE 28

#define MAX_CHANNEL_DATA_LENGTH       (MAX_FRAME_SIZE - 9)

#define SEND_TIMEOUT_BASE_MILLIS        500
#define FLOOD_SEND_TIMEOUT_FACTOR       16.0f
#define DIRECT_SEND_PERHOP_FACTOR       6.0f
#define DIRECT_SEND_PERHOP_EXTRA_MILLIS 250
#define LAZY_CONTACTS_WRITE_DELAY       5000

#define PUBLIC_GROUP_PSK                "izOH6cXN6mrJ5e26oRXNcg=="

// these are _pushed_ to client app at any time
#define PUSH_CODE_ADVERT                0x80
#define PUSH_CODE_PATH_UPDATED          0x81
#define PUSH_CODE_SEND_CONFIRMED        0x82
#define PUSH_CODE_MSG_WAITING           0x83
#define PUSH_CODE_RAW_DATA              0x84
#define PUSH_CODE_LOGIN_SUCCESS         0x85
#define PUSH_CODE_LOGIN_FAIL            0x86
#define PUSH_CODE_STATUS_RESPONSE       0x87
#define PUSH_CODE_LOG_RX_DATA           0x88
#define PUSH_CODE_TRACE_DATA            0x89
#define PUSH_CODE_NEW_ADVERT            0x8A
#define PUSH_CODE_TELEMETRY_RESPONSE    0x8B
#define PUSH_CODE_BINARY_RESPONSE       0x8C
#define PUSH_CODE_PATH_DISCOVERY_RESPONSE 0x8D
#define PUSH_CODE_CONTROL_DATA          0x8E   // v8+
#define PUSH_CODE_CONTACT_DELETED       0x8F // used to notify client app of deleted contact when overwriting oldest
#define PUSH_CODE_CONTACTS_FULL         0x90 // used to notify client app that contacts storage is full

#define ERR_CODE_UNSUPPORTED_CMD        1
#define ERR_CODE_NOT_FOUND              2
#define ERR_CODE_TABLE_FULL             3
#define ERR_CODE_BAD_STATE              4
#define ERR_CODE_FILE_IO_ERROR          5
#define ERR_CODE_ILLEGAL_ARG            6

#define MAX_SIGN_DATA_LEN               (8 * 1024) // 8K

// Auto-add config bitmask
// Bit 0: If set, overwrite oldest non-favourite contact when contacts file is full
// Bits 1-4: these indicate which contact types to auto-add when manual_contact_mode = 0x01
#define AUTO_ADD_OVERWRITE_OLDEST (1 << 0)  // 0x01 - overwrite oldest non-favourite when full
#define AUTO_ADD_CHAT             (1 << 1)  // 0x02 - auto-add Chat (Companion) (ADV_TYPE_CHAT)
#define AUTO_ADD_REPEATER         (1 << 2)  // 0x04 - auto-add Repeater (ADV_TYPE_REPEATER)
#define AUTO_ADD_ROOM_SERVER      (1 << 3)  // 0x08 - auto-add Room Server (ADV_TYPE_ROOM)
#define AUTO_ADD_SENSOR           (1 << 4)  // 0x10 - auto-add Sensor (ADV_TYPE_SENSOR)

void MyMesh::writeOKFrame() {
  uint8_t buf[1];
  buf[0] = RESP_CODE_OK;
  _serial->writeFrame(buf, 1);
}
void MyMesh::writeErrFrame(uint8_t err_code) {
  uint8_t buf[2];
  buf[0] = RESP_CODE_ERR;
  buf[1] = err_code;
  _serial->writeFrame(buf, 2);
}

void MyMesh::writeDisabledFrame() {
  uint8_t buf[1];
  buf[0] = RESP_CODE_DISABLED;
  _serial->writeFrame(buf, 1);
}

void MyMesh::writeContactRespFrame(uint8_t code, const ContactInfo &contact) {
  int i = 0;
  out_frame[i++] = code;
  memcpy(&out_frame[i], contact.id.pub_key, PUB_KEY_SIZE);
  i += PUB_KEY_SIZE;
  out_frame[i++] = contact.type;
  out_frame[i++] = contact.flags;
  out_frame[i++] = contact.out_path_len;
  memcpy(&out_frame[i], contact.out_path, MAX_PATH_SIZE);
  i += MAX_PATH_SIZE;
  StrHelper::strzcpy((char *)&out_frame[i], contact.name, 32);
  i += 32;
  memcpy(&out_frame[i], &contact.last_advert_timestamp, 4);
  i += 4;
  memcpy(&out_frame[i], &contact.gps_lat, 4);
  i += 4;
  memcpy(&out_frame[i], &contact.gps_lon, 4);
  i += 4;
  memcpy(&out_frame[i], &contact.lastmod, 4);
  i += 4;
  _serial->writeFrame(out_frame, i);
}

void MyMesh::updateContactFromFrame(ContactInfo &contact, uint32_t& last_mod, const uint8_t *frame, int len) {
  int i = 0;
  uint8_t code = frame[i++]; // eg. CMD_ADD_UPDATE_CONTACT
  memcpy(contact.id.pub_key, &frame[i], PUB_KEY_SIZE);
  i += PUB_KEY_SIZE;
  contact.type = frame[i++];
  contact.flags = frame[i++];
  contact.out_path_len = frame[i++];
  memcpy(contact.out_path, &frame[i], MAX_PATH_SIZE);
  i += MAX_PATH_SIZE;
  memcpy(contact.name, &frame[i], 32);
  i += 32;
  memcpy(&contact.last_advert_timestamp, &frame[i], 4);
  i += 4;
  if (len >= i + 8) { // optional fields
    memcpy(&contact.gps_lat, &frame[i], 4);
    i += 4;
    memcpy(&contact.gps_lon, &frame[i], 4);
    i += 4;
    if (len >= i + 4) {
      memcpy(&last_mod, &frame[i], 4);
    }
  }
}

bool MyMesh::Frame::isChannelMsg() const {
  return buf[0] == RESP_CODE_CHANNEL_MSG_RECV || buf[0] == RESP_CODE_CHANNEL_MSG_RECV_V3 ||
         buf[0] == RESP_CODE_CHANNEL_DATA_RECV;
}

bool MyMesh::Frame::isDisplayableDirectMsg() const {
  int txt_type_index;
  if (buf[0] == RESP_CODE_CONTACT_MSG_RECV_V3) {
    txt_type_index = 11;
  } else if (buf[0] == RESP_CODE_CONTACT_MSG_RECV) {
    txt_type_index = 8;
  } else {
    return false;
  }
  if (len <= txt_type_index) return false;
  return buf[txt_type_index] == TXT_TYPE_PLAIN ||
         buf[txt_type_index] == TXT_TYPE_SIGNED_PLAIN;
}

void MyMesh::addToOfflineQueue(const uint8_t frame[], int len) {
  if (offline_queue_len >= OFFLINE_QUEUE_SIZE) {
    MESH_DEBUG_PRINTLN("WARN: offline_queue is full!");
    int pos = 0;
    while (pos < offline_queue_len) {
      if (offline_queue[pos].isChannelMsg()) {
        for (int i = pos; i < offline_queue_len - 1; i++) { // delete oldest channel msg from queue
          offline_queue[i] = offline_queue[i + 1];
        }
        MESH_DEBUG_PRINTLN("INFO: removed oldest channel message from queue.");
        offline_queue[offline_queue_len - 1].len = len;
        memcpy(offline_queue[offline_queue_len - 1].buf, frame, len);
        return;
      }
      pos++;
    }
    MESH_DEBUG_PRINTLN("INFO: no channel messages to remove from queue.");
  } else {
    offline_queue[offline_queue_len].len = len;
    memcpy(offline_queue[offline_queue_len].buf, frame, len);
    offline_queue_len++;
  }
}

int MyMesh::getFromOfflineQueue(uint8_t frame[]) {
  if (offline_queue_len > 0) {         // check offline queue
    size_t len = offline_queue[0].len; // take from top of queue
    memcpy(frame, offline_queue[0].buf, len);

    offline_queue_len--;
    for (int i = 0; i < offline_queue_len; i++) { // delete top item from queue
      offline_queue[i] = offline_queue[i + 1];
    }
    return len;
  }
  return 0; // queue is empty
}

float MyMesh::getAirtimeBudgetFactor() const {
  return _prefs.airtime_factor;
}

int MyMesh::getInterferenceThreshold() const {
  return 0; // disabled for now, until currentRSSI() problem is resolved
}
bool MyMesh::getCADEnabled() const {
  return false; // hardware CAD before TX (disabled by default, until configurable)
}

static void applyCompanionRxPowerSaving(uint8_t sf, float bw) {
#ifdef WRAPPER_CLASS
  RxPowerSavingControl* control = &radio_driver;

  // setRxPowerSaving() rejects out-of-range periods without touching the
  // wrapper's state, so on any failure we must explicitly stand the duty cycle
  // down. Otherwise it would stay armed with the *previous* SF/BW timings -
  // e.g. SF5/BW500 yields rx=655us (below the 1ms minimum), and the radio would
  // keep sleeping in windows sized for SF11, missing every preamble.
  uint32_t rx_us = 0;
  uint32_t sleep_us = 0;
  bool ok = calcRxPowerSavingLevel(RX_POWERSAVING_BALANCED_LEVEL, sf, bw,
                                   RX_POWERSAVING_PROFILE_PREAMBLE, &rx_us, &sleep_us) &&
            control->setRxPowerSaving(true, rx_us, sleep_us);
  if (!ok) {
    control->setRxPowerSaving(false, RX_POWERSAVING_DEFAULT_RX_US,
                              RX_POWERSAVING_DEFAULT_SLEEP_US);
  }
  MESH_DEBUG_PRINTLN("RX Power Saving: companion level=5,preamble=16,rx=%lu,sleep=%lu,%s",
                     (unsigned long)rx_us, (unsigned long)sleep_us,
                     ok ? "accepted" : "unavailable - continuous RX");
#else
  (void)sf;
  (void)bw;
#endif
}

int MyMesh::calcRxDelay(float score, uint32_t air_time) const {
  if (_prefs.rx_delay_base <= 0.0f) return 0;
  return (int)((pow(_prefs.rx_delay_base, 0.85f - score) - 1.0) * air_time);
}

uint32_t MyMesh::getRetransmitDelay(const mesh::Packet *packet) {
  uint32_t t = (_radio->getEstAirtimeFor(packet->getPathByteLen() + packet->payload_len + 2) * 0.5f);
  return getRNG()->nextInt(0, 5*t + 1);
}
uint32_t MyMesh::getDirectRetransmitDelay(const mesh::Packet *packet) {
  uint32_t t = (_radio->getEstAirtimeFor(packet->getPathByteLen() + packet->payload_len + 2) * 0.2f);
  return getRNG()->nextInt(0, 5*t + 1);
}

uint8_t MyMesh::getExtraAckTransmitCount() const {
  return _prefs.multi_acks;
}

void MyMesh::logRxRaw(float snr, float rssi, const uint8_t raw[], int len) {
  int snr_q4 = (int)(snr * 4.0f);
  if (snr_q4 < -128) snr_q4 = -128;
  if (snr_q4 > 127) snr_q4 = 127;
  int rssi_i = (int)rssi;
  if (rssi_i < -128) rssi_i = -128;
  if (rssi_i > 127) rssi_i = 127;
  last_rx_snr_q4 = (int8_t)snr_q4;
  last_rx_rssi = (int8_t)rssi_i;
  last_rx_millis = millis();

  if (_serial->isConnected() && len + 3 <= MAX_FRAME_SIZE) {
    int i = 0;
    out_frame[i++] = PUSH_CODE_LOG_RX_DATA;
    out_frame[i++] = last_rx_snr_q4;
    out_frame[i++] = last_rx_rssi;
    memcpy(&out_frame[i], raw, len);
    i += len;

    _serial->writeFrame(out_frame, i);
  }
}

bool MyMesh::isAutoAddEnabled() const {
  return (_prefs.manual_add_contacts & 1) == 0;
}

bool MyMesh::shouldAutoAddContactType(uint8_t contact_type) const {
  if ((_prefs.manual_add_contacts & 1) == 0) {
    return true;
  }

  uint8_t type_bit = 0;
  switch (contact_type) {
    case ADV_TYPE_CHAT:
      type_bit = AUTO_ADD_CHAT;
      break;
    case ADV_TYPE_REPEATER:
      type_bit = AUTO_ADD_REPEATER;
      break;
    case ADV_TYPE_ROOM:
      type_bit = AUTO_ADD_ROOM_SERVER;
      break;
    case ADV_TYPE_SENSOR:
      type_bit = AUTO_ADD_SENSOR;
      break;
    default:
      return false;  // Unknown type, don't auto-add
  }

  return (_prefs.autoadd_config & type_bit) != 0;
}

bool MyMesh::shouldOverwriteWhenFull() const {
  return (_prefs.autoadd_config & AUTO_ADD_OVERWRITE_OLDEST) != 0;
}

uint8_t MyMesh::getAutoAddMaxHops() const {
  return _prefs.autoadd_max_hops;
}

void MyMesh::onContactOverwrite(const uint8_t* pub_key) {
    _store->deleteBlobByKey(pub_key, PUB_KEY_SIZE); // delete from storage
  if (_serial->isConnected()) {
    out_frame[0] = PUSH_CODE_CONTACT_DELETED;
    memcpy(&out_frame[1], pub_key, PUB_KEY_SIZE);
    _serial->writeFrame(out_frame, 1 + PUB_KEY_SIZE);
  }
}

void MyMesh::onContactsFull() {
  if (_serial->isConnected()) {
    out_frame[0] = PUSH_CODE_CONTACTS_FULL;
    _serial->writeFrame(out_frame, 1);
  }
}

void MyMesh::onDiscoveredContact(ContactInfo &contact, bool is_new, uint8_t path_len, const uint8_t* path) {
  noteNetworkStatus(contact, path_len);

  if (_serial->isConnected()) {
    if (is_new) {
      writeContactRespFrame(PUSH_CODE_NEW_ADVERT, contact);
    } else {
      out_frame[0] = PUSH_CODE_ADVERT;
      memcpy(&out_frame[1], contact.id.pub_key, PUB_KEY_SIZE);
      _serial->writeFrame(out_frame, 1 + PUB_KEY_SIZE);
    }
  } else {
#ifdef DISPLAY_CLASS
    if (_ui) _ui->notify(UIEventType::newContactMessage);
#endif
  }

  // add inbound-path to mem cache
  if (path && mesh::Packet::isValidPathLen(path_len)) {  // check path is valid
    AdvertPath* p = advert_paths;
    uint32_t oldest = 0xFFFFFFFF;
    for (int i = 0; i < ADVERT_PATH_TABLE_SIZE; i++) {   // check if already in table, otherwise evict oldest
      if (memcmp(advert_paths[i].pubkey_prefix, contact.id.pub_key, sizeof(AdvertPath::pubkey_prefix)) == 0) {
        p = &advert_paths[i];   // found
        break;
      }
      if (advert_paths[i].recv_timestamp < oldest) {
        oldest = advert_paths[i].recv_timestamp;
        p = &advert_paths[i];
      }
    }

    memcpy(p->pubkey_prefix, contact.id.pub_key, sizeof(p->pubkey_prefix));
    strcpy(p->name, contact.name);
    p->recv_timestamp = getRTCClock()->getCurrentTime();
    p->path_len = mesh::Packet::copyPath(p->path, path, path_len);
  }

  if (!is_new) dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY); // only schedule lazy write for contacts that are in contacts[]
}

static int sort_by_recent(const void *a, const void *b) {
  return ((AdvertPath *) b)->recv_timestamp - ((AdvertPath *) a)->recv_timestamp;
}

int MyMesh::getRecentlyHeard(AdvertPath dest[], int max_num) {
  if (max_num > ADVERT_PATH_TABLE_SIZE) max_num = ADVERT_PATH_TABLE_SIZE;
  qsort(advert_paths, ADVERT_PATH_TABLE_SIZE, sizeof(advert_paths[0]), sort_by_recent);

  for (int i = 0; i < max_num; i++) {
    dest[i] = advert_paths[i];
  }
  return max_num;
}

static int sortNetworkStatusByRecent(const void* a, const void* b) {
  uint32_t ta = ((const NetworkStatusEntry*)a)->recv_timestamp;
  uint32_t tb = ((const NetworkStatusEntry*)b)->recv_timestamp;
  if (tb > ta) return 1;
  if (tb < ta) return -1;
  return 0;
}

uint8_t MyMesh::getRouteStatusFlags(uint8_t path_len) const {
  if (path_len == OUT_PATH_UNKNOWN) return NETWORK_STATUS_DIRECT;
  if (!mesh::Packet::isValidPathLen(path_len)) return 0;
  return (path_len & 63) == 0 ? NETWORK_STATUS_DIRECT : NETWORK_STATUS_VIA_RELAY;
}

void MyMesh::noteNetworkStatus(const ContactInfo& contact, uint8_t path_len) {
  if (contact.type != ADV_TYPE_REPEATER && contact.type != ADV_TYPE_CHAT) return;
  if (last_rx_millis == 0) return;
  NetworkStatusEntry* entry = network_status;
  uint32_t oldest = 0xFFFFFFFF;
  for (int i = 0; i < NETWORK_STATUS_TABLE_SIZE; i++) {
    if (memcmp(network_status[i].pubkey_prefix, contact.id.pub_key,
               sizeof(network_status[i].pubkey_prefix)) == 0) {
      entry = &network_status[i];
      break;
    }
    if (network_status[i].recv_timestamp < oldest) {
      oldest = network_status[i].recv_timestamp;
      entry = &network_status[i];
    }
  }
  memcpy(entry->pubkey_prefix, contact.id.pub_key, sizeof(entry->pubkey_prefix));
  StrHelper::strzcpy(entry->name, contact.name, sizeof(entry->name));
  entry->recv_timestamp = getRTCClock()->getCurrentTime();
  entry->snr_q4 = last_rx_snr_q4;
  entry->rssi = last_rx_rssi;
  entry->type = contact.type;
  entry->path_len = path_len;
  entry->flags = (contact.type == ADV_TYPE_REPEATER ? NETWORK_STATUS_REPEATER
                                                    : NETWORK_STATUS_CLIENT_REPEAT_UNKNOWN) |
                 getRouteStatusFlags(path_len);
}

static uint32_t hashTrafficName(const char* name) {
  uint32_t h = 2166136261UL;
  while (name && *name) {
    h ^= (uint8_t)*name++;
    h *= 16777619UL;
  }
  return h;
}

static void splitChannelText(const char* fallback_name, const char* text,
                             char* origin, size_t origin_len, char* body, size_t body_len) {
  const char* sep = text ? strstr(text, ": ") : NULL;
  if (sep && sep > text) {
    size_t origin_copy = (size_t)(sep - text);
    if (origin_copy >= origin_len) origin_copy = origin_len - 1;
    memcpy(origin, text, origin_copy);
    origin[origin_copy] = 0;
    StrHelper::strzcpy(body, sep + 2, body_len);
  } else {
    StrHelper::strzcpy(origin, fallback_name, origin_len);
    StrHelper::strzcpy(body, text ? text : "", body_len);
  }
}

void MyMesh::noteTrafficStatus(const char* name, uint8_t slot, uint8_t path_len, uint8_t flags) {
  if (last_rx_millis == 0) return;
  uint32_t name_hash = hashTrafficName(name);
  uint8_t key[7] = {'T', slot, (uint8_t)name_hash, (uint8_t)(name_hash >> 8),
                    (uint8_t)(name_hash >> 16), (uint8_t)(name_hash >> 24), path_len};
  NetworkStatusEntry* entry = network_status;
  uint32_t oldest = 0xFFFFFFFF;
  for (int i = 0; i < NETWORK_STATUS_TABLE_SIZE; i++) {
    if (memcmp(network_status[i].pubkey_prefix, key, sizeof(key)) == 0) {
      entry = &network_status[i];
      break;
    }
    if (network_status[i].recv_timestamp < oldest) {
      oldest = network_status[i].recv_timestamp;
      entry = &network_status[i];
    }
  }
  memcpy(entry->pubkey_prefix, key, sizeof(entry->pubkey_prefix));
  StrHelper::strzcpy(entry->name, name, sizeof(entry->name));
  entry->recv_timestamp = getRTCClock()->getCurrentTime();
  entry->snr_q4 = last_rx_snr_q4;
  entry->rssi = last_rx_rssi;
  entry->type = ADV_TYPE_NONE;
  entry->path_len = path_len;
  entry->flags = flags | getRouteStatusFlags(path_len);
}

int MyMesh::getRecentNetworkStatus(NetworkStatusEntry dest[], int max_num,
                                   uint32_t max_age_secs) {
  if (max_num > NETWORK_STATUS_TABLE_SIZE) max_num = NETWORK_STATUS_TABLE_SIZE;
  qsort(network_status, NETWORK_STATUS_TABLE_SIZE, sizeof(network_status[0]),
        sortNetworkStatusByRecent);
  uint32_t now = getRTCClock()->getCurrentTime();
  int count = 0;
  for (int i = 0; i < NETWORK_STATUS_TABLE_SIZE && count < max_num; i++) {
    if (network_status[i].name[0] == 0 || network_status[i].recv_timestamp == 0) continue;
    uint32_t age = network_status[i].recv_timestamp > now ? 0 : now - network_status[i].recv_timestamp;
    if (age > max_age_secs) continue;
    dest[count++] = network_status[i];
  }
  return count;
}

void MyMesh::noteChannelChat(const char* channel_name, mesh::Packet* pkt, const char* text) {
  recent_chat_head = (recent_chat_head + 1) % RECENT_CHAT_TABLE_SIZE;
  RecentChatEntry* entry = &recent_chat[recent_chat_head];
  entry->recv_timestamp = getRTCClock()->getCurrentTime();
  entry->path_len = pkt && pkt->isRouteFlood() ? pkt->path_len : OUT_PATH_UNKNOWN;
  entry->flags = getRouteStatusFlags(entry->path_len);
  entry->snr_q4 = pkt ? (int8_t)(pkt->getSNR() * 4) : 0;
  entry->rssi = pkt ? last_rx_rssi : 0;
  splitChannelText(channel_name, text, entry->origin, sizeof(entry->origin),
                   entry->text, sizeof(entry->text));
}

int MyMesh::getRecentChannelMessages(RecentChatEntry dest[], int max_num) {
  if (max_num > RECENT_CHAT_TABLE_SIZE) max_num = RECENT_CHAT_TABLE_SIZE;
  int count = 0;
  for (int offset = 0; offset < RECENT_CHAT_TABLE_SIZE && count < max_num; offset++) {
    int i = recent_chat_head - offset;
    if (i < 0) i += RECENT_CHAT_TABLE_SIZE;
    if (recent_chat[i].recv_timestamp == 0 || recent_chat[i].text[0] == 0) continue;
    dest[count++] = recent_chat[i];
  }
  return count;
}

bool MyMesh::startLinkTest() {
  memset(&link_test, 0, sizeof(link_test));
  link_test.done = true;
  link_test.best_snr_q4 = -128;
  link_test.worst_snr_q4 = 127;
  return false;
}

void MyMesh::getLinkTestStatus(LinkTestStatus& dest) const {
  dest = link_test;
}

void MyMesh::onContactPathUpdated(const ContactInfo &contact) {
  out_frame[0] = PUSH_CODE_PATH_UPDATED;
  memcpy(&out_frame[1], contact.id.pub_key, PUB_KEY_SIZE);
  _serial->writeFrame(out_frame, 1 + PUB_KEY_SIZE); // NOTE: app may not be connected

  dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
}

ContactInfo*  MyMesh::processAck(const uint8_t *data) {
  // see if matches any in a table
  for (int i = 0; i < EXPECTED_ACK_TABLE_SIZE; i++) {
    if (memcmp(data, &expected_ack_table[i].ack, 4) == 0) { // got an ACK from recipient
      out_frame[0] = PUSH_CODE_SEND_CONFIRMED;
      memcpy(&out_frame[1], data, 4);
      uint32_t trip_time = _ms->getMillis() - expected_ack_table[i].msg_sent;
      memcpy(&out_frame[5], &trip_time, 4);
      _serial->writeFrame(out_frame, 9);

      // NOTE: the same ACK can be received multiple times!
      expected_ack_table[i].ack = 0; // clear expected hash, now that we have received ACK
      return expected_ack_table[i].contact;
    }
  }
  return checkConnectionsAck(data);
}

void MyMesh::queueMessage(const ContactInfo &from, uint8_t txt_type, mesh::Packet *pkt,
                          uint32_t sender_timestamp, const uint8_t *extra, int extra_len, const char *text) {
  int i = 0;
  if (app_target_ver >= 3) {
    out_frame[i++] = RESP_CODE_CONTACT_MSG_RECV_V3;
    out_frame[i++] = (int8_t)(pkt->getSNR() * 4);
    out_frame[i++] = 0; // reserved1
    out_frame[i++] = 0; // reserved2
  } else {
    out_frame[i++] = RESP_CODE_CONTACT_MSG_RECV;
  }
  memcpy(&out_frame[i], from.id.pub_key, 6);
  i += 6; // just 6-byte prefix
  uint8_t path_len = out_frame[i++] = pkt->isRouteFlood() ? pkt->path_len : 0xFF;
  out_frame[i++] = txt_type;
  memcpy(&out_frame[i], &sender_timestamp, 4);
  i += 4;
  if (extra_len > 0) {
    memcpy(&out_frame[i], extra, extra_len);
    i += extra_len;
  }
  int tlen = strlen(text); // TODO: UTF-8 ??
  if (i + tlen > MAX_FRAME_SIZE) {
    tlen = MAX_FRAME_SIZE - i;
  }
  memcpy(&out_frame[i], text, tlen);
  i += tlen;
  addToOfflineQueue(out_frame, i);

  if (_serial->isConnected()) {
    uint8_t frame[1];
    frame[0] = PUSH_CODE_MSG_WAITING; // send push 'tickle'
    _serial->writeFrame(frame, 1);
  }

#ifdef DISPLAY_CLASS
  // we only want to show text messages on display, not cli data
  bool should_display = txt_type == TXT_TYPE_PLAIN || txt_type == TXT_TYPE_SIGNED_PLAIN;
  if (should_display && _ui) {
    _ui->newMsg(path_len, from.name, text, offline_queue_len, UI_MSG_FLAG_DIRECT);
    if (!_serial->isConnected()) {
      _ui->notify(UIEventType::contactMessage);
    }
  }
#endif
}

bool MyMesh::filterRecvFloodPacket(mesh::Packet* packet) {
  // REVISIT: try to determine which Region (from transport_codes[1]) that Sender is indicating for replies/responses
  //    if unknown, fallback to finding Region from transport_codes[0], the 'scope' used by Sender
  return false;
}

bool MyMesh::allowPacketForward(const mesh::Packet* packet) {
  return _prefs.isRepeatEn();
}

void MyMesh::sendFloodScoped(const TransportKey& scope, mesh::Packet* pkt, uint32_t delay_millis) {
  if (scope.isNull()) {
    sendFlood(pkt, delay_millis, _prefs.path_hash_mode + 1);
  } else {
    uint16_t codes[2];
    codes[0] = scope.calcTransportCode(pkt);
    codes[1] = 0;  // REVISIT: set to 'home' Region, for sender/return region?
    sendFlood(pkt, codes, delay_millis, _prefs.path_hash_mode + 1);
  }
}

void MyMesh::sendFloodScoped(const ContactInfo& recipient, mesh::Packet* pkt, uint32_t delay_millis) {
  // TODO: dynamic send_scope, depending on recipient and current 'home' Region
  if (send_unscoped) {
    sendFlood(pkt, delay_millis, _prefs.path_hash_mode + 1);  // app has explicitly requested un-scoped
  } else {
    TransportKey default_scope;
    memcpy(&default_scope.key, _prefs.default_scope_key, sizeof(default_scope.key));

    auto scope = send_scope.isNull() ? &default_scope : &send_scope;
    sendFloodScoped(*scope, pkt, delay_millis);
  }
}
void MyMesh::sendFloodScoped(const mesh::GroupChannel& channel, mesh::Packet* pkt, uint32_t delay_millis) {
  // TODO: have per-channel send_scope
  if (send_unscoped) {
    sendFlood(pkt, delay_millis, _prefs.path_hash_mode + 1);  // app has explicitly requested un-scoped
  } else {
    TransportKey default_scope;
    memcpy(&default_scope.key, _prefs.default_scope_key, sizeof(default_scope.key));

    auto scope = send_scope.isNull() ? &default_scope : &send_scope;
    sendFloodScoped(*scope, pkt, delay_millis);
  }
}

void MyMesh::onMessageRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                           const char *text) {
  markConnectionActive(from); // in case this is from a server, and we have a connection
  noteNetworkStatus(from, pkt && pkt->isRouteFlood() ? pkt->path_len : OUT_PATH_UNKNOWN);
  queueMessage(from, TXT_TYPE_PLAIN, pkt, sender_timestamp, NULL, 0, text);
}

void MyMesh::onCommandDataRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                               const char *text) {
  markConnectionActive(from); // in case this is from a server, and we have a connection
  noteNetworkStatus(from, pkt && pkt->isRouteFlood() ? pkt->path_len : OUT_PATH_UNKNOWN);
  queueMessage(from, TXT_TYPE_CLI_DATA, pkt, sender_timestamp, NULL, 0, text);
}

void MyMesh::onSignedMessageRecv(const ContactInfo &from, mesh::Packet *pkt, uint32_t sender_timestamp,
                                 const uint8_t *sender_prefix, const char *text) {
  markConnectionActive(from);
  noteNetworkStatus(from, pkt && pkt->isRouteFlood() ? pkt->path_len : OUT_PATH_UNKNOWN);
  // from.sync_since change needs to be persisted
  dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
  queueMessage(from, TXT_TYPE_SIGNED_PLAIN, pkt, sender_timestamp, sender_prefix, 4, text);
}

void MyMesh::onChannelMessageRecv(const mesh::GroupChannel &channel, mesh::Packet *pkt, uint32_t timestamp,
                                  const char *text) {
  int i = 0;
  if (app_target_ver >= 3) {
    out_frame[i++] = RESP_CODE_CHANNEL_MSG_RECV_V3;
    out_frame[i++] = (int8_t)(pkt->getSNR() * 4);
    out_frame[i++] = 0; // reserved1
    out_frame[i++] = 0; // reserved2
  } else {
    out_frame[i++] = RESP_CODE_CHANNEL_MSG_RECV;
  }

  uint8_t channel_idx = findChannelIdx(channel);
  out_frame[i++] = channel_idx;
  uint8_t path_len = out_frame[i++] = pkt->isRouteFlood() ? pkt->path_len : 0xFF;

  out_frame[i++] = TXT_TYPE_PLAIN;
  memcpy(&out_frame[i], &timestamp, 4);
  i += 4;
  int tlen = strlen(text); // TODO: UTF-8 ??
  if (i + tlen > MAX_FRAME_SIZE) {
    tlen = MAX_FRAME_SIZE - i;
  }
  memcpy(&out_frame[i], text, tlen);
  i += tlen;
  addToOfflineQueue(out_frame, i);

#ifdef DISPLAY_CLASS
  const char* channel_name = "Unknown";
  ChannelDetails channel_details;
  if (getChannel(channel_idx, channel_details)) channel_name = channel_details.name;
  noteTrafficStatus(channel_name, channel_idx, path_len, NETWORK_STATUS_CHANNEL_TRAFFIC);
  noteChannelChat(channel_name, pkt, text);
  const char* mention_text = channelMentionBodyText(text);
  uint8_t ui_flags = textMentionsNodeName(this, mention_text, _prefs.node_name)
                         ? UI_MSG_FLAG_MENTION
                         : UI_MSG_FLAG_NONE;
#endif

  if (_serial->isConnected()) {
    uint8_t frame[1];
    frame[0] = PUSH_CODE_MSG_WAITING; // send push 'tickle'
    _serial->writeFrame(frame, 1);
  } else {
#ifdef DISPLAY_CLASS
#if !UI_NOTIFY_ONLY_IMPORTANT_MESSAGES
    if (_ui) _ui->notify(UIEventType::channelMessage);
#endif
#endif
  }
#ifdef DISPLAY_CLASS
  if (_ui) _ui->newMsg(path_len, channel_name, text, offline_queue_len, ui_flags);
#endif
}

void MyMesh::onChannelDataRecv(const mesh::GroupChannel &channel, mesh::Packet *pkt, uint16_t data_type,
                               const uint8_t *data, size_t data_len) {
  if (data_len > MAX_CHANNEL_DATA_LENGTH) {
    MESH_DEBUG_PRINTLN("onChannelDataRecv: dropping payload_len=%d exceeds frame limit=%d",
                       (uint32_t)data_len, (uint32_t)MAX_CHANNEL_DATA_LENGTH);
    return;
  }

  int i = 0;
  out_frame[i++] = RESP_CODE_CHANNEL_DATA_RECV;
  out_frame[i++] = (int8_t)(pkt->getSNR() * 4);
  out_frame[i++] = 0; // reserved1
  out_frame[i++] = 0; // reserved2

  uint8_t channel_idx = findChannelIdx(channel);
  out_frame[i++] = channel_idx;
  out_frame[i++] = pkt->isRouteFlood() ? pkt->path_len : 0xFF;
  out_frame[i++] = (uint8_t)(data_type & 0xFF);
  out_frame[i++] = (uint8_t)(data_type >> 8);
  out_frame[i++] = (uint8_t)data_len;

  int copy_len = (int)data_len;
  if (copy_len > 0) {
    memcpy(&out_frame[i], data, copy_len);
    i += copy_len;
  }
  addToOfflineQueue(out_frame, i);

  if (_serial->isConnected()) {
    uint8_t frame[1];
    frame[0] = PUSH_CODE_MSG_WAITING; // send push 'tickle'
    _serial->writeFrame(frame, 1);
  }
}

uint8_t MyMesh::onContactRequest(const ContactInfo &contact, uint32_t sender_timestamp, const uint8_t *data,
                                 uint8_t len, uint8_t *reply) {
  if (data[0] == REQ_TYPE_GET_TELEMETRY_DATA) {
    uint8_t permissions = 0;
    uint8_t cp = contact.flags >> 1; // LSB used as 'favourite' bit (so only use upper bits)

    if (_prefs.telemetry_mode_base == TELEM_MODE_ALLOW_ALL) {
      permissions = TELEM_PERM_BASE;
    } else if (_prefs.telemetry_mode_base == TELEM_MODE_ALLOW_FLAGS) {
      permissions = cp & TELEM_PERM_BASE;
    }

    if (_prefs.telemetry_mode_loc == TELEM_MODE_ALLOW_ALL) {
      permissions |= TELEM_PERM_LOCATION;
    } else if (_prefs.telemetry_mode_loc == TELEM_MODE_ALLOW_FLAGS) {
      permissions |= cp & TELEM_PERM_LOCATION;
    }

    if (_prefs.telemetry_mode_env == TELEM_MODE_ALLOW_ALL) {
      permissions |= TELEM_PERM_ENVIRONMENT;
    } else if (_prefs.telemetry_mode_env == TELEM_MODE_ALLOW_FLAGS) {
      permissions |= cp & TELEM_PERM_ENVIRONMENT;
    }

    uint8_t perm_mask = ~(data[1]);    // NEW: first reserved byte (of 4), is now inverse mask to apply to permissions
    permissions &= perm_mask;

    if (permissions & TELEM_PERM_BASE) { // only respond if base permission bit is set
      telemetry.reset();
      telemetry.addVoltage(TELEM_CHANNEL_SELF, (float)board.getBattMilliVolts() / 1000.0f);
      // query other sensors -- target specific
      sensors.querySensors(permissions, telemetry);

      float temperature = board.getMCUTemperature();
      if(!isnan(temperature)) { // Supported boards with built-in temperature sensor. ESP32-C3 may return NAN
        telemetry.addTemperature(TELEM_CHANNEL_SELF, temperature); // Built-in MCU Temperature
      }

      memcpy(reply, &sender_timestamp,
             4); // reflect sender_timestamp back in response packet (kind of like a 'tag')

      uint8_t tlen = telemetry.getSize();
      memcpy(&reply[4], telemetry.getBuffer(), tlen);
      return 4 + tlen;
    }
  }
  return 0; // unknown
}

void MyMesh::onContactResponse(const ContactInfo &contact, const uint8_t *data, uint8_t len) {
  uint32_t tag;
  memcpy(&tag, data, 4);

  if (pending_login && memcmp(&pending_login, contact.id.pub_key, 4) == 0) { // check for login response
    // yes, is response to pending sendLogin()
    pending_login = 0;

    int i = 0;
    if (memcmp(&data[4], "OK", 2) == 0) { // legacy Repeater login OK response
      out_frame[i++] = PUSH_CODE_LOGIN_SUCCESS;
      out_frame[i++] = 0; // legacy: is_admin = false
      memcpy(&out_frame[i], contact.id.pub_key, 6);
      i += 6;                                     // pub_key_prefix
    } else if (data[4] == RESP_SERVER_LOGIN_OK) { // new login response
      uint16_t keep_alive_secs = ((uint16_t)data[5]) * 16;
      if (keep_alive_secs > 0) {
        startConnection(contact, keep_alive_secs);
      }
      out_frame[i++] = PUSH_CODE_LOGIN_SUCCESS;
      out_frame[i++] = data[6]; // permissions (eg. is_admin)
      memcpy(&out_frame[i], contact.id.pub_key, 6);
      i += 6; // pub_key_prefix
      memcpy(&out_frame[i], &tag, 4);
      i += 4; // NEW: include server timestamp
      out_frame[i++] = data[7]; // NEW (v7): ACL permissions
      out_frame[i++] = data[12]; // FIRMWARE_VER_LEVEL
    } else {
      out_frame[i++] = PUSH_CODE_LOGIN_FAIL;
      out_frame[i++] = 0; // reserved
      memcpy(&out_frame[i], contact.id.pub_key, 6);
      i += 6; // pub_key_prefix
    }
    _serial->writeFrame(out_frame, i);
  } else if (len > 4 && // check for status response
             pending_status &&
             memcmp(&pending_status, contact.id.pub_key, 4) == 0 // legacy matching scheme
                                                                 // FUTURE: tag == pending_status
  ) {
    pending_status = 0;

    int i = 0;
    out_frame[i++] = PUSH_CODE_STATUS_RESPONSE;
    out_frame[i++] = 0; // reserved
    memcpy(&out_frame[i], contact.id.pub_key, 6);
    i += 6; // pub_key_prefix
    memcpy(&out_frame[i], &data[4], len - 4);
    i += (len - 4);
    _serial->writeFrame(out_frame, i);
  } else if (len > 4 && tag == pending_telemetry) {  // check for matching response tag
    pending_telemetry = 0;

    int i = 0;
    out_frame[i++] = PUSH_CODE_TELEMETRY_RESPONSE;
    out_frame[i++] = 0; // reserved
    memcpy(&out_frame[i], contact.id.pub_key, 6);
    i += 6; // pub_key_prefix
    memcpy(&out_frame[i], &data[4], len - 4);
    i += (len - 4);
    _serial->writeFrame(out_frame, i);
  } else if (len > 4 && tag == pending_req) {  // check for matching response tag
    pending_req = 0;

    int i = 0;
    out_frame[i++] = PUSH_CODE_BINARY_RESPONSE;
    out_frame[i++] = 0; // reserved
    memcpy(&out_frame[i], &tag, 4);   // app needs to match this to RESP_CODE_SENT.tag
    i += 4;
    memcpy(&out_frame[i], &data[4], len - 4);
    i += (len - 4);
    _serial->writeFrame(out_frame, i);
  }
}

bool MyMesh::onContactPathRecv(ContactInfo& contact, uint8_t* in_path, uint8_t in_path_len, uint8_t* out_path, uint8_t out_path_len, uint8_t extra_type, uint8_t* extra, uint8_t extra_len) {
  if (extra_type == PAYLOAD_TYPE_RESPONSE && extra_len > 4) {
    uint32_t tag;
    memcpy(&tag, extra, 4);

    if (tag == pending_discovery) {  // check for matching response tag)
      pending_discovery = 0;

      if (!mesh::Packet::isValidPathLen(in_path_len) || !mesh::Packet::isValidPathLen(out_path_len)) {
        MESH_DEBUG_PRINTLN("onContactPathRecv, invalid path sizes: %d, %d", in_path_len, out_path_len);
      } else {
        int i = 0;
        out_frame[i++] = PUSH_CODE_PATH_DISCOVERY_RESPONSE;
        out_frame[i++] = 0; // reserved
        memcpy(&out_frame[i], contact.id.pub_key, 6);
        i += 6; // pub_key_prefix
        out_frame[i++] = out_path_len;
        i += mesh::Packet::writePath(&out_frame[i], out_path, out_path_len);
        out_frame[i++] = in_path_len;
        i += mesh::Packet::writePath(&out_frame[i], in_path, in_path_len);
        // NOTE: telemetry data in 'extra' is discarded at present

        _serial->writeFrame(out_frame, i);
      }
      return false;  // DON'T send reciprocal path!
    }
  }
  // let base class handle received path and data
  return BaseChatMesh::onContactPathRecv(contact, in_path, in_path_len, out_path, out_path_len, extra_type, extra, extra_len);
}

void MyMesh::onControlDataRecv(mesh::Packet *packet) {
  if (packet->payload_len + 4 > sizeof(out_frame)) {
    MESH_DEBUG_PRINTLN("onControlDataRecv(), payload_len too long: %d", packet->payload_len);
    return;
  }
  int i = 0;
  out_frame[i++] = PUSH_CODE_CONTROL_DATA;
  out_frame[i++] = (int8_t)(_radio->getLastSNR() * 4);
  out_frame[i++] = (int8_t)(_radio->getLastRSSI());
  out_frame[i++] = packet->path_len;
  memcpy(&out_frame[i], packet->payload, packet->payload_len);
  i += packet->payload_len;

  if (_serial->isConnected()) {
    _serial->writeFrame(out_frame, i);
  } else {
    MESH_DEBUG_PRINTLN("onControlDataRecv(), data received while app offline");
  }
}

void MyMesh::onRawDataRecv(mesh::Packet *packet) {
  if (packet->payload_len + 4 > sizeof(out_frame)) {
    MESH_DEBUG_PRINTLN("onRawDataRecv(), payload_len too long: %d", packet->payload_len);
    return;
  }
  int i = 0;
  out_frame[i++] = PUSH_CODE_RAW_DATA;
  out_frame[i++] = (int8_t)(_radio->getLastSNR() * 4);
  out_frame[i++] = (int8_t)(_radio->getLastRSSI());
  out_frame[i++] = 0xFF; // reserved (possibly path_len in future)
  memcpy(&out_frame[i], packet->payload, packet->payload_len);
  i += packet->payload_len;

  if (_serial->isConnected()) {
    _serial->writeFrame(out_frame, i);
  } else {
    MESH_DEBUG_PRINTLN("onRawDataRecv(), data received while app offline");
  }
}

void MyMesh::onTraceRecv(mesh::Packet *packet, uint32_t tag, uint32_t auth_code, uint8_t flags,
                         const uint8_t *path_snrs, const uint8_t *path_hashes, uint8_t path_len) {
  uint8_t path_sz = flags & 0x03;  // NEW v1.11+
  if (12 + path_len + (path_len >> path_sz) + 1 > sizeof(out_frame)) {
    MESH_DEBUG_PRINTLN("onTraceRecv(), path_len is too long: %d", (uint32_t)path_len);
    return;
  }
  int i = 0;
  out_frame[i++] = PUSH_CODE_TRACE_DATA;
  out_frame[i++] = 0; // reserved
  out_frame[i++] = path_len;
  out_frame[i++] = flags;
  memcpy(&out_frame[i], &tag, 4);
  i += 4;
  memcpy(&out_frame[i], &auth_code, 4);
  i += 4;
  memcpy(&out_frame[i], path_hashes, path_len);
  i += path_len;

  memcpy(&out_frame[i], path_snrs, path_len >> path_sz);
  i += path_len >> path_sz;
  out_frame[i++] = (int8_t)(packet->getSNR() * 4); // extra/final SNR (to this node)

  if (_serial->isConnected()) {
    _serial->writeFrame(out_frame, i);
  } else {
    MESH_DEBUG_PRINTLN("onTraceRecv(), data received while app offline");
  }
}

uint32_t MyMesh::calcFloodTimeoutMillisFor(uint32_t pkt_airtime_millis) const {
  return SEND_TIMEOUT_BASE_MILLIS + (FLOOD_SEND_TIMEOUT_FACTOR * pkt_airtime_millis);
}
uint32_t MyMesh::calcDirectTimeoutMillisFor(uint32_t pkt_airtime_millis, uint8_t path_len) const {
  uint8_t path_hash_count = path_len & 63;
  return SEND_TIMEOUT_BASE_MILLIS +
         ((pkt_airtime_millis * DIRECT_SEND_PERHOP_FACTOR + DIRECT_SEND_PERHOP_EXTRA_MILLIS) *
          (path_hash_count + 1));
}

void MyMesh::onSendTimeout() {}

MyMesh::MyMesh(mesh::Radio &radio, mesh::RNG &rng, mesh::RTCClock &rtc, SimpleMeshTables &tables, DataStore& store, AbstractUITask* ui)
    : BaseChatMesh(radio, *new ArduinoMillis(), rng, rtc, *new StaticPoolPacketManager(16), tables),
      _serial(NULL), telemetry(MAX_PACKET_PAYLOAD - 4), _store(&store), _ui(ui), _iter(0) {
  _iter_started = false;
  _cli_rescue = false;
  offline_queue_len = 0;
  app_target_ver = 0;
  clearPendingReqs();
  next_ack_idx = 0;
  sign_data = NULL;
  dirty_contacts_expiry = 0;
  memset(advert_paths, 0, sizeof(advert_paths));
  memset(network_status, 0, sizeof(network_status));
  memset(recent_chat, 0, sizeof(recent_chat));
  memset(&link_test, 0, sizeof(link_test));
  link_test.best_snr_q4 = -128;
  link_test.worst_snr_q4 = 127;
  last_rx_snr_q4 = 0;
  last_rx_rssi = 0;
  last_rx_millis = 0;
  recent_chat_head = 0;
  channel_busy_ms = 0;
  channel_busy_sample_ms = millis();
  next_auto_advert = 0;
  phone_gps_last_update_ms = 0;
  memset(send_scope.key, 0, sizeof(send_scope.key));
  send_unscoped = false;

  // defaults
  _prefs.airtime_factor = 1.0;
  strcpy(_prefs.node_name, "NONAME");
  _prefs.freq = LORA_FREQ;
  _prefs.sf = LORA_SF;
  _prefs.bw = LORA_BW;
  _prefs.cr = LORA_CR;
  _prefs.tx_power_dbm = LORA_TX_POWER;
  _prefs.gps_enabled = 0;       // GPS disabled by default
  _prefs.gps_interval = 0;      // No automatic GPS updates by default
  _prefs.adc_multiplier = 0.0f;
  _prefs.notify_mode = DEFAULT_NOTIFY_MODE & NOTIFY_MODE_ALL;
  _prefs.notify_gpio_pin = DEFAULT_NOTIFY_GPIO_PIN;
  _prefs.notify_tone_pin = DEFAULT_NOTIFY_TONE_PIN;
  _prefs.notify_vibe_pin = DEFAULT_NOTIFY_VIBE_PIN;
  _prefs.notify_tone_id = DEFAULT_NOTIFY_TONE_ID;
  _prefs.notify_tone_volume = DEFAULT_NOTIFY_TONE_VOLUME;
  _prefs.auto_advert_interval_mins = 0;
  _prefs.ch2_mode = CH2_MODE_OFF;
  _prefs.board_leds_enabled = BOARD_LEDS_DEFAULT ? 1 : 0;
#if defined(UI_T096_PREMIUM_TFT)
  _prefs.ui_font = 10;
#else
  _prefs.ui_font = 5;
#endif
  _prefs.ui_theme = 0;
  _prefs.unread_led_enabled = 1;
  _prefs.msg_popup_enabled = 1;
  _prefs.important_notify_mode = DEFAULT_IMPORTANT_NOTIFY_MODE & NOTIFY_MODE_ALL;
#ifdef UI_FORCE_IMPORTANT_NOTIFY_MODE
  _prefs.important_notify_mode = UI_FORCE_IMPORTANT_NOTIFY_MODE & NOTIFY_MODE_ALL;
#endif
  _prefs.notifications_muted = 0;
  _prefs.ui_top_color = 1;
  _prefs.ui_bottom_color = 0;
  _prefs.backlight_timeout_idx = 0;
  _prefs.offline_dm_led_enabled = 1;
  _prefs.ble_dm_led_enabled = 1;
  _prefs.low_battery_shutdown_enabled = LOW_BATTERY_SHUTDOWN_DEFAULT_ENABLED ? 1 : 0;
  _prefs.notify_tone_bridge_enabled = 0;
  _prefs.notify_tone_8bit_enabled = 0;
  _prefs.notify_pin_fix_version = 0;
#ifdef DEFAULT_NOTIFY_TONE_HIGH_DRIVE
  _prefs.notify_tone_high_drive_enabled = DEFAULT_NOTIFY_TONE_HIGH_DRIVE ? 1 : 0;
#else
  _prefs.notify_tone_high_drive_enabled = 0;
#endif
  _prefs.notify_tone_resonance_hz = DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
  _prefs.notify_tone_dm_id = _prefs.notify_tone_id;
  _prefs.notify_tone_mention_id = _prefs.notify_tone_id;
  _prefs.notify_tone_system_id = _prefs.notify_tone_id;
  _prefs.smart_profile_id = SMART_PROFILE_CUSTOM;
  _prefs.favorite_setting_1 = SMART_FAVORITE_NOTIFY_MODE;
  _prefs.favorite_setting_2 = SMART_FAVORITE_SYSTEM_TONE;
  _prefs.favorite_setting_3 = SMART_FAVORITE_BLUETOOTH;
  _prefs.gps_source = GPS_SOURCE_HW;
  _prefs.radio_fem_rxgain = 1;
  _prefs.radio_fem_txgain = 0;
  //_prefs.rx_delay_base = 10.0f;  enable once new algo fixed
  _prefs.setRepeatEn(false);
#if defined(USE_SX1262) || defined(USE_SX1268)
#ifdef SX126X_RX_BOOSTED_GAIN
  _prefs.rx_boosted_gain = SX126X_RX_BOOSTED_GAIN;
#else
  _prefs.rx_boosted_gain = 1; // enabled by default
#endif
#endif
}

void MyMesh::begin(bool has_display) {
  BaseChatMesh::begin();

  if (!_store->loadMainIdentity(self_id)) {
    self_id = radio_new_identity(); // create new random identity
    int count = 0;
    while (count < 10 && (self_id.pub_key[0] == 0x00 || self_id.pub_key[0] == 0xFF)) { // reserved id hashes
      self_id = radio_new_identity();
      count++;
    }
    _store->saveMainIdentity(self_id);
  }

// if name is provided as a build flag, use that as default node name instead
#ifdef ADVERT_NAME
  strcpy(_prefs.node_name, ADVERT_NAME);
#else
  // use hex of first 4 bytes of identity public key as default node name
  char pub_key_hex[10];
  mesh::Utils::toHex(pub_key_hex, self_id.pub_key, 4);
  strcpy(_prefs.node_name, pub_key_hex);
#endif

  // if build provides default-scope, init with that
#ifdef DEFAULT_FLOOD_SCOPE_NAME
  strcpy(_prefs.default_scope_name, DEFAULT_FLOOD_SCOPE_NAME);
  {
    TransportKeyStore temp;
    TransportKey key;
    temp.getAutoKeyFor(0, "#" DEFAULT_FLOOD_SCOPE_NAME, key);
    memcpy(_prefs.default_scope_key, key.key, sizeof(key.key));
  }
#endif

  // load persisted prefs
  _store->loadPrefs(_prefs);
  sensors.node_lat = _prefs.node_lat;
  sensors.node_lon = _prefs.node_lon;

  // sanitise bad pref values
  _prefs.rx_delay_base = constrain(_prefs.rx_delay_base, 0, 20.0f);
  _prefs.airtime_factor = constrain(_prefs.airtime_factor, 0, 9.0f);
  _prefs.freq = constrain(_prefs.freq, 150.0f, 2500.0f);
  _prefs.bw = constrain(_prefs.bw, 7.8f, 500.0f);
  _prefs.sf = constrain(_prefs.sf, 5, 12);
  _prefs.cr = constrain(_prefs.cr, 5, 8);
  _prefs.tx_power_dbm = constrain(_prefs.tx_power_dbm, -9, MAX_LORA_TX_POWER);
  _prefs.gps_enabled = constrain(_prefs.gps_enabled, 0, 1);  // Ensure boolean 0 or 1
  _prefs.gps_interval = constrain(_prefs.gps_interval, 0, 86400);  // Max 24 hours

#if UI_PHONE_GPS == 1
  if (_prefs.gps_source != GPS_SOURCE_PHONE) _prefs.gps_source = GPS_SOURCE_HW;
#else
  _prefs.gps_source = GPS_SOURCE_HW;
  phone_gps_last_update_ms = 0;
#endif
  if (!isValidAutoAdvertIntervalMins(_prefs.auto_advert_interval_mins)) {
    _prefs.auto_advert_interval_mins = 0;
  }
  _prefs.ch2_mode = CH2_MODE_OFF; // CH2 transport is not implemented in this release
  _prefs.board_leds_enabled = constrain(_prefs.board_leds_enabled, 0, 1);
  meshcoreSetBoardLedsEnabled(_prefs.board_leds_enabled != 0);
  _prefs.adc_multiplier = constrain(_prefs.adc_multiplier, 0.0f, 20000.0f);
  _prefs.low_battery_shutdown_enabled = constrain(_prefs.low_battery_shutdown_enabled, 0, 1);
  _prefs.notify_mode &= NOTIFY_MODE_ALL;
#ifdef PIN_MSG_ALERT
  if (_prefs.notify_gpio_pin < 0) _prefs.notify_gpio_pin = DEFAULT_NOTIFY_GPIO_PIN;
#else
  _prefs.notify_gpio_pin = -1;
#endif
#if defined(PIN_BUZZER) || defined(PIN_MSG_TONE) || defined(PIN_MSG_ALERT)
  if (_prefs.notify_tone_pin < 0) _prefs.notify_tone_pin = DEFAULT_NOTIFY_TONE_PIN;
#else
  _prefs.notify_tone_pin = -1;
#endif
  if (_prefs.notify_vibe_pin < -1) _prefs.notify_vibe_pin = DEFAULT_NOTIFY_VIBE_PIN;
  if (_prefs.notify_tone_id >= NOTIFY_TONE_COUNT) _prefs.notify_tone_id = DEFAULT_NOTIFY_TONE_ID;
  if (_prefs.notify_tone_volume == 0 || _prefs.notify_tone_volume > 10) {
    _prefs.notify_tone_volume = DEFAULT_NOTIFY_TONE_VOLUME;
  }
#if DEFAULT_NOTIFY_REPAIR_LEGACY
  bool notify_prefs_changed = false;
#ifdef PIN_MSG_ALERT
  // Early SmartUI builds stored the shared alert LED as the tone GPIO.  The
  // value is syntactically valid, so the normal range checks cannot repair it.
  notify_prefs_changed = migrateLegacyNotifyPins(
      _prefs, PIN_MSG_ALERT, DEFAULT_NOTIFY_GPIO_PIN, DEFAULT_NOTIFY_TONE_PIN,
      DEFAULT_NOTIFY_REPAIR_LEGACY);
#else
  if (_prefs.notify_pin_fix_version < DEFAULT_NOTIFY_REPAIR_LEGACY) {
    _prefs.notify_pin_fix_version = DEFAULT_NOTIFY_REPAIR_LEGACY;
    notify_prefs_changed = true;
  }
#endif
#endif
#if defined(UI_T096_PREMIUM_TFT)
  if (_prefs.ui_font < 5 || _prefs.ui_font > UI_FONT_PREF_MAX) _prefs.ui_font = 10;
#else
  _prefs.ui_font = constrain(_prefs.ui_font, 0, UI_FONT_PREF_MAX);
#endif
  _prefs.ui_theme = constrain(_prefs.ui_theme, 0, 6);
  _prefs.unread_led_enabled = constrain(_prefs.unread_led_enabled, 0, 1);
  _prefs.msg_popup_enabled = constrain(_prefs.msg_popup_enabled, 0, 1);
  _prefs.notifications_muted = constrain(_prefs.notifications_muted, 0, 1);
  _prefs.night_quiet_active = constrain(_prefs.night_quiet_active, 0, 1);
  if (_prefs.night_prompt_day > 100000UL) _prefs.night_prompt_day = 0;
  _prefs.ui_top_color = constrain(_prefs.ui_top_color, 0, 5);
  _prefs.ui_bottom_color = constrain(_prefs.ui_bottom_color, 0, 5);
  _prefs.backlight_timeout_idx = constrain(_prefs.backlight_timeout_idx, 0, 2);
  _prefs.offline_dm_led_enabled = constrain(_prefs.offline_dm_led_enabled, 0, 1);
  _prefs.ble_dm_led_enabled = constrain(_prefs.ble_dm_led_enabled, 0, 1);
  _prefs.notify_tone_bridge_enabled = constrain(_prefs.notify_tone_bridge_enabled, 0, 1);
  _prefs.notify_tone_8bit_enabled = constrain(_prefs.notify_tone_8bit_enabled, 0, 1);
  _prefs.notify_tone_high_drive_enabled = constrain(_prefs.notify_tone_high_drive_enabled, 0, 1);
  if (_prefs.notify_tone_resonance_hz < 1800 || _prefs.notify_tone_resonance_hz > 4200) {
    _prefs.notify_tone_resonance_hz = DEFAULT_NOTIFY_TONE_RESONANCE_HZ;
  }
  if (_prefs.notify_tone_dm_id >= NOTIFY_TONE_COUNT) _prefs.notify_tone_dm_id = _prefs.notify_tone_id;
  if (_prefs.notify_tone_mention_id >= NOTIFY_TONE_COUNT) _prefs.notify_tone_mention_id = _prefs.notify_tone_id;
  if (_prefs.notify_tone_system_id >= NOTIFY_TONE_COUNT) _prefs.notify_tone_system_id = _prefs.notify_tone_id;
#if defined(UI_SMART_B12_TONE_LIST) && UI_SMART_B12_TONE_LIST == 1
  _prefs.notify_tone_id = _prefs.notify_tone_system_id;
  _prefs.notify_tone_dm_id = _prefs.notify_tone_system_id;
  _prefs.notify_tone_mention_id = _prefs.notify_tone_system_id;
#endif
  if (_prefs.smart_profile_id > SMART_PROFILE_NIGHT) _prefs.smart_profile_id = SMART_PROFILE_CUSTOM;
  if (_prefs.favorite_setting_1 == 0 || _prefs.favorite_setting_1 > SMART_FAVORITE_MAX) {
    _prefs.favorite_setting_1 = SMART_FAVORITE_NOTIFY_MODE;
  }
  if (_prefs.favorite_setting_2 == 0 || _prefs.favorite_setting_2 > SMART_FAVORITE_MAX) {
    _prefs.favorite_setting_2 = SMART_FAVORITE_SYSTEM_TONE;
  }
  if (_prefs.favorite_setting_3 == 0 || _prefs.favorite_setting_3 > SMART_FAVORITE_MAX) {
    _prefs.favorite_setting_3 = SMART_FAVORITE_BLUETOOTH;
  }
#if !defined(UI_TONE_8BIT_PAGE) || UI_TONE_8BIT_PAGE != 1
  _prefs.notify_tone_8bit_enabled = 0;
#endif
#if !defined(UI_TONE_BRIDGE_PAGE) || UI_TONE_BRIDGE_PAGE != 1
  _prefs.notify_tone_bridge_enabled = 0;
#elif defined(DEFAULT_NOTIFY_TONE_PIN)
  if (_prefs.notify_tone_bridge_enabled) _prefs.notify_tone_pin = DEFAULT_NOTIFY_TONE_PIN;
#endif
#if !defined(UI_TONE_HIGH_DRIVE_PAGE) || UI_TONE_HIGH_DRIVE_PAGE != 1
  _prefs.notify_tone_high_drive_enabled = 0;
#endif
  _prefs.important_notify_mode &= NOTIFY_MODE_ALL;

#if DEFAULT_NOTIFY_REPAIR_LEGACY
  // Persist the one-time GPIO repair immediately.  Otherwise the stale pin
  // remains in prefs.json until the user happens to change another setting.
  if (notify_prefs_changed) _store->savePrefs(_prefs);
#endif

#ifdef BLE_PIN_CODE // 123456 by default
  if (_prefs.ble_pin == 0) {
#ifdef DISPLAY_CLASS
    if (has_display && BLE_PIN_CODE == 123456) {
      StdRNG rng;
      _active_ble_pin = rng.nextInt(100000, 999999);
#if defined(BLE_PIN_PERSIST_RANDOM) && BLE_PIN_PERSIST_RANDOM
      // Generate a new passkey after an erase/factory reset, then keep it
      // stable across ordinary reboots so the printed UI value stays useful.
      _prefs.ble_pin = _active_ble_pin;
      _store->savePrefs(_prefs);
#endif
    } else {
      _active_ble_pin = BLE_PIN_CODE; // otherwise static pin
    }
#else
    _active_ble_pin = BLE_PIN_CODE; // otherwise static pin
#endif
  } else {
    _active_ble_pin = _prefs.ble_pin;
  }
#else
  _active_ble_pin = 0;
#endif

  resetContacts();
  _store->loadContacts(this);
  bootstrapRTCfromContacts();
  addChannel("Public", PUBLIC_GROUP_PSK); // pre-configure Andy's public channel
  _store->loadChannels(this);

  board.setAdcMultiplier(_prefs.adc_multiplier);
  radio_driver.setParams(_prefs.freq, _prefs.bw, _prefs.sf, _prefs.cr);
  radio_driver.setTxPower(_prefs.tx_power_dbm);
  radio_driver.setRxBoostedGainMode(_prefs.rx_boosted_gain);
  board.setLoRaFemLnaEnabled(_prefs.radio_fem_rxgain);
  board.setLoRaFemPaGainEnabled(_prefs.radio_fem_txgain);
  MESH_DEBUG_PRINTLN("RX Boosted Gain Mode: %s",
                     radio_driver.getRxBoostedGainMode() ? "Enabled" : "Disabled");
  applyCompanionRxPowerSaving(_prefs.sf, _prefs.bw);
  updateAutoAdvertTimer();
}

const char *MyMesh::getNodeName() {
  return _prefs.node_name;
}
NodePrefs *MyMesh::getNodePrefs() {
  return &_prefs;
}
uint32_t MyMesh::getBLEPin() {
  return _active_ble_pin;
}

uint16_t MyMesh::getAutoAdvertIntervalMins() const {
  return _prefs.auto_advert_interval_mins;
}

void MyMesh::updateAutoAdvertTimer() {
  if (_prefs.auto_advert_interval_mins > 0) {
    next_auto_advert = futureMillis((uint32_t)_prefs.auto_advert_interval_mins * 60UL * 1000UL);
  } else {
    next_auto_advert = 0;
  }
}

void MyMesh::cycleAutoAdvertInterval() {
  _prefs.auto_advert_interval_mins = nextAutoAdvertIntervalMins(_prefs.auto_advert_interval_mins);
  updateAutoAdvertTimer();
  savePrefs();
}

void MyMesh::applyUiPrefsRuntime() {
  board.setLoRaFemLnaEnabled(_prefs.radio_fem_rxgain != 0);
  board.setLoRaFemPaGainEnabled(_prefs.radio_fem_txgain != 0);
  radio_driver.setRxBoostedGainMode(_prefs.rx_boosted_gain != 0);
  meshcoreSetBoardLedsEnabled(_prefs.board_leds_enabled != 0);
  board.setAdcMultiplier(_prefs.adc_multiplier);
  updateAutoAdvertTimer();
}

bool MyMesh::isPhoneGpsFresh() const {
  return isPhoneGpsEnabled() && phone_gps_last_update_ms != 0 &&
         (unsigned long)(millis() - phone_gps_last_update_ms) <= PHONE_GPS_STALE_MS;
}

uint32_t MyMesh::getPhoneGpsAgeSeconds() const {
  if (phone_gps_last_update_ms == 0) return 0xFFFFFFFFUL;
  return (uint32_t)((unsigned long)(millis() - phone_gps_last_update_ms) / 1000UL);
}

const char* MyMesh::getGpsSourceName() const {
  return isPhoneGpsEnabled() ? "PHONE" : "HW";
}

void MyMesh::setGpsSource(uint8_t source, bool save) {
#if UI_PHONE_GPS == 1
  source = source == GPS_SOURCE_PHONE ? GPS_SOURCE_PHONE : GPS_SOURCE_HW;
#else
  source = GPS_SOURCE_HW;
#endif
  if (_prefs.gps_source == source) return;
  _prefs.gps_source = source;
  phone_gps_last_update_ms = 0;
#if ENV_INCLUDE_GPS == 1
  if (source == GPS_SOURCE_PHONE) {
    sensors.setSettingValue("gps", "0");
    _prefs.gps_enabled = 0;
  }
#endif
  if (save) savePrefs();
}

bool MyMesh::setPhoneGpsFix(int32_t lat, int32_t lon, int32_t alt) {
#if UI_PHONE_GPS != 1
  (void)lat;
  (void)lon;
  (void)alt;
  return false;
#else
  if (lat < -90000000L || lat > 90000000L || lon < -180000000L || lon > 180000000L) {
    return false;
  }
  if (!isPhoneGpsEnabled()) setGpsSource(GPS_SOURCE_PHONE, true);
  sensors.node_lat = ((double)lat) / 1000000.0;
  sensors.node_lon = ((double)lon) / 1000000.0;
  sensors.node_altitude = ((double)alt) / 1000.0;
  phone_gps_last_update_ms = millis();
  if (phone_gps_last_update_ms == 0) phone_gps_last_update_ms = 1;
  return true;
#endif
}

bool MyMesh::getShareableLocation(double& lat, double& lon, double& alt) const {
  if (isPhoneGpsEnabled() && !isPhoneGpsFresh()) return false;
  lat = sensors.node_lat;
  lon = sensors.node_lon;
  alt = sensors.node_altitude;
  return lat >= -90.0 && lat <= 90.0 && lon >= -180.0 && lon <= 180.0;
}

struct FreqRange {
  uint32_t lower_freq, upper_freq;
};

static FreqRange repeat_freq_ranges[] = {
  #ifdef ALLOWED_REPEAT_FREQ_RANGE
  ALLOWED_REPEAT_FREQ_RANGE
  #else
  { 433000, 433000 },
  { 869495, 869495 },
  { 918000, 918000 }
  #endif
};

bool MyMesh::isValidClientRepeatFreq(uint32_t f) const {
  for (int i = 0; i < sizeof(repeat_freq_ranges)/sizeof(repeat_freq_ranges[0]); i++) {
    auto r = &repeat_freq_ranges[i];
    if (f >= r->lower_freq && f <= r->upper_freq) return true;
  }
  return false;
}

void MyMesh::startInterface(BaseSerialInterface &serial) {
  _serial = &serial;
  serial.enable();
}

void MyMesh::handleCmdFrame(size_t len) {
  if (cmd_frame[0] == CMD_DEVICE_QUERY && len >= 2) { // sent when app establishes connection
    app_target_ver = cmd_frame[1];                    // which version of protocol does app understand

    int i = 0;
    out_frame[i++] = RESP_CODE_DEVICE_INFO;
    out_frame[i++] = FIRMWARE_VER_CODE;
    out_frame[i++] = MAX_CONTACTS / 2;   // v3+
    out_frame[i++] = MAX_GROUP_CHANNELS; // v3+
    memcpy(&out_frame[i], &_prefs.ble_pin, 4);
    i += 4;
    memset(&out_frame[i], 0, 12);
    strcpy((char *)&out_frame[i], FIRMWARE_BUILD_DATE);
    i += 12;
    StrHelper::strzcpy((char *)&out_frame[i], board.getManufacturerName(), 40);
    i += 40;
    StrHelper::strzcpy((char *)&out_frame[i], FIRMWARE_VERSION, 20);
    i += 20;
    out_frame[i++] = _prefs.isRepeatEn() ? 1 : 0;   // v9+
    out_frame[i++] = _prefs.path_hash_mode;  // v10+
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_APP_START &&
             len >= 8) { // sent when app establishes connection, respond with node ID
    //  cmd_frame[1..7]  reserved future
    char *app_name = (char *)&cmd_frame[8];
    cmd_frame[len] = 0; // make app_name null terminated
    MESH_DEBUG_PRINTLN("App %s connected", app_name);

    _iter_started = false; // stop any left-over ContactsIterator
    int i = 0;
    out_frame[i++] = RESP_CODE_SELF_INFO;
    out_frame[i++] = ADV_TYPE_CHAT; // what this node Advert identifies as (maybe node's pronouns too?? :-)
    out_frame[i++] = _prefs.tx_power_dbm;
    out_frame[i++] = MAX_LORA_TX_POWER;
    memcpy(&out_frame[i], self_id.pub_key, PUB_KEY_SIZE);
    i += PUB_KEY_SIZE;

    int32_t lat, lon;
    lat = (sensors.node_lat * 1000000.0);
    lon = (sensors.node_lon * 1000000.0);
    memcpy(&out_frame[i], &lat, 4);
    i += 4;
    memcpy(&out_frame[i], &lon, 4);
    i += 4;
    out_frame[i++] = _prefs.multi_acks; // new v7+
    out_frame[i++] = _prefs.advert_loc_policy;
    out_frame[i++] = (_prefs.telemetry_mode_env << 4) | (_prefs.telemetry_mode_loc << 2) |
                     (_prefs.telemetry_mode_base); // v5+
    out_frame[i++] = _prefs.manual_add_contacts;

    uint32_t freq = _prefs.freq * 1000;
    memcpy(&out_frame[i], &freq, 4);
    i += 4;
    uint32_t bw = _prefs.bw * 1000;
    memcpy(&out_frame[i], &bw, 4);
    i += 4;
    out_frame[i++] = _prefs.sf;
    out_frame[i++] = _prefs.cr;

    int tlen = strlen(_prefs.node_name); // revisit: UTF_8 ??
    memcpy(&out_frame[i], _prefs.node_name, tlen);
    i += tlen;
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_SEND_TXT_MSG && len >= 14) {
    int i = 1;
    uint8_t txt_type = cmd_frame[i++];
    uint8_t attempt = cmd_frame[i++];
    uint32_t msg_timestamp;
    memcpy(&msg_timestamp, &cmd_frame[i], 4);
    i += 4;
    uint8_t *pub_key_prefix = &cmd_frame[i];
    i += 6;
    ContactInfo *recipient = lookupContactByPubKey(pub_key_prefix, 6);
    if (recipient && (txt_type == TXT_TYPE_PLAIN || txt_type == TXT_TYPE_CLI_DATA)) {
      char *text = (char *)&cmd_frame[i];
      int tlen = len - i;
      uint32_t est_timeout;
      text[tlen] = 0; // ensure null
      int result;
      uint32_t expected_ack;
      if (txt_type == TXT_TYPE_CLI_DATA) {
        msg_timestamp = getRTCClock()->getCurrentTimeUnique(); // Use node's RTC instead of app timestamp to avoid tripping replay protection
        result = sendCommandData(*recipient, msg_timestamp, attempt, text, est_timeout);
        expected_ack = 0; // no Ack expected
      } else {
        result = sendMessage(*recipient, msg_timestamp, attempt, text, expected_ack, est_timeout);
      }
      // TODO: add expected ACK to table
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        if (expected_ack) {
          expected_ack_table[next_ack_idx].msg_sent = _ms->getMillis(); // add to circular table
          expected_ack_table[next_ack_idx].ack = expected_ack;
          expected_ack_table[next_ack_idx].contact = recipient;
          next_ack_idx = (next_ack_idx + 1) % EXPECTED_ACK_TABLE_SIZE;
        }

        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &expected_ack, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(recipient == NULL
                        ? ERR_CODE_NOT_FOUND
                        : ERR_CODE_UNSUPPORTED_CMD); // unknown recipient, or unsupported TXT_TYPE_*
    }
  } else if (cmd_frame[0] == CMD_SEND_CHANNEL_TXT_MSG) { // send GroupChannel text msg
    int i = 1;
    uint8_t txt_type = cmd_frame[i++]; // should be TXT_TYPE_PLAIN
    uint8_t channel_idx = cmd_frame[i++];
    uint32_t msg_timestamp;
    memcpy(&msg_timestamp, &cmd_frame[i], 4);
    i += 4;
    const char *text = (char *)&cmd_frame[i];

    if (txt_type != TXT_TYPE_PLAIN) {
      writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);
    } else {
      ChannelDetails channel;
      bool success = getChannel(channel_idx, channel);
      if (success && sendGroupMessage(msg_timestamp, channel.channel, _prefs.node_name, text, len - i)) {
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_NOT_FOUND); // bad channel_idx
      }
    }
  } else if (cmd_frame[0] == CMD_SEND_CHANNEL_DATA) { // send GroupChannel datagram
    if (len < 4) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      return;
    }
    int i = 1;
    uint8_t channel_idx = cmd_frame[i++];
    uint8_t path_len = cmd_frame[i++];

    // validate path len, allowing 0xFF for flood
    if (!mesh::Packet::isValidPathLen(path_len) && path_len != OUT_PATH_UNKNOWN) {
      MESH_DEBUG_PRINTLN("CMD_SEND_CHANNEL_DATA invalid path size: %d", path_len);
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      return;
    }

    // parse provided path if not flood
    uint8_t path[MAX_PATH_SIZE];
    if (path_len != OUT_PATH_UNKNOWN) {
      i += mesh::Packet::writePath(path, &cmd_frame[i], path_len);
    }

    uint16_t data_type = ((uint16_t)cmd_frame[i]) | (((uint16_t)cmd_frame[i + 1]) << 8);
    i += 2;
    const uint8_t *payload = &cmd_frame[i];
    int payload_len = (len > (size_t)i) ? (int)(len - i) : 0;

    ChannelDetails channel;
    if (!getChannel(channel_idx, channel)) {
      writeErrFrame(ERR_CODE_NOT_FOUND); // bad channel_idx
    } else if (data_type == DATA_TYPE_RESERVED) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else if (payload_len > MAX_CHANNEL_DATA_LENGTH) {
      MESH_DEBUG_PRINTLN("CMD_SEND_CHANNEL_DATA payload too long: %d > %d", payload_len, MAX_CHANNEL_DATA_LENGTH);
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else if (sendGroupData(channel.channel, path, path_len, data_type, payload, payload_len)) {
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_TABLE_FULL);
    }
  } else if (cmd_frame[0] == CMD_GET_CONTACTS) { // get Contact list
    if (_iter_started) {
      writeErrFrame(ERR_CODE_BAD_STATE); // iterator is currently busy
    } else {
      if (len >= 5) { // has optional 'since' param
        memcpy(&_iter_filter_since, &cmd_frame[1], 4);
      } else {
        _iter_filter_since = 0;
      }

      uint8_t reply[5];
      reply[0] = RESP_CODE_CONTACTS_START;
      uint32_t count = getNumContacts(); // total, NOT filtered count
      memcpy(&reply[1], &count, 4);
      _serial->writeFrame(reply, 5);

      // start iterator
      _iter = startContactsIterator();
      _iter_started = true;
      _most_recent_lastmod = 0;
    }
  } else if (cmd_frame[0] == CMD_SET_ADVERT_NAME && len >= 2) {
    int nlen = len - 1;
    if (nlen > sizeof(_prefs.node_name) - 1) nlen = sizeof(_prefs.node_name) - 1; // max len
    memcpy(_prefs.node_name, &cmd_frame[1], nlen);
    _prefs.node_name[nlen] = 0; // null terminator
    savePrefs();
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_SET_ADVERT_LATLON && len >= 9) {
    int32_t lat, lon, alt = 0;
    memcpy(&lat, &cmd_frame[1], 4);
    memcpy(&lon, &cmd_frame[5], 4);
    if (len >= 13) {
      memcpy(&alt, &cmd_frame[9], 4); // for FUTURE support
    }
    if (lat <= 90 * 1E6 && lat >= -90 * 1E6 && lon <= 180 * 1E6 && lon >= -180 * 1E6) {
      sensors.node_lat = ((double)lat) / 1000000.0;
      sensors.node_lon = ((double)lon) / 1000000.0;
      savePrefs();
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG); // invalid geo coordinate
    }
  } else if (cmd_frame[0] == CMD_SET_PHONE_GPS) {
#if UI_PHONE_GPS == 1
    if (len < 9) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else {
      int32_t lat, lon, alt = 0;
      memcpy(&lat, &cmd_frame[1], 4);
      memcpy(&lon, &cmd_frame[5], 4);
      if (len >= 13) memcpy(&alt, &cmd_frame[9], 4);
      if (setPhoneGpsFix(lat, lon, alt)) {
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      }
    }
#else
    writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);
#endif
  } else if (cmd_frame[0] == CMD_GET_DEVICE_TIME) {
    uint8_t reply[5];
    reply[0] = RESP_CODE_CURR_TIME;
    uint32_t now = getRTCClock()->getCurrentTime();
    memcpy(&reply[1], &now, 4);
    _serial->writeFrame(reply, 5);
  } else if (cmd_frame[0] == CMD_SET_DEVICE_TIME && len >= 5) {
    uint32_t secs;
    memcpy(&secs, &cmd_frame[1], 4);
    mesh::RTCClock* rtc = getRTCClock();
    uint32_t curr = rtc->getCurrentTime();
    bool backward = secs < curr;
    bool sane_time = secs >= BLE_TIME_SYNC_MIN_UNIX && secs <= BLE_TIME_SYNC_MAX_UNIX;
    if (sane_time && (!backward || BLE_TIME_SYNC_ACCEPT_BACKWARD)) {
      if (backward) {
        rtc->setCurrentTimeAndRebaseUnique(secs);
      } else {
        rtc->setCurrentTime(secs);
      }
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    }
  } else if (cmd_frame[0] == CMD_SEND_SELF_ADVERT) {
    mesh::Packet* pkt;
    if (_prefs.advert_loc_policy == ADVERT_LOC_NONE) {
      pkt = createSelfAdvert(_prefs.node_name);
    } else {
      pkt = createSelfAdvert(_prefs.node_name, sensors.node_lat, sensors.node_lon);
    }
    if (pkt) {
      if (len >= 2 && cmd_frame[1] == 1) { // optional param (1 = flood, 0 = zero hop)
        unsigned long delay_millis = 0;
        TransportKey default_scope;
        memcpy(&default_scope.key, _prefs.default_scope_key, sizeof(default_scope.key));
        sendFloodScoped(default_scope, pkt, delay_millis);
      } else {
        sendZeroHop(pkt);
      }
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_TABLE_FULL);
    }
  } else if (cmd_frame[0] == CMD_RESET_PATH && len >= 1 + 32) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      recipient->out_path_len = OUT_PATH_UNKNOWN;
      // recipient->lastmod = ??   shouldn't be needed, app already has this version of contact
      dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // unknown contact
    }
  } else if (cmd_frame[0] == CMD_ADD_UPDATE_CONTACT && len >= 1 + 32 + 2 + 1) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    uint32_t last_mod = getRTCClock()->getCurrentTime();  // fallback value if not present in cmd_frame
    if (recipient) {
      updateContactFromFrame(*recipient, last_mod, cmd_frame, len);
      recipient->lastmod = last_mod;
      dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
      writeOKFrame();
    } else {
      ContactInfo contact;
      updateContactFromFrame(contact, last_mod, cmd_frame, len);
      contact.lastmod = last_mod;
      contact.sync_since = 0;
      if (addContact(contact)) {
        dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      }
    }
  } else if (cmd_frame[0] == CMD_REMOVE_CONTACT) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient && removeContact(*recipient)) {
      _store->deleteBlobByKey(pub_key, PUB_KEY_SIZE);
      dirty_contacts_expiry = futureMillis(LAZY_CONTACTS_WRITE_DELAY);
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // not found, or unable to remove
    }
  } else if (cmd_frame[0] == CMD_SHARE_CONTACT) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      if (shareContactZeroHop(*recipient)) {
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_TABLE_FULL); // unable to send
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND);
    }
  } else if (cmd_frame[0] == CMD_GET_CONTACT_BY_KEY) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *contact = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (contact) {
      writeContactRespFrame(RESP_CODE_CONTACT, *contact);
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // not found
    }
  } else if (cmd_frame[0] == CMD_EXPORT_CONTACT) {
    if (len < 1 + PUB_KEY_SIZE) {
      // export SELF
      mesh::Packet* pkt;
      if (_prefs.advert_loc_policy == ADVERT_LOC_NONE) {
        pkt = createSelfAdvert(_prefs.node_name);
      } else {
        pkt = createSelfAdvert(_prefs.node_name, sensors.node_lat, sensors.node_lon);
      }
      if (pkt) {
        pkt->header |= ROUTE_TYPE_FLOOD; // would normally be sent in this mode

        out_frame[0] = RESP_CODE_EXPORT_CONTACT;
        uint8_t out_len = pkt->writeTo(&out_frame[1]);
        releasePacket(pkt); // undo the obtainNewPacket()
        _serial->writeFrame(out_frame, out_len + 1);
      } else {
        writeErrFrame(ERR_CODE_TABLE_FULL); // Error
      }
    } else {
      uint8_t *pub_key = &cmd_frame[1];
      ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
      uint8_t out_len;
      if (recipient && (out_len = exportContact(*recipient, &out_frame[1])) > 0) {
        out_frame[0] = RESP_CODE_EXPORT_CONTACT;
        _serial->writeFrame(out_frame, out_len + 1);
      } else {
        writeErrFrame(ERR_CODE_NOT_FOUND); // not found
      }
    }
  } else if (cmd_frame[0] == CMD_IMPORT_CONTACT && len > 2 + 32 + 64) {
    if (importContact(&cmd_frame[1], len - 1)) {
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    }
  } else if (cmd_frame[0] == CMD_SYNC_NEXT_MESSAGE) {
    int out_len;
    bool direct_text_read = offline_queue_len > 0 && offline_queue[0].isDisplayableDirectMsg();
    if ((out_len = getFromOfflineQueue(out_frame)) > 0) {
      _serial->writeFrame(out_frame, out_len);
#ifdef DISPLAY_CLASS
      if (_ui) {
        // A BLE dequeue is not the same as dismissing the local notification.
        _ui->msgRead(offline_queue_len, false);
        if (direct_text_read) _ui->directMsgRead(false);
      }
#endif
    } else {
      out_frame[0] = RESP_CODE_NO_MORE_MESSAGES;
      _serial->writeFrame(out_frame, 1);
    }
  } else if (cmd_frame[0] == CMD_SET_RADIO_PARAMS) {
    int i = 1;
    uint32_t freq;
    memcpy(&freq, &cmd_frame[i], 4);
    i += 4;
    uint32_t bw;
    memcpy(&bw, &cmd_frame[i], 4);
    i += 4;
    uint8_t sf = cmd_frame[i++];
    uint8_t cr = cmd_frame[i++];
    uint8_t repeat = 0;  // default - false
    if (len > i) {
      repeat = cmd_frame[i++];   // FIRMWARE_VER_CODE  9+
    }

    if (repeat && !isValidClientRepeatFreq(freq)) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else if (freq >= 150000 && freq <= 2500000 && sf >= 5 && sf <= 12 && cr >= 5 && cr <= 8 && bw >= 7000 &&
        bw <= 500000) {
      _prefs.sf = sf;
      _prefs.cr = cr;
      _prefs.freq = (float)freq / 1000.0;
      _prefs.bw = (float)bw / 1000.0;
      _prefs.setRepeatEn(repeat != 0);
      savePrefs();

      radio_driver.setParams(_prefs.freq, _prefs.bw, _prefs.sf, _prefs.cr);
      applyCompanionRxPowerSaving(_prefs.sf, _prefs.bw);
      MESH_DEBUG_PRINTLN("OK: CMD_SET_RADIO_PARAMS: f=%d, bw=%d, sf=%d, cr=%d", freq, bw, (uint32_t)sf,
                         (uint32_t)cr);

      writeOKFrame();
    } else {
      MESH_DEBUG_PRINTLN("Error: CMD_SET_RADIO_PARAMS: f=%d, bw=%d, sf=%d, cr=%d", freq, bw, (uint32_t)sf,
                         (uint32_t)cr);
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    }
  } else if (cmd_frame[0] == CMD_SET_RADIO_TX_POWER) {
    int8_t power = (int8_t)cmd_frame[1];
    if (power < -9 || power > MAX_LORA_TX_POWER) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else {
      _prefs.tx_power_dbm = power;
      savePrefs();
      radio_driver.setTxPower(_prefs.tx_power_dbm);
      writeOKFrame();
    }
  } else if (cmd_frame[0] == CMD_SET_TUNING_PARAMS) {
    int i = 1;
    uint32_t rx, af;
    memcpy(&rx, &cmd_frame[i], 4);
    i += 4;
    memcpy(&af, &cmd_frame[i], 4);
    i += 4;
    _prefs.rx_delay_base = ((float)rx) / 1000.0f;
    _prefs.airtime_factor = ((float)af) / 1000.0f;
    savePrefs();
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_GET_TUNING_PARAMS) {
    uint32_t rx = _prefs.rx_delay_base * 1000, af = _prefs.airtime_factor * 1000;
    int i = 0;
    out_frame[i++] = RESP_CODE_TUNING_PARAMS;
    memcpy(&out_frame[i], &rx, 4); i += 4;
    memcpy(&out_frame[i], &af, 4); i += 4;
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_SET_OTHER_PARAMS) {
    _prefs.manual_add_contacts = cmd_frame[1];
    if (len >= 3) {
      _prefs.telemetry_mode_base = cmd_frame[2] & 0x03; // v5+
      _prefs.telemetry_mode_loc = (cmd_frame[2] >> 2) & 0x03;
      _prefs.telemetry_mode_env = (cmd_frame[2] >> 4) & 0x03;

      if (len >= 4) {
        _prefs.advert_loc_policy = cmd_frame[3];
        if (len >= 5) {
          _prefs.multi_acks = cmd_frame[4];
        }
      }
    }
    savePrefs();
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_SET_PATH_HASH_MODE && cmd_frame[1] == 0 && len >= 3) {
    if (cmd_frame[2] >= 3) {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else {
      _prefs.path_hash_mode = cmd_frame[2];
      savePrefs();
      writeOKFrame();
    }
  } else if (cmd_frame[0] == CMD_REBOOT && memcmp(&cmd_frame[1], "reboot", 6) == 0) {
    if (dirty_contacts_expiry) { // is there are pending dirty contacts write needed?
      saveContacts();
    }
    board.reboot();
  } else if (cmd_frame[0] == CMD_GET_BATT_AND_STORAGE) {
    uint8_t reply[11];
    int i = 0;
    reply[i++] = RESP_CODE_BATT_AND_STORAGE;
    uint16_t battery_millivolts = board.getBattMilliVolts();
    uint32_t used = _store->getStorageUsedKb();
    uint32_t total = _store->getStorageTotalKb();
    memcpy(&reply[i], &battery_millivolts, 2); i += 2;
    memcpy(&reply[i], &used, 4); i += 4;
    memcpy(&reply[i], &total, 4); i += 4;
    _serial->writeFrame(reply, i);
  } else if (cmd_frame[0] == CMD_EXPORT_PRIVATE_KEY) {
#if ENABLE_PRIVATE_KEY_EXPORT
    uint8_t reply[65];
    reply[0] = RESP_CODE_PRIVATE_KEY;
    self_id.writeTo(&reply[1], 64);
    _serial->writeFrame(reply, 65);
#else
    writeDisabledFrame();
#endif
  } else if (cmd_frame[0] == CMD_IMPORT_PRIVATE_KEY && len >= 65) {
#if ENABLE_PRIVATE_KEY_IMPORT
    if (!mesh::LocalIdentity::validatePrivateKey(&cmd_frame[1])) {
        writeErrFrame(ERR_CODE_ILLEGAL_ARG); // invalid key
    } else {
        mesh::LocalIdentity identity;
        identity.readFrom(&cmd_frame[1], 64);
        if (_store->saveMainIdentity(identity)) {
          self_id = identity;
          writeOKFrame();
          // re-load contacts, to invalidate ecdh shared_secrets
          resetContacts();
          _store->loadContacts(this);
        } else {
          writeErrFrame(ERR_CODE_FILE_IO_ERROR);
        }
    }
#else
    writeDisabledFrame();
#endif
  } else if (cmd_frame[0] == CMD_SEND_RAW_DATA && len >= 6) {
    int i = 1;
    int8_t path_len = cmd_frame[i++];
    if (path_len >= 0 && i + path_len + 4 <= len) { // minimum 4 byte payload
      uint8_t *path = &cmd_frame[i];
      i += path_len;
      auto pkt = createRawData(&cmd_frame[i], len - i);
      if (pkt) {
        sendDirect(pkt, path, path_len);
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      }
    } else {
      writeErrFrame(ERR_CODE_UNSUPPORTED_CMD); // flood, not supported (yet)
    }
  } else if (cmd_frame[0] == CMD_SEND_LOGIN && len >= 1 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    char *password = (char *)&cmd_frame[1 + PUB_KEY_SIZE];
    cmd_frame[len] = 0; // ensure null terminator in password
    if (recipient) {
      uint32_t est_timeout;
      int result = sendLogin(*recipient, password, est_timeout);
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        memcpy(&pending_login, recipient->id.pub_key, 4); // match this to onContactResponse()
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &pending_login, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // contact not found
    }
  } else if (cmd_frame[0] == CMD_SEND_ANON_REQ && len > 1 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    ContactInfo anon;
    if (recipient == NULL) { // FIRMWARE_VER_CODE 13+,  allow non-contact requests
      memset(&anon, 0, sizeof(anon));
      memcpy(anon.id.pub_key, pub_key, PUB_KEY_SIZE);
      anon.out_path_len = 0;   // default to zero-hop direct
      anon.type = ADV_TYPE_NONE;  // unknown
      anon.lastmod = getRTCClock()->getCurrentTime();

      if (addContact(anon)) recipient = &anon;
    }
    uint8_t *data = &cmd_frame[1 + PUB_KEY_SIZE];
    if (recipient) {
      uint32_t tag, est_timeout;
      int result = sendAnonReq(*recipient, data, len - (1 + PUB_KEY_SIZE), tag, est_timeout);
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        pending_req = tag; // match this to onContactResponse()
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_TABLE_FULL); // contacts full
    }
  } else if (cmd_frame[0] == CMD_SEND_STATUS_REQ && len >= 1 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      uint32_t tag, est_timeout;
      int result = sendRequest(*recipient, REQ_TYPE_GET_STATUS, tag, est_timeout);
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        // FUTURE:  pending_status = tag;  // match this in onContactResponse()
        memcpy(&pending_status, recipient->id.pub_key, 4); // legacy matching scheme
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // contact not found
    }
  } else if (cmd_frame[0] == CMD_SEND_PATH_DISCOVERY_REQ && cmd_frame[1] == 0 && len >= 2 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[2];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      uint32_t tag, est_timeout;
      // 'Path Discovery' is just a special case of flood + Telemetry req
      uint8_t req_data[9];
      req_data[0] = REQ_TYPE_GET_TELEMETRY_DATA;
      req_data[1] = ~(TELEM_PERM_BASE);  // NEW: inverse permissions mask (ie. we only want BASE telemetry)
      memset(&req_data[2], 0, 3);  // reserved
      getRNG()->random(&req_data[5], 4);   // random blob to help make packet-hash unique
      auto save = recipient->out_path_len;    // temporarily force sendRequest() to flood
      recipient->out_path_len = OUT_PATH_UNKNOWN;
      int result = sendRequest(*recipient, req_data, sizeof(req_data), tag, est_timeout);
      recipient->out_path_len = save;
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        pending_discovery = tag; // match this in onContactResponse()
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // contact not found
    }
  } else if (cmd_frame[0] == CMD_SEND_TELEMETRY_REQ && len >= 4 + PUB_KEY_SIZE) {  // can deprecate, in favour of CMD_SEND_BINARY_REQ
    uint8_t *pub_key = &cmd_frame[4];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      uint32_t tag, est_timeout;
      int result = sendRequest(*recipient, REQ_TYPE_GET_TELEMETRY_DATA, tag, est_timeout);
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        pending_telemetry = tag; // match this in onContactResponse()
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // contact not found
    }
  } else if (cmd_frame[0] == CMD_SEND_TELEMETRY_REQ && len == 4) {  // 'self' telemetry request
    telemetry.reset();
    telemetry.addVoltage(TELEM_CHANNEL_SELF, (float)board.getBattMilliVolts() / 1000.0f);
    float temperature = board.getMCUTemperature();
    if(!isnan(temperature)) { // Supported boards with built-in temperature sensor. ESP32-C3 may return NAN
      telemetry.addTemperature(TELEM_CHANNEL_SELF, temperature); // Built-in MCU Temperature
    }

    // query other sensors -- target specific
    sensors.querySensors(0xFF, telemetry);

    int i = 0;
    out_frame[i++] = PUSH_CODE_TELEMETRY_RESPONSE;
    out_frame[i++] = 0; // reserved
    memcpy(&out_frame[i], self_id.pub_key, 6);
    i += 6; // pub_key_prefix
    uint8_t tlen = telemetry.getSize();
    memcpy(&out_frame[i], telemetry.getBuffer(), tlen);
    i += tlen;
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_SEND_BINARY_REQ && len >= 2 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    ContactInfo *recipient = lookupContactByPubKey(pub_key, PUB_KEY_SIZE);
    if (recipient) {
      uint8_t *req_data = &cmd_frame[1 + PUB_KEY_SIZE];
      uint32_t tag, est_timeout;
      int result = sendRequest(*recipient, req_data, len - (1 + PUB_KEY_SIZE), tag, est_timeout);
      if (result == MSG_SEND_FAILED) {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      } else {
        clearPendingReqs();
        pending_req = tag; // match this in onContactResponse()
        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = (result == MSG_SEND_SENT_FLOOD) ? 1 : 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      }
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // contact not found
    }
  } else if (cmd_frame[0] == CMD_HAS_CONNECTION && len >= 1 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    if (hasConnectionTo(pub_key)) {
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND);
    }
  } else if (cmd_frame[0] == CMD_LOGOUT && len >= 1 + PUB_KEY_SIZE) {
    uint8_t *pub_key = &cmd_frame[1];
    stopConnection(pub_key);
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_GET_CHANNEL && len >= 2) {
    uint8_t channel_idx = cmd_frame[1];
    ChannelDetails channel;
    if (getChannel(channel_idx, channel)) {
      int i = 0;
      out_frame[i++] = RESP_CODE_CHANNEL_INFO;
      out_frame[i++] = channel_idx;
      strcpy((char *)&out_frame[i], channel.name);
      i += 32;
      memcpy(&out_frame[i], channel.channel.secret, 16);
      i += 16; // NOTE: only 128-bit supported
      _serial->writeFrame(out_frame, i);
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND);
    }
  } else if (cmd_frame[0] == CMD_SET_CHANNEL && len >= 2 + 32 + 32) {
    writeErrFrame(ERR_CODE_UNSUPPORTED_CMD); // not supported (yet)
  } else if (cmd_frame[0] == CMD_SET_CHANNEL && len >= 2 + 32 + 16) {
    uint8_t channel_idx = cmd_frame[1];
    ChannelDetails channel;
    StrHelper::strncpy(channel.name, (char *)&cmd_frame[2], 32);
    memset(channel.channel.secret, 0, sizeof(channel.channel.secret));
    memcpy(channel.channel.secret, &cmd_frame[2 + 32], 16); // NOTE: only 128-bit supported
    if (setChannel(channel_idx, channel)) {
      saveChannels();
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND); // bad channel_idx
    }
  } else if (cmd_frame[0] == CMD_SIGN_START) {
    out_frame[0] = RESP_CODE_SIGN_START;
    out_frame[1] = 0; // reserved
    uint32_t len = MAX_SIGN_DATA_LEN;
    memcpy(&out_frame[2], &len, 4);
    _serial->writeFrame(out_frame, 6);

    if (sign_data) {
      free(sign_data);
    }
    sign_data = (uint8_t *)malloc(MAX_SIGN_DATA_LEN);
    sign_data_len = 0;
  } else if (cmd_frame[0] == CMD_SIGN_DATA && len > 1) {
    if (sign_data == NULL || sign_data_len + (len - 1) > MAX_SIGN_DATA_LEN) {
      writeErrFrame(sign_data == NULL ? ERR_CODE_BAD_STATE : ERR_CODE_TABLE_FULL); // error: too long
    } else {
      memcpy(&sign_data[sign_data_len], &cmd_frame[1], len - 1);
      sign_data_len += (len - 1);
      writeOKFrame();
    }
  } else if (cmd_frame[0] == CMD_SIGN_FINISH) {
    if (sign_data) {
      self_id.sign(&out_frame[1], sign_data, sign_data_len);

      free(sign_data); // don't need sign_data now
      sign_data = NULL;

      out_frame[0] = RESP_CODE_SIGNATURE;
      _serial->writeFrame(out_frame, 1 + SIGNATURE_SIZE);
    } else {
      writeErrFrame(ERR_CODE_BAD_STATE);
    }
  } else if (cmd_frame[0] == CMD_SEND_TRACE_PATH && len > 10 && len - 10 < MAX_PACKET_PAYLOAD-5) {
    uint8_t path_len = len - 10;
    uint8_t flags = cmd_frame[9];
    uint8_t path_sz = flags & 0x03;  // NEW v1.11+
    if ((path_len >> path_sz) > MAX_PATH_SIZE || (path_len % (1 << path_sz)) != 0) { // make sure is multiple of path_sz
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    } else {
      uint32_t tag, auth;
      memcpy(&tag, &cmd_frame[1], 4);
      memcpy(&auth, &cmd_frame[5], 4);
      auto pkt = createTrace(tag, auth, flags);
      if (pkt) {
        sendDirect(pkt, &cmd_frame[10], path_len);

        uint32_t t = _radio->getEstAirtimeFor(pkt->payload_len + pkt->path_len + 2);
        uint32_t est_timeout = calcDirectTimeoutMillisFor(t, path_len >> path_sz);

        out_frame[0] = RESP_CODE_SENT;
        out_frame[1] = 0;
        memcpy(&out_frame[2], &tag, 4);
        memcpy(&out_frame[6], &est_timeout, 4);
        _serial->writeFrame(out_frame, 10);
      } else {
        writeErrFrame(ERR_CODE_TABLE_FULL);
      }
    }
  } else if (cmd_frame[0] == CMD_SET_DEVICE_PIN && len >= 5) {

    // get pin from command frame
    uint32_t pin;
    memcpy(&pin, &cmd_frame[1], 4);

    // ensure pin is zero, or a valid 6 digit pin
    if (pin == 0 || (pin >= 100000 && pin <= 999999)) {
      _prefs.ble_pin = pin;
      savePrefs();
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    }
  } else if (cmd_frame[0] == CMD_GET_CUSTOM_VARS) {
    out_frame[0] = RESP_CODE_CUSTOM_VARS;
    char *dp = (char *)&out_frame[1];
#if UI_PHONE_GPS == 1
    if (dp != (char *)&out_frame[1]) *dp++ = ',';
    strcpy(dp, isPhoneGpsEnabled() ? "gps_source:PHONE,phone_gps:" : "gps_source:HW,phone_gps:OFF");
    dp = strchr(dp, 0);
    if (isPhoneGpsEnabled()) {
      strcpy(dp, isPhoneGpsFresh() ? "FRESH" :
             (phone_gps_last_update_ms == 0 ? "WAIT" : "STALE"));
      dp = strchr(dp, 0);
    }
#endif
    for (int i = 0; i < sensors.getNumSettings() && dp - (char *)&out_frame[1] < 140; i++) {
      if (dp != (char *)&out_frame[1]) {
        *dp++ = ',';
      }
      strcpy(dp, sensors.getSettingName(i));
      dp = strchr(dp, 0);
      *dp++ = ':';
      strcpy(dp, sensors.getSettingValue(i));
      dp = strchr(dp, 0);
    }
    _serial->writeFrame(out_frame, dp - (char *)out_frame);
  } else if (cmd_frame[0] == CMD_SET_CUSTOM_VAR && len >= 4) {
    cmd_frame[len] = 0;
    char *sp = (char *)&cmd_frame[1];
    char *np = strchr(sp, ':'); // look for separator char
    if (np) {
      *np++ = 0; // modify 'cmd_frame', replace ':' with null
      bool success = false;
      if (strcmp(sp, "gps_source") == 0) {
#if UI_PHONE_GPS == 1
        if (strcmp(np, "PHONE") == 0 || strcmp(np, "phone") == 0 || strcmp(np, "1") == 0) {
          setGpsSource(GPS_SOURCE_PHONE);
          success = true;
        } else if (strcmp(np, "HW") == 0 || strcmp(np, "hw") == 0 || strcmp(np, "0") == 0) {
          setGpsSource(GPS_SOURCE_HW);
          success = true;
        }
#else
        // Keep compatibility with an explicit HW reset, but reject PHONE.
        if (strcmp(np, "HW") == 0 || strcmp(np, "hw") == 0 || strcmp(np, "0") == 0) {
          setGpsSource(GPS_SOURCE_HW);
          success = true;
        }
#endif
      } else {
        success = sensors.setSettingValue(sp, np);
      }
      if (success) {
        #if ENV_INCLUDE_GPS == 1
        // Update node preferences for GPS settings
        if (strcmp(sp, "gps") == 0) {
          if (np[0] == '1') setGpsSource(GPS_SOURCE_HW, false);
          _prefs.gps_enabled = (np[0] == '1') ? 1 : 0;
          savePrefs();
        } else if (strcmp(sp, "gps_interval") == 0) {
          uint32_t interval_seconds = atoi(np);
          _prefs.gps_interval = constrain(interval_seconds, 0, 86400);
          savePrefs();
        }
        #endif
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      }
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG);
    }
  } else if (cmd_frame[0] == CMD_GET_ADVERT_PATH && len >= PUB_KEY_SIZE+2) {
    // FUTURE use:  uint8_t reserved = cmd_frame[1];
    uint8_t *pub_key = &cmd_frame[2];
    AdvertPath* found = NULL;
    for (int i = 0; i < ADVERT_PATH_TABLE_SIZE; i++) {
      auto p = &advert_paths[i];
      if (memcmp(p->pubkey_prefix, pub_key, sizeof(p->pubkey_prefix)) == 0) {
        found = p;
        break;
      }
    }
    if (found) {
      int i = 0;
      out_frame[i++] = RESP_CODE_ADVERT_PATH;
      memcpy(&out_frame[i], &found->recv_timestamp, 4); i += 4;
      out_frame[i++] = found->path_len;
      i += mesh::Packet::writePath(&out_frame[i], found->path, found->path_len);
      _serial->writeFrame(out_frame, i);
    } else {
      writeErrFrame(ERR_CODE_NOT_FOUND);
    }
  } else if (cmd_frame[0] == CMD_GET_STATS && len >= 2) {
    uint8_t stats_type = cmd_frame[1];
    if (stats_type == STATS_TYPE_CORE) {
      int i = 0;
      out_frame[i++] = RESP_CODE_STATS;
      out_frame[i++] = STATS_TYPE_CORE;
      uint16_t battery_mv = board.getBattMilliVolts();
      uint32_t uptime_secs = _ms->getMillis() / 1000;
      uint8_t queue_len = (uint8_t)_mgr->getOutboundTotal();
      memcpy(&out_frame[i], &battery_mv, 2); i += 2;
      memcpy(&out_frame[i], &uptime_secs, 4); i += 4;
      memcpy(&out_frame[i], &_err_flags, 2); i += 2;
      out_frame[i++] = queue_len;
      _serial->writeFrame(out_frame, i);
    } else if (stats_type == STATS_TYPE_RADIO) {
      int i = 0;
      out_frame[i++] = RESP_CODE_STATS;
      out_frame[i++] = STATS_TYPE_RADIO;
      int16_t noise_floor = (int16_t)_radio->getNoiseFloor();
      int8_t last_rssi = (int8_t)radio_driver.getLastRSSI();
      int8_t last_snr = (int8_t)(radio_driver.getLastSNR() * 4); // scaled by 4 for 0.25 dB precision
      uint32_t tx_air_secs = getTotalAirTime() / 1000;
      uint32_t rx_air_secs = getReceiveAirTime() / 1000;
      memcpy(&out_frame[i], &noise_floor, 2); i += 2;
      out_frame[i++] = last_rssi;
      out_frame[i++] = last_snr;
      memcpy(&out_frame[i], &tx_air_secs, 4); i += 4;
      memcpy(&out_frame[i], &rx_air_secs, 4); i += 4;
      _serial->writeFrame(out_frame, i);
    } else if (stats_type == STATS_TYPE_PACKETS) {
      int i = 0;
      out_frame[i++] = RESP_CODE_STATS;
      out_frame[i++] = STATS_TYPE_PACKETS;
      uint32_t recv = radio_driver.getPacketsRecv();
      uint32_t sent = radio_driver.getPacketsSent();
      uint32_t n_sent_flood = getNumSentFlood();
      uint32_t n_sent_direct = getNumSentDirect();
      uint32_t n_recv_flood = getNumRecvFlood();
      uint32_t n_recv_direct = getNumRecvDirect();
      uint32_t n_recv_errors = radio_driver.getPacketsRecvErrors();
      memcpy(&out_frame[i], &recv, 4); i += 4;
      memcpy(&out_frame[i], &sent, 4); i += 4;
      memcpy(&out_frame[i], &n_sent_flood, 4); i += 4;
      memcpy(&out_frame[i], &n_sent_direct, 4); i += 4;
      memcpy(&out_frame[i], &n_recv_flood, 4); i += 4;
      memcpy(&out_frame[i], &n_recv_direct, 4); i += 4;
      memcpy(&out_frame[i], &n_recv_errors, 4); i += 4;
      _serial->writeFrame(out_frame, i);
    } else {
      writeErrFrame(ERR_CODE_ILLEGAL_ARG); // invalid stats sub-type
    }
  } else if (cmd_frame[0] == CMD_FACTORY_RESET && memcmp(&cmd_frame[1], "reset", 5) == 0) {
    if (_serial) {
      MESH_DEBUG_PRINTLN("Factory reset: disabling serial interface to prevent reconnects (BLE/WiFi)");
      _serial->disable(); // Phone app disconnects before we can send OK frame so it's safe here
    }
    bool success = _store->formatFileSystem();
    if (success) {
      writeOKFrame();
      delay(1000);
      board.reboot();  // doesn't return
    } else {
      writeErrFrame(ERR_CODE_FILE_IO_ERROR);
    }
  } else if (cmd_frame[0] == CMD_SET_FLOOD_SCOPE_KEY && len >= 2 && cmd_frame[1] == 0) {
    if (len >= 2 + 16) {
      memcpy(send_scope.key, &cmd_frame[2], sizeof(send_scope.key));  // set scope override TransportKey
    } else {
      memset(send_scope.key, 0, sizeof(send_scope.key));  // reset scope override
    }
    send_unscoped = false;
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_SET_FLOOD_SCOPE_KEY && len >= 2 && cmd_frame[1] == 1) {  // ver 12+
    send_unscoped = true;
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_SET_DEFAULT_FLOOD_SCOPE && len >= 1) {
    if (len >= 1+31+16) {
      int n = strlen((char *) &cmd_frame[1]);
      if (n > 0 && n < 31) {
        strcpy(_prefs.default_scope_name, (char *) &cmd_frame[1]);
        memcpy(_prefs.default_scope_key, &cmd_frame[1+31], 16);
        savePrefs();
        writeOKFrame();
      } else {
        writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      }
    } else {
      memset(_prefs.default_scope_name, 0, sizeof(_prefs.default_scope_name));  // set default scope to null
      memset(_prefs.default_scope_key, 0, sizeof(_prefs.default_scope_key));
      savePrefs();
      writeOKFrame();
    }
  } else if (cmd_frame[0] == CMD_GET_DEFAULT_FLOOD_SCOPE) {
    out_frame[0] = RESP_CODE_DEFAULT_FLOOD_SCOPE;
    if (strlen(_prefs.default_scope_name) > 0) {
      memcpy(&out_frame[1], _prefs.default_scope_name, 31);
      memcpy(&out_frame[1+31], _prefs.default_scope_key, 16);
      _serial->writeFrame(out_frame, 1+31+16);
    } else {
      _serial->writeFrame(out_frame, 1);   // no name or key means null
    }
  } else if (cmd_frame[0] == CMD_SEND_CONTROL_DATA && len >= 2 && (cmd_frame[1] & 0x80) != 0) {
    auto resp = createControlData(&cmd_frame[1], len - 1);
    if (resp) {
      sendZeroHop(resp);
      writeOKFrame();
    } else {
      writeErrFrame(ERR_CODE_TABLE_FULL);
    }
  } else if (cmd_frame[0] == CMD_SET_AUTOADD_CONFIG) {
    _prefs.autoadd_config = cmd_frame[1];
    if (len >= 3) {
      _prefs.autoadd_max_hops = min(cmd_frame[2], (uint8_t)64);
    }
    savePrefs();
    writeOKFrame();
  } else if (cmd_frame[0] == CMD_GET_AUTOADD_CONFIG) {
    int i = 0;
    out_frame[i++] = RESP_CODE_AUTOADD_CONFIG;
    out_frame[i++] = _prefs.autoadd_config;
    out_frame[i++] = _prefs.autoadd_max_hops;
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_GET_ALLOWED_REPEAT_FREQ) {
    int i = 0;
    out_frame[i++] = RESP_ALLOWED_REPEAT_FREQ;
    for (int k = 0; k < sizeof(repeat_freq_ranges)/sizeof(repeat_freq_ranges[0]) && i + 8 < sizeof(out_frame); k++) {
      auto r = &repeat_freq_ranges[k];
      memcpy(&out_frame[i], &r->lower_freq, 4); i += 4;
      memcpy(&out_frame[i], &r->upper_freq, 4); i += 4;
    }
    _serial->writeFrame(out_frame, i);
  } else if (cmd_frame[0] == CMD_SEND_RAW_PACKET && len >= 4) {
    auto pkt = obtainNewPacket();
    if (pkt) {
      uint8_t priority = cmd_frame[1];
      if (tryParsePacket(pkt, &cmd_frame[2], len - 2)) {
        sendPacket(pkt, priority, 0);
        writeOKFrame();
      } else {
        releasePacket(pkt);
        writeErrFrame(ERR_CODE_ILLEGAL_ARG);
      }
    } else {
      writeErrFrame(ERR_CODE_TABLE_FULL);
    }
  } else {
    writeErrFrame(ERR_CODE_UNSUPPORTED_CMD);
    MESH_DEBUG_PRINTLN("ERROR: unknown command: %02X", cmd_frame[0]);
  }
}

static bool save_filter(const ContactInfo& c) {
  return c.type != ADV_TYPE_NONE;   // don't save the transient/anon entries
}

void MyMesh::saveContacts() {
  _store->saveContacts(this, save_filter);
}

void MyMesh::enterCLIRescue() {
  _cli_rescue = true;
  cli_command[0] = 0;
  Serial.println("========= CLI Rescue =========");
}

void MyMesh::checkCLIRescueCmd() {
  int len = strlen(cli_command);
  while (Serial.available() && len < sizeof(cli_command)-1) {
    char c = Serial.read();
    if (c != '\n') {
      cli_command[len++] = c;
      cli_command[len] = 0;
    }
    Serial.print(c);  // echo
  }
  if (len == sizeof(cli_command)-1) {  // command buffer full
    cli_command[sizeof(cli_command)-1] = '\r';
  }

  if (len > 0 && cli_command[len - 1] == '\r') {  // received complete line
    cli_command[len - 1] = 0;  // replace newline with C string null terminator

    if (memcmp(cli_command, "set ", 4) == 0) {
      const char* config = &cli_command[4];
      if (memcmp(config, "pin ", 4) == 0) {
        _prefs.ble_pin = atoi(&config[4]);
        savePrefs();
        Serial.printf("  > pin is now %06d\n", _prefs.ble_pin);
      } else {
        Serial.printf("  Error: unknown config: %s\n", config);
      }
    } else if (strcmp(cli_command, "rebuild") == 0) {
      bool success = _store->formatFileSystem();
      if (success) {
        _store->saveMainIdentity(self_id);
        savePrefs();
        saveContacts();
        saveChannels();
        Serial.println("  > erase and rebuild done");
      } else {
        Serial.println("  Error: erase failed");
      }
    } else if (strcmp(cli_command, "erase") == 0) {
      bool success = _store->formatFileSystem();
      if (success) {
        Serial.println("  > erase done");
      } else {
        Serial.println("  Error: erase failed");
      }
    } else if (memcmp(cli_command, "ls", 2) == 0) {

      // get path from command e.g: "ls /adafruit"
      const char *path = &cli_command[3];

      bool is_fs2 = false;
      if (memcmp(path, "UserData/", 9) == 0) {
        path += 8; // skip "UserData"
      } else if (memcmp(path, "ExtraFS/", 8) == 0) {
        path += 7; // skip "ExtraFS"
        is_fs2 = true;
      }
      Serial.printf("Listing files in %s\n", path);

      // log each file and directory
      File root = _store->openRead(path);
      if (is_fs2 == false) {
        if (root) {
          File file = root.openNextFile();
          while (file) {
            if (file.isDirectory()) {
              Serial.printf("[dir]  UserData%s/%s\n", path, file.name());
            } else {
              Serial.printf("[file] UserData%s/%s (%d bytes)\n", path, file.name(), file.size());
            }
            // move to next file
            file = root.openNextFile();
          }
          root.close();
        }
      }

      if (is_fs2 == true || strlen(path) == 0 || strcmp(path, "/") == 0) {
        if (_store->getSecondaryFS() != nullptr) {
          File root2 = _store->openRead(_store->getSecondaryFS(), path);
          File file = root2.openNextFile();
          while (file) {
            if (file.isDirectory()) {
              Serial.printf("[dir]  ExtraFS%s/%s\n", path, file.name());
            } else {
              Serial.printf("[file] ExtraFS%s/%s (%d bytes)\n", path, file.name(), file.size());
            }
            // move to next file
            file = root2.openNextFile();
          }
          root2.close();
        }
      }
    } else if (memcmp(cli_command, "cat", 3) == 0) {

      // get path from command e.g: "cat /contacts3"
      const char *path = &cli_command[4];

      bool is_fs2 = false;
      if (memcmp(path, "UserData/", 9) == 0) {
        path += 8; // skip "UserData"
      } else if (memcmp(path, "ExtraFS/", 8) == 0) {
        path += 7; // skip "ExtraFS"
        is_fs2 = true;
      } else {
        Serial.println("Invalid path provided, must start with UserData/ or ExtraFS/");
        cli_command[0] = 0;
        return;
      }

      // log file content as hex
      File file = _store->openRead(path);
      if (is_fs2 == true) {
        file = _store->openRead(_store->getSecondaryFS(), path);
      }
      if(file){

        // get file content
        int file_size = file.available();
        uint8_t buffer[file_size];
        file.read(buffer, file_size);

        // print hex
        mesh::Utils::printHex(Serial, buffer, file_size);
        Serial.print("\n");

        file.close();

      }

    } else if (memcmp(cli_command, "rm ", 3) == 0) {
      // get path from command e.g: "rm /adv_blobs"
      const char *path = &cli_command[3];
      MESH_DEBUG_PRINTLN("Removing file: %s", path);
      // ensure path is not empty, or root dir
      if(!path || strlen(path) == 0 || strcmp(path, "/") == 0){
        Serial.println("Invalid path provided");
      } else {
      bool is_fs2 = false;
      if (memcmp(path, "UserData/", 9) == 0) {
        path += 8; // skip "UserData"
      } else if (memcmp(path, "ExtraFS/", 8) == 0) {
        path += 7; // skip "ExtraFS"
        is_fs2 = true;
      }

        // remove file
        bool removed;
        if (is_fs2) {
          MESH_DEBUG_PRINTLN("Removing file from ExtraFS: %s", path);
          removed = _store->removeFile(_store->getSecondaryFS(), path);
        } else {
          MESH_DEBUG_PRINTLN("Removing file from UserData: %s", path);
          removed = _store->removeFile(path);
        }
        if(removed){
          Serial.println("File removed");
        } else {
          Serial.println("Failed to remove file");
        }

      }

    } else if (strcmp(cli_command, "reboot") == 0) {
      board.reboot();  // doesn't return
    } else {
      Serial.println("  Error: unknown command");
    }

    cli_command[0] = 0;  // reset command buffer
  }
}

void MyMesh::checkSerialInterface() {
  size_t len = _serial->checkRecvFrame(cmd_frame);
  if (len > 0) {
    handleCmdFrame(len);
  } else if (_iter_started              // check if our ContactsIterator is 'running'
             && !_serial->isWriteBusy() // don't spam the Serial Interface too quickly!
  ) {
    ContactInfo contact;
    if (_iter.hasNext(this, contact)) {
      if (contact.lastmod > _iter_filter_since) { // apply the 'since' filter
        writeContactRespFrame(RESP_CODE_CONTACT, contact);
        if (contact.lastmod > _most_recent_lastmod) {
          _most_recent_lastmod = contact.lastmod; // save for the RESP_CODE_END_OF_CONTACTS frame
        }
      }
    } else { // EOF
      out_frame[0] = RESP_CODE_END_OF_CONTACTS;
      memcpy(&out_frame[1], &_most_recent_lastmod,
             4); // include the most recent lastmod, so app can update their 'since'
      _serial->writeFrame(out_frame, 5);
      _iter_started = false;
    }
  //} else if (!_serial->isWriteBusy()) {
  //  checkConnections();    // TODO - deprecate the 'Connections' stuff
  }
}

void MyMesh::loop() {
  BaseChatMesh::loop();
  sampleChannelBusy();

  if (_cli_rescue) {
    checkCLIRescueCmd();
  } else {
    checkSerialInterface();
  }

  // is there are pending dirty contacts write needed?
  if (dirty_contacts_expiry && millisHasNowPassed(dirty_contacts_expiry)) {
    saveContacts();
    dirty_contacts_expiry = 0;
  }

  if (next_auto_advert && millisHasNowPassed(next_auto_advert)) {
    if (!advert()) MESH_DEBUG_PRINTLN("ERROR: auto advert failed");
    updateAutoAdvertTimer();
  }

#ifdef DISPLAY_CLASS
  if (_ui) _ui->setHasConnection(_serial->isConnected());
#endif
}

void MyMesh::sampleChannelBusy() {
  unsigned long now = millis();
  if (channel_busy_sample_ms != 0 && _radio->isReceiving()) {
    channel_busy_ms += now - channel_busy_sample_ms;
  }
  channel_busy_sample_ms = now;
}

bool MyMesh::advert() {
  mesh::Packet* pkt;
  double lat, lon, alt;
  if (_prefs.advert_loc_policy == ADVERT_LOC_NONE || !getShareableLocation(lat, lon, alt)) {
    pkt = createSelfAdvert(_prefs.node_name);
  } else {
    pkt = createSelfAdvert(_prefs.node_name, lat, lon);
  }
  if (pkt) {
    sendZeroHop(pkt);
    return true;
  } else {
    return false;
  }
}

bool MyMesh::sendQuickReply(const char* text) {
  if (text == NULL || text[0] == 0) return false;
  ChannelDetails channel;
  if (!getChannel(0, channel)) return false;
  bool sent = sendGroupMessage(getRTCClock()->getCurrentTime(), channel.channel,
                               _prefs.node_name, text, strlen(text));
  if (sent) {
    char local_text[160];
    snprintf(local_text, sizeof(local_text), "%s: %s", _prefs.node_name, text);
    noteChannelChat(channel.name, NULL, local_text);
  }
  return sent;
}

int MyMesh::getQuickReplyChannelCount() {
#ifdef MAX_GROUP_CHANNELS
  int count = 0;
  for (uint8_t i = 0; i < MAX_GROUP_CHANNELS; i++) {
    ChannelDetails channel;
    if (getChannel(i, channel) && channel.name[0] != 0) count++;
  }
  return count;
#else
  return 0;
#endif
}

bool MyMesh::getQuickReplyChannel(uint16_t list_idx, uint8_t& channel_idx,
                                  ChannelDetails& channel) {
#ifdef MAX_GROUP_CHANNELS
  uint16_t seen = 0;
  for (uint8_t i = 0; i < MAX_GROUP_CHANNELS; i++) {
    ChannelDetails candidate;
    if (!getChannel(i, candidate) || candidate.name[0] == 0) continue;
    if (seen++ == list_idx) {
      channel_idx = i;
      channel = candidate;
      return true;
    }
  }
#endif
  return false;
}

int MyMesh::getQuickReplyContactCount() {
  int count = 0;
  ContactInfo contact;
  for (uint32_t i = 0; getContactByIdx(i, contact); i++) {
    // Target list intentionally excludes repeaters, rooms and sensors.
    if (contact.type == ADV_TYPE_CHAT && contact.name[0] != 0) count++;
  }
  return count;
}

bool MyMesh::getQuickReplyContact(uint16_t list_idx, ContactInfo& contact) {
  uint16_t seen = 0;
  ContactInfo candidate;
  for (uint32_t i = 0; getContactByIdx(i, candidate); i++) {
    if (candidate.type != ADV_TYPE_CHAT || candidate.name[0] == 0) continue;
    if (seen++ == list_idx) {
      contact = candidate;
      return true;
    }
  }
  return false;
}

bool MyMesh::sendQuickReplyToChannel(uint16_t list_idx, const char* text) {
  if (text == NULL || text[0] == 0) return false;
  uint8_t channel_idx = 0;
  ChannelDetails channel;
  if (!getQuickReplyChannel(list_idx, channel_idx, channel)) return false;
  bool sent = sendGroupMessage(getRTCClock()->getCurrentTime(), channel.channel,
                               _prefs.node_name, text, strlen(text));
  if (sent) {
    char local_text[160];
    snprintf(local_text, sizeof(local_text), "%s: %s", _prefs.node_name, text);
    noteChannelChat(channel.name, NULL, local_text);
  }
  return sent;
}

bool MyMesh::sendQuickReplyToContact(uint16_t list_idx, const char* text) {
  if (text == NULL || text[0] == 0) return false;
  ContactInfo contact_copy;
  if (!getQuickReplyContact(list_idx, contact_copy)) return false;
  ContactInfo* recipient = lookupContactByPubKey(contact_copy.id.pub_key, PUB_KEY_SIZE);
  if (recipient == NULL || recipient->type != ADV_TYPE_CHAT) return false;
  uint32_t expected_ack = 0;
  uint32_t est_timeout = 0;
  int result = sendMessage(*recipient, getRTCClock()->getCurrentTimeUnique(), 0,
                           text, expected_ack, est_timeout);
  if (result == MSG_SEND_FAILED) return false;
  if (expected_ack) {
    expected_ack_table[next_ack_idx].msg_sent = _ms->getMillis();
    expected_ack_table[next_ack_idx].ack = expected_ack;
    expected_ack_table[next_ack_idx].contact = recipient;
    next_ack_idx = (next_ack_idx + 1) % EXPECTED_ACK_TABLE_SIZE;
  }
  return true;
}

// To check if there is pending work
bool MyMesh::hasPendingWork() const {
  bool calibration_active = false;
#ifdef WRAPPER_CLASS
  const RxPowerSavingControl* rxps_control = &radio_driver;
  calibration_active = rxps_control->isRxPowerSavingCalibrationActive();
#endif
  return _mgr->getOutboundTotal() > 0 || dirty_contacts_expiry != 0 || calibration_active;
}
