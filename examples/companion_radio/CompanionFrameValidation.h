#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Lightweight, Arduino-independent validation for frames received from a
// companion transport.  Keep this header dependency-free so the same parser
// boundary can be exercised by native sanitised/fuzz-style tests.
namespace companion {

enum CommandCode : uint8_t {
  kAppStart = 1,
  kSendTextMessage = 2,
  kSendChannelTextMessage = 3,
  kGetContacts = 4,
  kGetDeviceTime = 5,
  kSetDeviceTime = 6,
  kSendSelfAdvert = 7,
  kSetAdvertName = 8,
  kAddUpdateContact = 9,
  kSyncNextMessage = 10,
  kSetRadioParams = 11,
  kSetRadioTxPower = 12,
  kResetPath = 13,
  kSetAdvertLatLon = 14,
  kRemoveContact = 15,
  kShareContact = 16,
  kExportContact = 17,
  kImportContact = 18,
  kReboot = 19,
  kGetBatteryAndStorage = 20,
  kSetTuningParams = 21,
  kDeviceQuery = 22,
  kExportPrivateKey = 23,
  kImportPrivateKey = 24,
  kSendRawData = 25,
  kSendLogin = 26,
  kSendStatusRequest = 27,
  kHasConnection = 28,
  kLogout = 29,
  kGetContactByKey = 30,
  kGetChannel = 31,
  kSetChannel = 32,
  kSignStart = 33,
  kSignData = 34,
  kSignFinish = 35,
  kSendTracePath = 36,
  kSetDevicePin = 37,
  kSetOtherParams = 38,
  kSendTelemetryRequest = 39,
  kGetCustomVars = 40,
  kSetCustomVar = 41,
  kGetAdvertPath = 42,
  kGetTuningParams = 43,
  kSetPhoneGpsLegacy = 44,
  kSendBinaryRequest = 50,
  kFactoryReset = 51,
  kSendPathDiscoveryRequest = 52,
  kSetFloodScopeKey = 54,
  kSendControlData = 55,
  kGetStats = 56,
  kSendAnonymousRequest = 57,
  kSetAutoaddConfig = 58,
  kGetAutoaddConfig = 59,
  kGetAllowedRepeatFrequency = 60,
  kSetPathHashMode = 61,
  kSendChannelData = 62,
  kSetDefaultFloodScope = 63,
  kGetDefaultFloodScope = 64,
  kSendRawPacket = 65,
  // Experimental SmartUI extension.  44 remains an opt-in legacy alias only
  // when phone-GPS support is explicitly compiled in.
  kSetPhoneGps = 200,
};

enum FrameValidationResult : uint8_t {
  kFrameValid = 0,
  kFrameEmpty,
  kFrameTooLarge,
  kFrameTooShort,
  kFrameInvalidPath,
  kFrameInvalidShape,
};

class FrameReader {
public:
  FrameReader(const uint8_t* data, size_t length)
      : _data(data), _length(length), _position(0) {}

