#include <gtest/gtest.h>

#include <climits>

#include "../../examples/companion_radio/ui-new/ConfirmedChoice.h"

namespace {

struct ChoiceHarness {
  smartui::ConfirmedChoice choice;
  int16_t preference = 7;
  int16_t hardware_value = 7;
  unsigned commits = 0;

  void commit(int16_t value) {
    preference = value;
    hardware_value = value;
    ++commits;
  }

  bool confirm() {
    int16_t draft;
    if (!choice.selected(draft)) return false;
    if (draft != preference) commit(draft);
    return true;
  }
};

} // namespace

TEST(ConfirmedChoice, EmptyListContainsOnlyCancel) {
  smartui::ConfirmedChoice choice;
  EXPECT_EQ(0, choice.count());
  EXPECT_EQ(0, choice.cursor());
  int16_t output = 123;
  EXPECT_FALSE(choice.selected(output));
  EXPECT_EQ(123, output);
  choice.begin(7);
  choice.move(1);
  choice.move(-1);
  choice.move(INT_MIN);
  choice.move(INT_MAX);
  EXPECT_EQ(0, choice.cursor());
  EXPECT_FALSE(choice.selected(output));
}

TEST(ConfirmedChoice, OpenAndBrowseHaveNoPreferenceOrHardwareWrites) {
  ChoiceHarness harness;
  ASSERT_TRUE(harness.choice.add(-1));
  ASSERT_TRUE(harness.choice.add(7));
  ASSERT_TRUE(harness.choice.add(12));
  harness.choice.begin(harness.preference);
  EXPECT_EQ(1, harness.choice.cursor());
  harness.choice.move(1);
  harness.choice.move(1);
  harness.choice.move(-1);
  EXPECT_EQ(7, harness.preference);
  EXPECT_EQ(7, harness.hardware_value);
  EXPECT_EQ(0U, harness.commits);
}

TEST(ConfirmedChoice, CancelDoesNotCommitAndPreservesOutput) {
  ChoiceHarness harness;
  harness.choice.add(7);
  harness.choice.add(12);
  harness.choice.begin(7);
  harness.choice.move(-1);
  ASSERT_EQ(harness.choice.count(), harness.choice.cursor());
  int16_t output = 99;
  EXPECT_FALSE(harness.choice.selected(output));
  EXPECT_EQ(99, output);
  EXPECT_FALSE(harness.confirm());
  EXPECT_EQ(0U, harness.commits);
  EXPECT_EQ(7, harness.preference);
}

TEST(ConfirmedChoice, ConfirmUnchangedSelectionDoesNotWriteAgain) {
  ChoiceHarness harness;
  harness.choice.add(7);
  harness.choice.add(12);
  harness.choice.begin(harness.preference);
  EXPECT_TRUE(harness.confirm());
  EXPECT_TRUE(harness.confirm());
  EXPECT_EQ(0U, harness.commits);
}

TEST(ConfirmedChoice, ChangedSelectionCommitsOnlyWhenExplicitlyConfirmed) {
  ChoiceHarness harness;
  harness.choice.add(7);
  harness.choice.add(12);
  harness.choice.begin(harness.preference);
  harness.choice.move(1);
  EXPECT_EQ(0U, harness.commits);
  ASSERT_TRUE(harness.confirm());
  EXPECT_EQ(1U, harness.commits);
  EXPECT_EQ(12, harness.preference);
  EXPECT_EQ(12, harness.hardware_value);
  EXPECT_TRUE(harness.confirm());
  EXPECT_EQ(1U, harness.commits);
}

