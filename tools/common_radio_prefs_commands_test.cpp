#include "helpers/CommonRadioPrefs.h"
#include "helpers/TxtDataHelpers.h"
#include "helpers/radiolib/LoRaConfigValidation.h"
#include "Utils.h"
#include "target.h"
#include <cstdio>
#include <cstring>
#include <string>

TestRadio radio_driver;
const char* StrHelper::ftoa(float value) {
  static char text[32]; snprintf(text, sizeof(text), "%g", value); return text;
}
const char* StrHelper::ftoa3(float value) { return ftoa(value); }

// Only the hardware/storage endpoint is simulated. The complete production
// CommonRadioPrefs.cpp, its header and its dynamic-key implementation link below.
class Prefs : public CommonRadioPrefs {
  void structure() override {}
public:
  unsigned writes = 0;
#define FIELD(type, name, initial) \
  type value##name = initial; \
  type get##name() const override { return value##name; } \
  void set##name(type value) override { value##name = value; ++writes; markDirty(); }
  FIELD(float, Freq, 868.0f)
  FIELD(float, Bandwidth, 125.0f)
  FIELD(uint8_t, SpreadFactor, 9)
  FIELD(uint8_t, CodingRate, 5)
  FIELD(float, AirtimeFactor, 1.0f)
  FIELD(uint8_t, IntThresh, 0)
  FIELD(uint8_t, RxGain, 0)
  FIELD(int8_t, TxPower, 20)
  FIELD(float, RxDelay, 1.0f)
  FIELD(uint16_t, AgcResetInt, 0)
  FIELD(uint8_t, HashMode, 0)
  FIELD(uint8_t, MultiAcks, 0)
  FIELD(float, FloodTxDelay, 0.5f)
  FIELD(float, DirectTxDelay, 0.2f)
  FIELD(uint8_t, FEMRxGain, 0)
  FIELD(uint8_t, FEMTxGain, 0)
#undef FIELD
  bool cad = false;
  bool isCadEnabled() const override { return cad; }
  void setCadEnabled(bool enabled) override { cad = enabled; ++writes; markDirty(); }
};

static unsigned checks, failed;
static void check(bool condition, const std::string& command, const char* reply) {
  ++checks;
  if (!condition) {
    ++failed;
    fprintf(stderr, "FAIL %s => %s\n", command.c_str(), reply);
  }
}
static std::string execute(Prefs& prefs, const std::string& text) {
  char command[256] = {}, reply[162];
  snprintf(command, sizeof(command), "%s", text.c_str());
  memset(reply, 0x5a, sizeof(reply));
  check(prefs.handleCommand(command, 0, reply + 1), text, "not handled");
  check(reply[0] == 0x5a && reply[161] == 0x5a, text, "reply bounds");
  return reply + 1;
}
int main() {
  for (const char* key : {"af", "dutycycle", "rxdelay", "txdelay", "direct.txdelay"}) {
    for (const char* invalid : {"nan", "NaN", "nan(1)", "-nan", "inf", "-inf", "1e999", "",
                                "garbage", "1junk", "1 2", "1%"}) {
      Prefs prefs;
      const std::string command = std::string("set ") + key + " " + invalid;
      const auto reply = execute(prefs, command);
      check(reply.rfind("Error", 0) == 0 || reply.rfind("ERROR", 0) == 0, command, reply.c_str());
      check(prefs.writes == 0 && !prefs.isDirty(), command, "changed settings");
    }
  }
  for (const char* invalid : {"nan,125,9,5", "868,nan,9,5", "868junk,125,9,5",
                              "868,125junk,9,5", "1e999,125,9,5", "868,1e999,9,5"}) {
    Prefs prefs;
    const std::string command = std::string("set radio ") + invalid;
    const auto reply = execute(prefs, command);
    check(reply == "Error, invalid radio params", command, reply.c_str());
    check(prefs.writes == 0 && !prefs.isDirty(), command, "changed settings");
  }
  struct Valid { const char* command; float expected; float (Prefs::*read)() const; };
  const Valid valid[] = {
      {"set af 0", 0, &Prefs::getAirtimeFactor}, {"set af 9", 9, &Prefs::getAirtimeFactor},
      {"set af 1.25", 1.25f, &Prefs::getAirtimeFactor}, {"set af 1e0", 1, &Prefs::getAirtimeFactor},
      {"set dutycycle 1", 99, &Prefs::getAirtimeFactor}, {"set dutycycle 100", 0, &Prefs::getAirtimeFactor},
      {"set dutycycle 25", 3, &Prefs::getAirtimeFactor},
      {"set rxdelay 0", 0, &Prefs::getRxDelay}, {"set rxdelay 20", 20, &Prefs::getRxDelay},
      {"set txdelay 0", 0, &Prefs::getFloodTxDelay}, {"set txdelay 2", 2, &Prefs::getFloodTxDelay},
      {"set direct.txdelay 0", 0, &Prefs::getDirectTxDelay}, {"set direct.txdelay 2", 2, &Prefs::getDirectTxDelay},
  };
  for (const Valid& item : valid) {
    Prefs prefs;
    const auto reply = execute(prefs, item.command);
    check(reply.rfind("OK", 0) == 0, item.command, reply.c_str());
    check(prefs.writes == 1 && prefs.isDirty(), item.command, "missing write");
    check(loRaFloatBits((prefs.*item.read)()) == loRaFloatBits(item.expected), item.command, "wrong value");
  }
  for (const char* command : {"set af -0.1", "set af 9.1", "set dutycycle 0", "set dutycycle 101",
                               "set rxdelay -1", "set rxdelay 21", "set txdelay -1", "set txdelay 3",
                               "set direct.txdelay -1", "set direct.txdelay 3"}) {
    Prefs prefs;
    execute(prefs, command);
    check(prefs.writes == 0 && !prefs.isDirty(), command, "out-of-range write");
  }
  Prefs prefs;
  const auto radio = execute(prefs, "set radio 868.125,125,9,5");
  check(radio == "OK - reboot to apply" && prefs.writes == 4 && prefs.isDirty(), "valid radio", radio.c_str());
  check(prefs.getFreq() == 868.125f && prefs.getBandwidth() == 125 &&
        prefs.getSpreadFactor() == 9 && prefs.getCodingRate() == 5, "valid radio", "wrong parameters");
  printf("%s: %u actual CommonRadioPrefs float-command checks (%u failures)\n", failed ? "FAIL" : "PASS", checks, failed);
  return failed ? 1 : 0;
}
