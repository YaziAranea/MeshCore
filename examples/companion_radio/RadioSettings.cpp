#include "RadioSettings.h"
#include "helpers/radiolib/LoRaConfigValidation.h"

#include <stdio.h>
#include <string.h>

namespace smartui {
namespace {
constexpr size_t MAX_TEXT = 156;

bool parseUnsignedList(const char* text, uint32_t* values, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    if (*text < '0' || *text > '9') return false;
    uint32_t value = 0;
    do {
      const uint32_t digit = static_cast<uint32_t>(*text++ - '0');
      if (value > (UINT32_MAX - digit) / 10U) return false;
      value = value * 10U + digit;
    } while (*text >= '0' && *text <= '9');
    values[i] = value;
    if (i + 1 == count) return *text == 0;
    if (*text++ != ' ') return false;
  }
  return false;
}

bool validState(const RadioSettingsState& state) {
  float bw = state.bandwidth_khz, canonical;
  if (canonicalSX1262Bandwidth(bw, canonical)) bw = canonical;
  return validCompanionLoRaParams(state.frequency_mhz, bw,
                                  state.sf, state.cr) &&
         state.path_bytes >= 1 && state.path_bytes <= 3;
}
}  // namespace

bool RadioSettings::handle(const char* command, char* reply, size_t capacity,
                            bool allow_mutation) {
  if (!command) return false;
  const char* ns;
  const char* body;
  if (strncmp(command, "ui ", 3) == 0) { ns = "ui"; body = command + 3; }
  else if (strncmp(command, "settings ", 9) == 0) { ns = "settings"; body = command + 9; }
  else return false;
  const bool radio = strcmp(body, "radio") == 0 || strncmp(body, "radio ", 6) == 0;
  const bool advert = strcmp(body, "advert") == 0 || strncmp(body, "advert ", 7) == 0;
  if (!radio && !advert) return false;
  if (!reply || capacity == 0) return true;
  auto error = [&](const char* reason) { snprintf(reply, capacity, "ERR %s %s", ns, reason); };
  // Refuse before any hardware/flash mutation if the full reply cannot fit.
  if (capacity <= MAX_TEXT) { error("buffer"); return true; }
  size_t length = 0;
  while (length <= MAX_TEXT && command[length]) {
    const uint8_t c = static_cast<uint8_t>(command[length++]);
    if (c < 0x20 || c > 0x7e) { error("invalid"); return true; }
  }
  if (length > MAX_TEXT) { error("invalid"); return true; }
  if (!_hooks.read || !_hooks.write || !_hooks.save || !_hooks.validate ||
      !_hooks.repeatAllowed || !_hooks.applyRadio || !_hooks.applyAdvert ||
      !_hooks.busy || !_hooks.healthy) { error("unsupported"); return true; }
  const RadioSettingsState before = _hooks.read();
  RadioSettingsState after = before;
  const bool query = strcmp(body, radio ? "radio" : "advert") == 0;
  if (!query) {
    const char* prefix = radio ? "radio set " : "advert set ";
    uint32_t values[5] = {};
    if (strncmp(body, prefix, strlen(prefix)) != 0 ||
        !parseUnsignedList(body + strlen(prefix), values, radio ? 5 : 1)) {
      error("invalid"); return true;
    }
    if (radio) {
      // Validate wide integers before narrowing, conversion or driver access.
      if (values[0] < 150000 || values[0] > 2500000 ||
          values[1] < 7000 || values[1] > 500000 ||
          values[2] < 5 || values[2] > 12 || values[3] < 5 || values[3] > 8 ||
          values[4] < 1 || values[4] > 3) { error("invalid"); return true; }
      after.frequency_mhz = companionFrequencyMHz(values[0]);
      after.bandwidth_khz = companionBandwidthKHz(values[1]);
      after.sf = static_cast<uint8_t>(values[2]);
      after.cr = static_cast<uint8_t>(values[3]);
      after.path_bytes = static_cast<uint8_t>(values[4]);
      if (!_hooks.validate(after)) { error("invalid"); return true; }
      if (before.repeat && !_hooks.repeatAllowed(values[0])) { error("repeat"); return true; }
    } else {
      if (!validAutoAdvertInterval(values[0])) { error("invalid"); return true; }
      after.advert_minutes = static_cast<uint16_t>(values[0]);
    }
    if (!allow_mutation) { error("readonly"); return true; }
    if (_hooks.busy()) { error("busy"); return true; }
    if (radio) {
      if (!validState(before) || !_hooks.healthy()) { error("restore"); return true; }
      // TX power and repeat are copied from before and never changed by presets.
      if (!_hooks.applyRadio(after)) {
        error(_hooks.applyRadio(before) ? "radio" : "restore");
        return true;
      }
    } else if (after.advert_minutes == before.advert_minutes) {
      // Idempotent re-application does not postpone the next advertisement.
      snprintf(reply, capacity, "OK %s advert interval_min=%u", ns, before.advert_minutes);
      return true;
    }
    _hooks.write(after);
    if (!_hooks.save()) {
      _hooks.write(before);
      error(!radio || _hooks.applyRadio(before) ? "storage" : "restore");
      return true;
    }
    if (!radio) _hooks.applyAdvert();
  }
  const RadioSettingsState current = _hooks.read();
  if (radio) {
    if (!validState(current) || !_hooks.healthy()) { error("restore"); return true; }
    snprintf(reply, capacity,
        "OK %s radio freq_khz=%lu bw_hz=%lu sf=%u cr=%u path_bytes=%u tx_dbm=%d repeat=%u",
        ns, static_cast<unsigned long>(current.frequency_mhz * 1000.0f + 0.5f),
        static_cast<unsigned long>(current.bandwidth_khz * 1000.0f + 0.5f),
        current.sf, current.cr, current.path_bytes, current.tx_dbm, current.repeat ? 1U : 0U);
  } else {
    if (!validAutoAdvertInterval(current.advert_minutes)) { error("invalid"); return true; }
    snprintf(reply, capacity, "OK %s advert interval_min=%u", ns, current.advert_minutes);
  }
  return true;
}

}  // namespace smartui