TEST(ConfirmedChoice, NegativeValuesAreRealOptionsNotCancelSentinels) {
  smartui::ConfirmedChoice choice;
  choice.add(-1);
  choice.add(INT16_MIN);
  choice.add(INT16_MAX);
  choice.begin(-1);
  int16_t output = 0;
  EXPECT_TRUE(choice.selected(output));
  EXPECT_EQ(-1, output);
  choice.move(1);
  EXPECT_TRUE(choice.selected(output));
  EXPECT_EQ(INT16_MIN, output);
  choice.move(1);
  EXPECT_TRUE(choice.selected(output));
  EXPECT_EQ(INT16_MAX, output);
  choice.move(1);
  EXPECT_FALSE(choice.selected(output));
}

TEST(ConfirmedChoice, UnknownActiveValueBeginsOnCancel) {
  smartui::ConfirmedChoice choice;
  choice.add(3);
  choice.add(7);
  choice.begin(99);
  EXPECT_EQ(choice.count(), choice.cursor());
  choice.move(1);
  EXPECT_EQ(0, choice.cursor());
  choice.move(-1);
  EXPECT_EQ(choice.count(), choice.cursor());
}

TEST(ConfirmedChoice, NavigationWrapsBothDirectionsIncludingCancel) {
  smartui::ConfirmedChoice choice;
  choice.add(3);
  choice.add(7);
  choice.begin(3);
  choice.move(-1);
  EXPECT_EQ(2, choice.cursor());
  choice.move(-1);
  EXPECT_EQ(1, choice.cursor());
  choice.move(2);
  EXPECT_EQ(0, choice.cursor());
  choice.move(0);
  EXPECT_EQ(0, choice.cursor());
  choice.move(INT_MAX);
  EXPECT_EQ(INT_MAX % 3, choice.cursor());
  const int previous = choice.cursor();
  choice.move(INT_MIN);
  EXPECT_EQ((previous + INT_MIN % 3 + 3) % 3, choice.cursor());
}

TEST(ConfirmedChoice, CapacityLimitRejectsExtraOptionWithoutChangingSelection) {
  smartui::ConfirmedChoice choice;
  for (int16_t i = 0; i < smartui::ConfirmedChoice::CAPACITY; ++i) {
    ASSERT_TRUE(choice.add(i));
  }
  ASSERT_EQ(32, choice.count());
  choice.begin(31);
  EXPECT_FALSE(choice.add(99));
  EXPECT_EQ(32, choice.count());
  EXPECT_EQ(31, choice.cursor());
  EXPECT_EQ(31, choice.value(31));
  EXPECT_EQ(0, choice.value(32));
  EXPECT_EQ(0, choice.value(256));
  choice.move(1);
  EXPECT_EQ(32, choice.cursor());
  int16_t output;
  EXPECT_FALSE(choice.selected(output));
  choice.move(1);
  EXPECT_EQ(0, choice.cursor());
}

TEST(ConfirmedChoice, ResetDiscardsDraftAndCanPopulateFreshList) {
  smartui::ConfirmedChoice choice;
  choice.add(3);
  choice.add(7);
  choice.begin(7);
  choice.reset();
  EXPECT_EQ(0, choice.count());
  EXPECT_EQ(0, choice.cursor());
  EXPECT_EQ(0, choice.value(1));
  choice.add(12);
  EXPECT_EQ(1, choice.cursor()); // Adding options preserves an existing Cancel.
  choice.begin(12);
  int16_t output = 0;
  EXPECT_TRUE(choice.selected(output));
  EXPECT_EQ(12, output);
}

TEST(ConfirmedChoice, ConstAccessorsAndDuplicateValuesAreDeterministic) {
  smartui::ConfirmedChoice choice;
  choice.add(7);
  choice.add(7);
  choice.begin(7);
  const auto& read_only = choice;
  EXPECT_EQ(2, read_only.count());
  EXPECT_EQ(0, read_only.cursor());
  EXPECT_EQ(7, read_only.value(1));
  int16_t output = 0;
  EXPECT_TRUE(read_only.selected(output));
  EXPECT_EQ(7, output);
  choice.add(12);
  EXPECT_EQ(0, choice.cursor());
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
