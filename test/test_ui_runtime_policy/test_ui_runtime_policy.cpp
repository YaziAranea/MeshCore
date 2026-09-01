#include <gtest/gtest.h>

#include "../../examples/companion_radio/ui-new/UiTiming.h"
#include "../../examples/companion_radio/ui-new/ClockUptime.h"
#include "../../examples/companion_radio/ui-new/AdcCalibrationUi.h"
#include "../../src/helpers/AdcCalibration.h"
#include "../../src/helpers/RTCClockQuality.h"

TEST(UiTiming, DeadlineComparisonSurvivesMillisWrap) {
  const uint32_t before_wrap = 0xFFFFFFF0U;
  const uint32_t deadline = before_wrap + 32U;

  EXPECT_TRUE(smartui::deadlinePending(before_wrap, deadline));
  EXPECT_TRUE(smartui::deadlinePending(0x0000000FU, deadline));
  EXPECT_TRUE(smartui::deadlineReached(0x00000010U, deadline));
  EXPECT_TRUE(smartui::deadlineReached(0x00000020U, deadline));
}

TEST(UiTiming, ElapsedComparisonSurvivesMillisWrap) {
  const uint32_t started = 0xFFFFFFF8U;
  EXPECT_FALSE(smartui::elapsedAtLeast(0x00000005U, started, 14U));
  EXPECT_TRUE(smartui::elapsedAtLeast(0x00000006U, started, 14U));
}

TEST(UiTiming, OptionalAndImmediateDeadlinesKeepZeroSemantics) {
  EXPECT_FALSE(smartui::optionalDeadlinePending(100U, 0U));
  EXPECT_TRUE(smartui::deadlineDueOrImmediate(0xFFFFFFF0U, 0U));
}

TEST(ClockUptime, UsesCompactLowChurnUnits) {
  char text[12];
  smartui::formatClockUptime(text, sizeof(text), 59);
  EXPECT_STREQ("U 0m", text);
  smartui::formatClockUptime(text, sizeof(text), 12 * 60);
  EXPECT_STREQ("U 12m", text);
  smartui::formatClockUptime(text, sizeof(text), 7 * 3600);
  EXPECT_STREQ("U 7h", text);
  smartui::formatClockUptime(text, sizeof(text), 3 * 86400);
  EXPECT_STREQ("U 3d", text);
  smartui::formatClockUptime(text, sizeof(text), 2000ULL * 86400ULL);
  EXPECT_STREQ("U 999+d", text);
}

TEST(ClockUptime, PlacementUsesMeasuredWidthAndNeverOverlapsNeighbours) {
  EXPECT_EQ(97, smartui::clockUptimeRightEdge(50, 100, 27));
  EXPECT_EQ(-1, smartui::clockUptimeRightEdge(70, 100, 27));
  EXPECT_EQ(-1, smartui::clockUptimeRightEdge(10, 10, 5));
}

TEST(RtcClockQuality, PlausibilityDoesNotAcceptBootSeedsOrAbsurdDates) {
  EXPECT_FALSE(meshRtcTimestampPlausible(0));
  EXPECT_FALSE(meshRtcTimestampPlausible(MESH_RTC_TRUST_MIN - 1));
  EXPECT_TRUE(meshRtcTimestampPlausible(MESH_RTC_TRUST_MIN));
  EXPECT_TRUE(meshRtcTimestampPlausible(MESH_RTC_TRUST_MAX));
  EXPECT_FALSE(meshRtcTimestampPlausible(MESH_RTC_TRUST_MAX + 1U));
}

TEST(AdcCalibration, AcceptsResetAndSaneBoardSpecificWindow) {
  float applied = -1.0f;
  EXPECT_TRUE(mesh::normalizeAdcMultiplier(0.0f, 4.9f, applied));
  EXPECT_FLOAT_EQ(4.9f, applied);
  EXPECT_TRUE(mesh::normalizeAdcMultiplier(3.675f, 4.9f, applied));
  EXPECT_TRUE(mesh::normalizeAdcMultiplier(6.125f, 4.9f, applied));
  EXPECT_FALSE(mesh::normalizeAdcMultiplier(3.674f, 4.9f, applied));
  EXPECT_FALSE(mesh::normalizeAdcMultiplier(6.126f, 4.9f, applied));
  EXPECT_FALSE(mesh::normalizeAdcMultiplier(NAN, 4.9f, applied));
}

TEST(AdcCalibration, ConversionIsRoundedAndSaturating) {
  EXPECT_EQ(0U, mesh::saturatingBatteryMilliVolts(NAN));
  EXPECT_EQ(0U, mesh::saturatingBatteryMilliVolts(-1.0f));
  EXPECT_EQ(2500U, mesh::saturatingBatteryMilliVolts(2499.6f));
  EXPECT_EQ(65535U, mesh::saturatingBatteryMilliVolts(100000.0f));
}

TEST(AdcCalibration, FactoryResetHasDistinctNonDestructiveGesture) {
  EXPECT_TRUE(smartui::adcFactoryResetGesture(true, true, false, 2));
  EXPECT_FALSE(smartui::adcFactoryResetGesture(true, true, false, 1));
  EXPECT_FALSE(smartui::adcFactoryResetGesture(true, true, true, 2));
  EXPECT_FALSE(smartui::adcFactoryResetGesture(false, true, false, 2));
  EXPECT_FALSE(smartui::adcFactoryResetGesture(true, false, false, 2));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
