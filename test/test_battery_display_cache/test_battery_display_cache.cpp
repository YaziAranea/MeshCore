#include <gtest/gtest.h>
#include "../../examples/companion_radio/ui-new/BatteryDisplayCache.h"

TEST(BatteryDisplayCache, FirstReadIsImmediateAndSharedBetweenPages) {
  smartui::BatteryDisplayCache cache;
  int reads = 0;
  auto adc = [&reads]() -> uint16_t { ++reads; return 3800; };
  EXPECT_EQ(3800U, cache.read(0, 1000, adc));
  EXPECT_EQ(3, reads);
  EXPECT_EQ(3800U, cache.read(999, 1000, adc));
  EXPECT_EQ(3, reads);
  EXPECT_EQ(3800U, cache.read(1000, 1000, adc));
  EXPECT_EQ(6, reads);
}

TEST(BatteryDisplayCache, RisingAndFallingStepsHaveNoHistoricSmoothing) {
  smartui::BatteryDisplayCache cache;
  uint16_t voltage = 3700;
  auto adc = [&voltage]() -> uint16_t { return voltage; };
  EXPECT_EQ(3700U, cache.read(0, 1000, adc));
  voltage = 4200;
  EXPECT_EQ(4200U, cache.read(1000, 1000, adc));
  voltage = 2900;
  EXPECT_EQ(2900U, cache.read(2000, 1000, adc));
}

TEST(BatteryDisplayCache, SlowPaperRefreshUsesPresentVoltageImmediately) {
  smartui::BatteryDisplayCache cache;
  EXPECT_EQ(4100U, cache.read(100, 1000, []() { return 4100; }));
  EXPECT_EQ(3600U, cache.read(60100, 1000, []() { return 3600; }));
  EXPECT_EQ(3500U, cache.read(3600100, 1000, []() { return 3500; }));
}

TEST(BatteryDisplayCache, WakeAndCalibrationInvalidationBypassCacheInterval) {
  smartui::BatteryDisplayCache cache;
  EXPECT_EQ(3800U, cache.read(100, 1000, []() { return 3800; }));
  cache.invalidate();
  EXPECT_EQ(4000U, cache.read(110, 1000, []() { return 4000; }));
}

TEST(BatteryDisplayCache, OneHighOrLowAdcSpikeDoesNotMoveTheDisplay) {
  smartui::BatteryDisplayCache cache;
  const uint16_t samples[] = {3800, 65535, 3801, 1, 3799, 3800};
  int at = 0;
  auto adc = [&]() { return samples[at++]; };
  EXPECT_EQ(3801U, cache.read(0, 1000, adc));
  EXPECT_EQ(3799U, cache.read(1000, 1000, adc));
  EXPECT_EQ(6, at);
}

TEST(BatteryDisplayCache, UnavailableAdcDoesNotLeaveAStaleVoltageOnScreen) {
  smartui::BatteryDisplayCache cache;
  EXPECT_EQ(3800U, cache.read(0, 1000, []() { return 3800; }));
  EXPECT_EQ(0U, cache.read(1000, 1000, []() { return 0; }));
  EXPECT_EQ(2500U, cache.read(2000, 1000, []() { return 2500; }));
}

TEST(BatteryDisplayCache, MillisWrapKeepsTheOneSecondCacheInterval) {
  smartui::BatteryDisplayCache cache;
  EXPECT_EQ(3800U, cache.read(UINT32_MAX - 499U, 1000, []() { return 3800; }));
  EXPECT_EQ(3800U, cache.read(499, 1000, []() { return 4000; }));
  EXPECT_EQ(4000U, cache.read(500, 1000, []() { return 4000; }));
}

TEST(BatteryDisplayCache, MissingSampleDoesNotHideTheTwoPresentReadings) {
  smartui::BatteryDisplayCache cache;
  const uint16_t samples[] = {0, 3799, 3801};
  int at = 0;
  EXPECT_EQ(3799U, cache.read(0, 1000, [&]() { return samples[at++]; }));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