  size_t size() const { return _length; }
  size_t position() const { return _position; }
  size_t remaining() const {
    return _position <= _length ? _length - _position : 0;
  }
  bool has(size_t offset, size_t count = 1) const {
    return offset <= _length && count <= _length - offset;
  }
  bool skip(size_t count) {
    if (count > remaining()) return false;
    _position += count;
    return true;
  }
  bool readU8(uint8_t& value) {
    if (!has(_position)) return false;
    value = _data[_position++];
    return true;
  }
  bool readBytes(void* destination, size_t count) {
    if (count > remaining()) return false;
    if (count != 0) memcpy(destination, &_data[_position], count);
    _position += count;
    return true;
  }
  const uint8_t* take(size_t count) {
    if (count > remaining()) return NULL;
    const uint8_t* result = &_data[_position];
    _position += count;
    return result;
  }
  bool equalsAt(size_t offset, const char* token, size_t token_length) const {
    return token != NULL && has(offset, token_length) &&
           memcmp(&_data[offset], token, token_length) == 0;
  }
  bool boundedCStringLength(size_t offset, size_t field_length, size_t& result) const {
    if (!has(offset, field_length)) return false;
    const void* end = memchr(&_data[offset], 0, field_length);
    if (end == NULL) return false;
    result = static_cast<const uint8_t*>(end) - &_data[offset];
    return true;
  }

private:
  const uint8_t* _data;
  size_t _length;
  size_t _position;
};

inline bool encodedPathByteLength(uint8_t encoded_length, size_t max_path_bytes,
                                  size_t& byte_length) {
  const size_t hash_count = encoded_length & 63U;
  const size_t hash_size = (encoded_length >> 6U) + 1U;
  if (hash_size == 4U) return false;  // reserved encoding, including 0xFF
  byte_length = hash_count * hash_size;
  return byte_length <= max_path_bytes;
}

inline size_t minimumCommandFrameLength(uint8_t command, size_t public_key_size,
                                        size_t max_path_bytes) {
  switch (command) {
    case kAppStart: return 8;
    case kSendTextMessage: return 8 + 6;  // command/type/attempt/time/key-prefix + text
    case kSendChannelTextMessage: return 7;
    case kSetDeviceTime: return 5;
    case kSetAdvertName: return 2;
    case kAddUpdateContact:
      return 1 + public_key_size + 3 + max_path_bytes + 32 + 4;
    case kSetRadioParams: return 11;
    case kSetRadioTxPower: return 2;
    case kResetPath:
    case kRemoveContact:
    case kShareContact:
    case kGetContactByKey:
    case kSendLogin:
    case kSendStatusRequest:
    case kHasConnection:
    case kLogout:
      return 1 + public_key_size;
    case kGetChannel: return 2;
    case kSetAdvertLatLon: return 9;
    case kImportContact: return 3 + 32 + 64;
    case kReboot: return 7;
    case kSetTuningParams: return 9;
    case kDeviceQuery: return 2;
    case kImportPrivateKey: return 65;
    case kSendRawData: return 6;
    case kSetChannel: return 2 + 32 + 16;
    case kSignData: return 2;
    case kSendTracePath: return 11;
    case kSetDevicePin: return 5;
    case kSetOtherParams: return 2;
    case kSetCustomVar: return 4;
    case kGetAdvertPath: return public_key_size + 2;
    case kSendBinaryRequest: return 2 + public_key_size;
    case kFactoryReset: return 6;
    case kSendPathDiscoveryRequest: return 2 + public_key_size;
    case kSetFloodScopeKey:
    case kSendControlData:
    case kGetStats:
    case kSetAutoaddConfig:
      return 2;
    case kSendAnonymousRequest: return 2 + public_key_size;
    case kSetPathHashMode: return 3;
    case kSendChannelData: return 5;
    case kSendRawPacket: return 4;
    default: return 1;
  }
}

inline FrameValidationResult validateCommandFrame(const uint8_t* data, size_t length,
                                                  size_t capacity,
                                                  size_t public_key_size,
                                                  size_t max_path_bytes,
                                                  size_t max_packet_payload) {
  if (data == NULL || length == 0) return kFrameEmpty;
  if (length > capacity) return kFrameTooLarge;

  const uint8_t command = data[0];
  if (length < minimumCommandFrameLength(command, public_key_size, max_path_bytes)) {
    return kFrameTooShort;
  }

  switch (command) {
    case kGetContacts:
      // The optional "since" value is a complete uint32_t, never a fragment.
      if (length != 1 && length < 5) return kFrameInvalidShape;
      break;

    case kSetAdvertLatLon:
      // Altitude is optional, but if present it must be a complete int32_t.
      if (length > 9 && length < 13) return kFrameInvalidShape;
      break;

    case kExportContact:
      // One-byte form exports self.  A remote export always identifies the
      // contact with a complete public key; a truncated key must not silently
      // turn into a self export.
      if (length != 1 && length < 1 + public_key_size) {
        return kFrameInvalidShape;
      }
      break;

    case kAddUpdateContact: {
      const size_t path_length_offset = 1 + public_key_size + 2;
      const uint8_t encoded_length = data[path_length_offset];
      size_t ignored = 0;
      if (encoded_length != 0xFF &&
          !encodedPathByteLength(encoded_length, max_path_bytes, ignored)) {
        return kFrameInvalidPath;
      }
      const size_t fixed_length =
          1 + public_key_size + 3 + max_path_bytes + 32 + 4;
      // GPS is an optional pair of int32 values; last-mod is another complete
      // uint32. Do not silently accept fragments of either extension.
      if ((length > fixed_length && length < fixed_length + 8) ||
          (length > fixed_length + 8 && length < fixed_length + 12)) {
        return kFrameInvalidShape;
      }
      break;
    }

    case kSendRawData: {
      size_t path_bytes = 0;
      if (!encodedPathByteLength(data[1], max_path_bytes, path_bytes)) {
        return kFrameInvalidPath;
      }
      if (path_bytes > length - 2 || length - 2 - path_bytes < 4) {
        return kFrameTooShort;
      }
      break;
    }

    case kSendTelemetryRequest:
      // Four bytes means local telemetry; remote telemetry contains a full key.
      if (length != 4 && length < 4 + public_key_size) return kFrameInvalidShape;
      break;

    case kSendTracePath: {
      const size_t path_bytes = length - 10;
      const uint8_t path_size_shift = data[9] & 0x03U;
      if (path_size_shift >= 3U || path_bytes >= max_packet_payload - 5U ||
          (path_bytes >> path_size_shift) > max_path_bytes ||
          (path_bytes % (1U << path_size_shift)) != 0) {
        return kFrameInvalidPath;
      }
      break;
    }

    case kSetFloodScopeKey:
      if (data[1] == 0) {
        // Mode zero accepts either a reset or a complete 16-byte key.
        if (length != 2 && length < 18) return kFrameInvalidShape;
      } else if (data[1] != 1) {
        return kFrameInvalidShape;
      }
      break;

    case kSendChannelData: {
      const uint8_t encoded_length = data[2];
      size_t path_bytes = 0;
      if (encoded_length != 0xFF &&
          !encodedPathByteLength(encoded_length, max_path_bytes, path_bytes)) {
        return kFrameInvalidPath;
      }
      if (encoded_length == 0xFF) path_bytes = 0;
      const size_t fixed_length = 3 + path_bytes + 2;
      if (length < fixed_length) return kFrameTooShort;
      if (length - fixed_length > capacity - 9) return kFrameInvalidShape;
      break;
    }

    case kSetDefaultFloodScope:
      // One byte clears the scope. Partial fixed-width records must not clear it.
      if (length != 1 && length < 1 + 31 + 16) return kFrameInvalidShape;
      break;

    default:
      break;
  }

  return kFrameValid;
}

}  // namespace companion
