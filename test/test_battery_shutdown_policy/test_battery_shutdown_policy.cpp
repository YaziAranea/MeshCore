#include <gtest/gtest.h>

#include "../../examples/companion_radio/ui-new/BatteryShutdownPolicy.h"

TEST(BatteryShutdownPolicy, NormalToggleSelectsNormalOrEmergencyFloor) {
  EXPECT_EQ(3200U, smartui::batteryShutdownThreshold(true, 3200, 2700));
  EXPECT_EQ(2700U, smartui::batteryShutdownThreshold(false, 3200, 2700));
  EXPECT_EQ(0U, smartui::batteryShutdownThreshold(false, 3200, 0));
}

TEST(BatteryShutdownPolicy, ThreeConsecutiveLowReadingsAreRequired) {
  uint8_t strikes = 0;
  strikes = smartui::nextLowBatteryStrikeCount(strikes, 3199, 3200, 3);
  EXPECT_EQ(1U, strikes);
  strikes = smartui::nextLowBatteryStrikeCount(strikes, 3100, 3200, 3);
  EXPECT_EQ(2U, strikes);
  strikes = smartui::nextLowBatteryStrikeCount(strikes, 3000, 3200, 3);
  EXPECT_EQ(3U, strikes);
}

TEST(BatteryShutdownPolicy, ExactlyAtThresholdIsNotLowAndResetsHistory) {
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(2, 3200, 3200, 3));
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(2, 3300, 3200, 3));
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(2, 2700, 2700, 3));
}

TEST(BatteryShutdownPolicy, EmergencyFloorStillRequiresConsecutiveValidReadings) {
  const uint16_t threshold = smartui::batteryShutdownThreshold(false, 3200, 2700);
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(2, 2800, threshold, 3));
  EXPECT_EQ(1U, smartui::nextLowBatteryStrikeCount(0, 2699, threshold, 3));
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(2, 2500, threshold, 3));
}

TEST(BatteryShutdownPolicy, SevereUndervoltageNeverFailsOpen) {
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(2, 2499, 3200, 3));
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(2, 2000, 3200, 3));
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(2, 1, 3200, 3));
}

TEST(BatteryShutdownPolicy, AbsentReadingDoesNotCountOrEraseEvidence) {
  EXPECT_FALSE(smartui::batteryReading(0).valid);
  EXPECT_EQ(2U, smartui::nextLowBatteryStrikeCount(2, 0, 3200, 3));
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(0, 0, 3200, 3));
  EXPECT_EQ(1U, smartui::nextLowBatteryStrikeCount(0, 2500, 3200, 3));
}

TEST(BatteryShutdownPolicy, ZeroThresholdAlwaysResets) {
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(3, 2600, 0, 3));
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(3, 0, 0, 3));
}

TEST(BatteryShutdownPolicy, StrikeCountSaturatesAndCannotOverflow) {
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(3, 2600, 3200, 3));
  EXPECT_EQ(3U, smartui::nextLowBatteryStrikeCount(255, 2600, 3200, 3));
  EXPECT_EQ(255U, smartui::nextLowBatteryStrikeCount(254, 2600, 3200, 255));
  EXPECT_EQ(255U, smartui::nextLowBatteryStrikeCount(255, 2600, 3200, 255));
  EXPECT_EQ(0U, smartui::nextLowBatteryStrikeCount(0, 2600, 3200, 0));
}

TEST(BatteryShutdownPolicy, RecoveryBreaksTheConsecutiveSequence) {
  uint8_t strikes = smartui::nextLowBatteryStrikeCount(1, 3100, 3200, 3);
  ASSERT_EQ(2U, strikes);
  strikes = smartui::nextLowBatteryStrikeCount(strikes, 3250, 3200, 3);
  ASSERT_EQ(0U, strikes);
  EXPECT_EQ(1U, smartui::nextLowBatteryStrikeCount(strikes, 3100, 3200, 3));
}

TEST(BatteryShutdownPolicy, SafetyMedianIgnoresAbsentSamples) {
  auto all = smartui::medianBatteryReading(3700, 2500, 2600);
  ASSERT_TRUE(all.valid);
  EXPECT_EQ(2600U, all.millivolts);

  auto two = smartui::medianBatteryReading(0, 2600, 2500);
  ASSERT_TRUE(two.valid);
  EXPECT_EQ(2500U, two.millivolts);

  auto one = smartui::medianBatteryReading(0, 0, 2499);
  ASSERT_TRUE(one.valid);
  EXPECT_EQ(2499U, one.millivolts);

  EXPECT_FALSE(smartui::medianBatteryReading(0, 0, 0).valid);
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
