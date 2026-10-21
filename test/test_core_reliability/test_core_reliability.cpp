#include <gtest/gtest.h>

#include "helpers/DeferredSavePolicy.h"
#include "helpers/PrefsTransaction.h"
#include "helpers/WrapTimer.h"

TEST(DeferredSavePolicy, FutureDeadlineDoesNotBecomeImmediateWork) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(1000u, 5000u);

  EXPECT_TRUE(policy.pending());
  EXPECT_FALSE(policy.due(5999u, 30000u));
  EXPECT_TRUE(policy.due(6000u, 30000u));
}

TEST(DeferredSavePolicy, RepeatedChangesCannotExtendPastMaximumAge) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(1000u, 5000u);
  policy.schedule(5000u, 5000u);
  policy.schedule(9000u, 5000u);

  EXPECT_FALSE(policy.due(9999u, 30000u));
  policy.schedule(30500u, 5000u);
  EXPECT_FALSE(policy.due(30999u, 30000u));
  EXPECT_TRUE(policy.due(31000u, 30000u));
}

TEST(DeferredSavePolicy, DeadlineSurvivesUint32Wrap) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(0xFFFFFFF0u, 50u);

  EXPECT_FALSE(policy.due(20u, 30000u));
  EXPECT_TRUE(policy.due(34u, 30000u));
  policy.clear();
  EXPECT_FALSE(policy.pending());
}

TEST(DeferredSavePolicy, RetriesBackOffWithoutNewChangesBypassingOrExtendingDelay) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(1000u, 5000u);
  uint32_t now = 6000u;
  ASSERT_TRUE(policy.due(now, 30000u));

  for (uint32_t delay : {5000u, 10000u, 20000u, 40000u, 80000u,
                         160000u, 300000u, 300000u}) {
    policy.retryFrom(now, 5000u, 300000u);
    for (uint32_t elapsed : {0u, delay / 2, delay - 1}) {
      policy.schedule(now + elapsed, 5000u);
      EXPECT_TRUE(policy.pending());
      EXPECT_FALSE(policy.due(now + elapsed, 30000u));
    }
    now += delay;
    policy.schedule(now, 5000u);
    EXPECT_TRUE(policy.due(now, 30000u));
  }
}

TEST(DeferredSavePolicy, RetryDeadlineSurvivesUint32Wrap) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(0xFFFFE000u, 5000u);
  policy.retryFrom(0xFFFFFFF0u, 5000u, 300000u);
  policy.schedule(4983u, 5000u);
  EXPECT_FALSE(policy.due(4983u, 30000u));
  EXPECT_TRUE(policy.due(4984u, 30000u));
}

TEST(DeferredSavePolicy, ExplicitFlushBypassesBackoffButFailureKeepsDirtyAndDeadline) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(1000u, 5000u);
  policy.retryFrom(6000u, 5000u, 300000u);
  policy.retryFrom(11000u, 5000u, 300000u);
  unsigned saves = 0;
  EXPECT_FALSE(mesh::storage::flushDeferredSave(
      policy, false, [&saves]() { ++saves; return false; }));
  EXPECT_EQ(1u, saves);
  EXPECT_TRUE(policy.pending());
  EXPECT_FALSE(policy.due(20999u, 30000u));
  EXPECT_TRUE(policy.due(21000u, 30000u));

  EXPECT_TRUE(mesh::storage::flushDeferredSave(
      policy, false, [&saves]() { ++saves; return true; }));
  EXPECT_EQ(2u, saves);
  EXPECT_FALSE(policy.pending());
  // Successful explicit flush resets the retry ladder as well as the batch.
  policy.schedule(12000u, 5000u);
  EXPECT_FALSE(policy.due(16999u, 30000u));
  EXPECT_TRUE(policy.due(17000u, 30000u));
  policy.retryFrom(17000u, 5000u, 300000u);
  EXPECT_FALSE(policy.due(21999u, 30000u));
  EXPECT_TRUE(policy.due(22000u, 30000u));
}

TEST(DeferredSavePolicy, RecoveryQuarantineNeverReplaysDirtyRamState) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(100u, 5000u);
  unsigned saves = 0;

  EXPECT_FALSE(mesh::storage::flushDeferredSave(
      policy, true, [&saves]() {
        ++saves;
        return true;
      }));
  EXPECT_EQ(0u, saves);
  EXPECT_TRUE(policy.pending());
}

TEST(DeferredSavePolicy, SuccessfulFlushWritesOnceAndClearsPendingState) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(100u, 5000u);
  unsigned saves = 0;

  EXPECT_TRUE(mesh::storage::flushDeferredSave(
      policy, false, [&saves]() {
        ++saves;
        return true;
      }));
  EXPECT_EQ(1u, saves);
  EXPECT_FALSE(policy.pending());
}

TEST(PrefsTransaction, KeepsMutationWhenSaveSucceeds) {
  struct State { int value; } live = {2};
  const State before = {1};
  bool runtime_restored = false;

  EXPECT_TRUE(mesh::storage::persistOrRollback(
      live, before, []() { return true; },
      [&runtime_restored]() { runtime_restored = true; }));
  EXPECT_EQ(2, live.value);
  EXPECT_FALSE(runtime_restored);
}

TEST(PrefsTransaction, RestoresSnapshotAndRuntimeWhenSaveFails) {
  struct State { int value; } live = {2};
  const State before = {1};
  int runtime_value = live.value;

  EXPECT_FALSE(mesh::storage::persistOrRollback(
      live, before, []() { return false; },
      [&]() { runtime_value = live.value; }));
  EXPECT_EQ(1, live.value);
  EXPECT_EQ(1, runtime_value);
}

TEST(WrapTimer, BleThrottleExpiresAcrossMillisWrap) {
  EXPECT_FALSE(mesh::timing::elapsedAtLeast(1049u, 1000u, 60u));
  EXPECT_TRUE(mesh::timing::elapsedAtLeast(1060u, 1000u, 60u));
  EXPECT_FALSE(mesh::timing::elapsedAtLeast(20u, 0xFFFFFFF0u, 50u));
  EXPECT_TRUE(mesh::timing::elapsedAtLeast(34u, 0xFFFFFFF0u, 50u));
  EXPECT_TRUE(mesh::timing::elapsedAtLeast(0x00001000u, 0xD0000000u, 60u));
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
