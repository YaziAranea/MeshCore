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

TEST(DeferredSavePolicy, FailedWriteRetryIsBoundedAndNotBusyLooped) {
  mesh::storage::DeferredSavePolicy policy;
  policy.schedule(100u, 5u);
  ASSERT_TRUE(policy.due(105u, 30u));

  policy.retryFrom(105u, 5u);
  EXPECT_FALSE(policy.due(109u, 30u));
  EXPECT_TRUE(policy.due(110u, 30u));
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
