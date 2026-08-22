#include <gtest/gtest.h>

#include <cstdio>
#include <cstring>
#include <string>

#include "../../examples/companion_radio/NodePrefs.h"

class ReplayStream : public Stream {
  const char* _text;
  int _pos = 0;
  int _len;

public:
  explicit ReplayStream(const char* text) : _text(text), _len(strlen(text)) { }

  int available() override { return _len - _pos; }
  int read() override { return _pos < _len ? _text[_pos++] : -1; }
  int peek() override { return _pos < _len ? _text[_pos] : -1; }
};

class CaptureStream : public Stream {
  std::string _text;

  size_t emit(long long value) {
    char text[24];
    int length = snprintf(text, sizeof(text), "%lld", value);
    return write(reinterpret_cast<const uint8_t*>(text), length);
  }

public:
  size_t write(uint8_t value) override {
    _text.push_back(static_cast<char>(value));
    return 1;
  }

  size_t write(const uint8_t* buffer, size_t size) override {
    _text.append(reinterpret_cast<const char*>(buffer), size);
    return size;
  }

  size_t print(unsigned char value, int = DEC) override { return emit(value); }
  size_t print(int value, int = DEC) override { return emit(value); }
  size_t print(unsigned int value, int = DEC) override { return emit(value); }
  size_t print(long value, int = DEC) override { return emit(value); }
  size_t print(unsigned long value, int = DEC) override { return emit(value); }
  size_t print(long long value, int = DEC) override { return emit(value); }
  size_t print(unsigned long long value, int = DEC) override { return emit(value); }
  size_t print(double value, int precision = 2) override {
    char text[48];
    int length = snprintf(text, sizeof(text), "%.*f", precision, value);
    return write(reinterpret_cast<const uint8_t*>(text), length);
  }

  const std::string& text() const { return _text; }
};

TEST(CompanionNodePrefs, SmartUiBuzzerSettingsCreateMigrationMarkerAndRoundTrip) {
  NodePrefs saved;
  saved.notify_mode = NOTIFY_MODE_GPIO | NOTIFY_MODE_TONE;
  saved.notify_gpio_pin = 45;
  saved.notify_tone_pin = 31;
  saved.notify_tone_id = 12;
  saved.notify_tone_volume = 7;
  saved.important_notify_mode = NOTIFY_MODE_TONE;
  saved.notifications_muted = 1;
  saved.notify_tone_bridge_enabled = 1;
  saved.notify_tone_8bit_enabled = 1;
  saved.notify_tone_high_drive_enabled = 1;
  saved.notify_pin_fix_version = 1;
  saved.notify_tone_resonance_hz = 3400;
  saved.notify_tone_dm_id = 12;
  saved.notify_tone_mention_id = 12;
  saved.notify_tone_system_id = 12;

  CaptureStream output;
  ASSERT_TRUE(saved.saveSerial(output));
  EXPECT_NE(std::string::npos, output.text().find("smart_ui:{"));
  EXPECT_NE(std::string::npos, output.text().find("tone_pin:31"));
  EXPECT_NE(std::string::npos, output.text().find("bridge:1"));
  EXPECT_NE(std::string::npos, output.text().find("pin_fix:1"));

  ReplayStream input(output.text().c_str());
  NodePrefs loaded;
  ASSERT_TRUE(loaded.loadSerial(input)) << output.text();
  EXPECT_EQ(saved.notify_mode, loaded.notify_mode);
  EXPECT_EQ(saved.notify_gpio_pin, loaded.notify_gpio_pin);
  EXPECT_EQ(saved.notify_tone_pin, loaded.notify_tone_pin);
  EXPECT_EQ(saved.notify_tone_id, loaded.notify_tone_id);
  EXPECT_EQ(saved.notify_tone_volume, loaded.notify_tone_volume);
  EXPECT_EQ(saved.important_notify_mode, loaded.important_notify_mode);
  EXPECT_EQ(saved.notifications_muted, loaded.notifications_muted);
  EXPECT_EQ(saved.notify_tone_bridge_enabled, loaded.notify_tone_bridge_enabled);
  EXPECT_EQ(saved.notify_tone_8bit_enabled, loaded.notify_tone_8bit_enabled);
  EXPECT_EQ(saved.notify_tone_high_drive_enabled, loaded.notify_tone_high_drive_enabled);
  EXPECT_EQ(saved.notify_pin_fix_version, loaded.notify_pin_fix_version);
  EXPECT_EQ(saved.notify_tone_resonance_hz, loaded.notify_tone_resonance_hz);
  EXPECT_EQ(saved.notify_tone_dm_id, loaded.notify_tone_dm_id);
  EXPECT_EQ(saved.notify_tone_mention_id, loaded.notify_tone_mention_id);
  EXPECT_EQ(saved.notify_tone_system_id, loaded.notify_tone_system_id);
}

TEST(CompanionNodePrefs, LegacyBuzzerRepairRunsOnce) {
  NodePrefs prefs;
  prefs.notify_gpio_pin = 45;
  prefs.notify_tone_pin = 45;

  ASSERT_TRUE(migrateLegacyNotifyPins(prefs, 45, 45, 31, 1));
  EXPECT_EQ(45, prefs.notify_gpio_pin);
  EXPECT_EQ(31, prefs.notify_tone_pin);
  EXPECT_EQ(1, prefs.notify_pin_fix_version);

  // Sharing the alert/tone pin is a valid explicit choice after migration.
  prefs.notify_tone_pin = 45;
  EXPECT_FALSE(migrateLegacyNotifyPins(prefs, 45, 45, 31, 1));
  EXPECT_EQ(45, prefs.notify_tone_pin);
}

#if 0
// Re-enable test once we can SET fem_ values in companion
TEST(CompanionNodePrefs, RxGainSettingsRoundTripIndependently) {
  NodePrefs saved;
  saved.rx_boosted_gain = 0;
  saved.radio_fem_rxgain = 1;
  saved.radio_fem_txgain = 0;

  CaptureStream output;
  ASSERT_TRUE(saved.saveSerial(output));
  EXPECT_NE(std::string::npos, output.text().find("rxgain:0"));
  EXPECT_NE(std::string::npos, output.text().find("fem_rxgain:1"));
  EXPECT_NE(std::string::npos, output.text().find("fem_txgain:0"));

  ReplayStream input("{radio:{rxgain:1,fem_rxgain:0,fem_txgain:1}}");
  NodePrefs loaded;
  loaded.rx_boosted_gain = 0;
  loaded.radio_fem_rxgain = 1;
  loaded.radio_fem_txgain = 0;

  ASSERT_TRUE(loaded.loadSerial(input));
  EXPECT_EQ(1, loaded.rx_boosted_gain);
  EXPECT_EQ(0, loaded.radio_fem_rxgain);
  EXPECT_EQ(1, loaded.radio_fem_txgain);
}
#endif

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
