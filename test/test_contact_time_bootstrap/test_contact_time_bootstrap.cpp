#include <gtest/gtest.h>

#include "helpers/ContactTimeBootstrap.h"

TEST(ContactTimeBootstrap, SelectsOnlyTheNewestPlausibleContactTimestamp) {
  uint32_t latest = 0;
  latest = selectContactTimeBootstrapCandidate(latest, MESH_RTC_TRUST_MIN - 1U);
  EXPECT_EQ(0U, latest);
  latest = selectContactTimeBootstrapCandidate(latest, MESH_RTC_TRUST_MIN + 20U);
  latest = selectContactTimeBootstrapCandidate(latest, MESH_RTC_TRUST_MIN + 10U);
  EXPECT_EQ(MESH_RTC_TRUST_MIN + 20U, latest);
}

TEST(ContactTimeBootstrap, ProducesAOneSecondEstimateWithoutOverflow) {
  uint32_t estimate = 0;
  EXPECT_TRUE(makeContactTimeEstimate(MESH_RTC_TRUST_MIN, estimate));
  EXPECT_EQ(MESH_RTC_TRUST_MIN + 1U, estimate);

  EXPECT_FALSE(makeContactTimeEstimate(0, estimate));
  EXPECT_FALSE(makeContactTimeEstimate(MESH_RTC_TRUST_MAX, estimate));
  EXPECT_FALSE(makeContactTimeEstimate(UINT32_MAX, estimate));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
