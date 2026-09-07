#include <gtest/gtest.h>
#include "../../examples/companion_radio/ui-new/QuickTargetUi.h"

TEST(QuickTargetUi, InitialsAreCaseInsensitiveAndEveryNameHasAGroup) {
  EXPECT_EQ(0, smartui::contactInitialGroup("Alex"));
  EXPECT_EQ(0, smartui::contactInitialGroup(" alex"));
  EXPECT_EQ(26, smartui::contactInitialGroup("Анна"));
  EXPECT_EQ(26, smartui::contactInitialGroup("анна"));
  EXPECT_EQ(smartui::contactInitialGroup("Елена"), smartui::contactInitialGroup("ёж"));
  EXPECT_EQ(57, smartui::contactInitialGroup("я"));
  EXPECT_EQ(58, smartui::contactInitialGroup("123"));
  EXPECT_EQ(58, smartui::contactInitialGroup(""));
  EXPECT_EQ(58, smartui::contactInitialGroup(nullptr));
  EXPECT_EQ(58, smartui::contactInitialGroup("\xD0"));
  EXPECT_EQ(58, smartui::contactInitialGroup("🚀"));
  for (uint8_t i = 0; i < smartui::CONTACT_INITIAL_GROUPS; ++i) {
    char label[3] = {};
    smartui::contactInitialLabel(i, label);
    EXPECT_EQ(i, smartui::contactInitialGroup(label));
  }
}

TEST(QuickTargetUi, RecentKeysAreBoundedDeduplicatedAndStableIds) {
  smartui::RecentRecipientKeys<2> recent;
  uint8_t a[2] = {1, 2}, b[2] = {1, 3}, c[2] = {3, 4}, d[2] = {4, 5};
  EXPECT_EQ(0, recent.count());
  EXPECT_EQ(nullptr, recent.at(0));
  recent.remember(a); recent.remember(b); recent.remember(c);
  EXPECT_EQ(3, recent.count());
  EXPECT_EQ(0, memcmp(c, recent.at(0), 2));
  recent.remember(a);
  EXPECT_EQ(3, recent.count());
  EXPECT_EQ(0, memcmp(a, recent.at(0), 2));
  EXPECT_EQ(0, memcmp(c, recent.at(1), 2));
  recent.remember(d);
  EXPECT_EQ(0, memcmp(d, recent.at(0), 2));
  EXPECT_EQ(0, memcmp(a, recent.at(1), 2));
  EXPECT_EQ(0, memcmp(c, recent.at(2), 2));
  EXPECT_EQ(nullptr, recent.at(3));
  recent.remember(nullptr);
  EXPECT_EQ(3, recent.count());
}

TEST(QuickTargetUi, GpsStatesDoNotDependOnColor) {
  EXPECT_STREQ("OFF", smartui::gpsClockStateWord(false, false));
  EXPECT_STREQ("OFF", smartui::gpsClockStateWord(false, true));
  EXPECT_STREQ("...", smartui::gpsClockStateWord(true, false));
  EXPECT_STREQ("FIX", smartui::gpsClockStateWord(true, true));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
