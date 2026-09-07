#include <gtest/gtest.h>

#include "../../examples/companion_radio/ui-new/SettingUndo.h"

TEST(SettingUndo, EmptyAndUnchangedDoNotSave) {
  smartui::SettingUndo undo;
  uint8_t value = 4;
  undo.capture(value, value);
  EXPECT_FALSE(undo.available());
  EXPECT_EQ(smartui::SettingUndo::Empty, undo.apply([]() { ADD_FAILURE(); return true; }));
}

TEST(SettingUndo, RestoresOnlyRecordedFieldAndHasNoRedo) {
  smartui::SettingUndo undo;
  uint8_t tone = 7;
  uint32_t external_pin = 123456;
  undo.capture(tone, uint8_t(2));
  external_pin = 789012;
  unsigned saves = 0;
  EXPECT_EQ(smartui::SettingUndo::Applied, undo.apply([&]() {
    ++saves;
    EXPECT_EQ(2, tone);
    EXPECT_EQ(789012U, external_pin);
    return true;
  }));
  EXPECT_EQ(1U, saves);
  EXPECT_EQ(2, tone);
  EXPECT_FALSE(undo.available());
  EXPECT_EQ(smartui::SettingUndo::Empty, undo.apply([]() { ADD_FAILURE(); return true; }));
}

TEST(SettingUndo, NewerAffectedValueRejectsAllWritesAtomically) {
  smartui::SettingUndo undo;
  uint8_t system = 7, direct = 7, mention = 7, legacy = 7;
  undo.capture(system, uint8_t(1));
  undo.capture(direct, uint8_t(2));
  undo.capture(mention, uint8_t(3));
  undo.capture(legacy, uint8_t(4));
  mention = 9;  // App changed one member of the coupled common-tone choice.
  EXPECT_EQ(smartui::SettingUndo::Conflict, undo.apply([]() { ADD_FAILURE(); return true; }));
  EXPECT_EQ(7, system);
  EXPECT_EQ(7, direct);
  EXPECT_EQ(9, mention);
  EXPECT_EQ(7, legacy);
  EXPECT_FALSE(undo.available());
}

TEST(SettingUndo, CoupledCommonToneRestoresEveryChangedId) {
  smartui::SettingUndo undo;
  uint8_t system = 7, direct = 7, mention = 7, legacy = 7;
  undo.capture(system, uint8_t(1));
  undo.capture(direct, uint8_t(2));
  undo.capture(mention, uint8_t(3));
  undo.capture(legacy, uint8_t(4));
  EXPECT_EQ(4, undo.count());
  EXPECT_EQ(smartui::SettingUndo::Applied, undo.apply([]() { return true; }));
  EXPECT_EQ(1, system);
  EXPECT_EQ(2, direct);
  EXPECT_EQ(3, mention);
  EXPECT_EQ(4, legacy);
}

TEST(SettingUndo, FailedSaveRestoresCurrentValuesAndAllowsRetry) {
  smartui::SettingUndo undo;
  uint8_t theme = 2;
  float adc = 5.125f;
  undo.capture(theme, uint8_t(1));
  undo.capture(adc, 4.9f);
  EXPECT_EQ(smartui::SettingUndo::SaveFailed, undo.apply([&]() {
    EXPECT_EQ(1, theme);
    EXPECT_FLOAT_EQ(4.9f, adc);
    return false;
  }));
  EXPECT_EQ(2, theme);
  EXPECT_FLOAT_EQ(5.125f, adc);
  EXPECT_TRUE(undo.available());
  EXPECT_EQ(smartui::SettingUndo::Applied, undo.apply([]() { return true; }));
  EXPECT_EQ(1, theme);
  EXPECT_FLOAT_EQ(4.9f, adc);
}

TEST(SettingUndo, JournalCopyKeepsDestinationNotTemporarySnapshot) {
  smartui::SettingUndo undo;
  int16_t timezone = 360;
  {
    smartui::SettingUndo temporary;
    int16_t previous = 180;
    temporary.capture(timezone, previous);
    undo = temporary;
    previous = 720;
  }
  EXPECT_EQ(smartui::SettingUndo::Applied, undo.apply([]() { return true; }));
  EXPECT_EQ(180, timezone);
}

TEST(SettingUndo, OverflowCannotPartiallyRestore) {
  smartui::SettingUndo undo;
  uint8_t values[smartui::SettingUndo::CAPACITY + 1];
  for (auto& value : values) { value = 1; undo.capture(value, uint8_t(0)); }
  EXPECT_TRUE(undo.overflowed());
  EXPECT_FALSE(undo.available());
  EXPECT_EQ(smartui::SettingUndo::Empty, undo.apply([]() { ADD_FAILURE(); return true; }));
  for (auto value : values) EXPECT_EQ(1, value);
  undo.clear();
  EXPECT_FALSE(undo.overflowed());
}

struct PrivateBool {
  bool value = true;
  static bool read(void* context) { return static_cast<PrivateBool*>(context)->value; }
  static void write(void* context, bool value) { static_cast<PrivateBool*>(context)->value = value; }
};

TEST(SettingUndo, GetterSetterPreferenceHasSameConflictAndSaveGuarantees) {
  smartui::SettingUndo undo;
  PrivateBool repeat;
  uint8_t theme = 2;
  undo.capture(theme, uint8_t(1));
  undo.captureBool(&repeat, false, true, PrivateBool::read, PrivateBool::write);
  EXPECT_EQ(smartui::SettingUndo::SaveFailed, undo.apply([&]() {
    EXPECT_FALSE(repeat.value);
    EXPECT_EQ(1, theme);
    return false;
  }));
  EXPECT_TRUE(repeat.value);
  EXPECT_EQ(2, theme);
  repeat.value = false;
  EXPECT_EQ(smartui::SettingUndo::Conflict, undo.apply([]() { ADD_FAILURE(); return true; }));
  EXPECT_EQ(2, theme);
}

TEST(SettingUndo, GetterSetterOnlyUndoWorksAndClears) {
  smartui::SettingUndo undo;
  PrivateBool repeat;
  undo.captureBool(&repeat, false, true, PrivateBool::read, PrivateBool::write);
  EXPECT_TRUE(undo.available());
  EXPECT_EQ(smartui::SettingUndo::Applied, undo.apply([]() { return true; }));
  EXPECT_FALSE(repeat.value);
  EXPECT_FALSE(undo.available());
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
