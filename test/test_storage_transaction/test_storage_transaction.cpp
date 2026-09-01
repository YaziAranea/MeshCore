#include <gtest/gtest.h>

#include "helpers/StorageTransaction.h"

using mesh::storage::RecoveryCandidate;

TEST(StorageTransaction, PrefersCommittedPrimary) {
  EXPECT_EQ(RecoveryCandidate::PRIMARY,
            mesh::storage::chooseRecoveryCandidate(true, true, true));
  EXPECT_EQ(RecoveryCandidate::PRIMARY,
            mesh::storage::chooseRecoveryCandidate(true, false, false));
}

TEST(StorageTransaction, RecoversValidatedTemporaryAfterRotationInterruption) {
  EXPECT_EQ(RecoveryCandidate::TEMPORARY,
            mesh::storage::chooseRecoveryCandidate(false, true, true));
  EXPECT_EQ(RecoveryCandidate::TEMPORARY,
            mesh::storage::chooseRecoveryCandidate(false, true, false));
}

TEST(StorageTransaction, FallsBackToBackupWhenNewGenerationIsIncomplete) {
  EXPECT_EQ(RecoveryCandidate::BACKUP,
            mesh::storage::chooseRecoveryCandidate(false, false, true));
  EXPECT_EQ(RecoveryCandidate::NONE,
            mesh::storage::chooseRecoveryCandidate(false, false, false));
}

TEST(StorageTransaction, Crc32MatchesStandardVectorAndStreamingUpdates) {
  static const uint8_t input[] = "123456789";
  mesh::storage::Crc32 one_shot;
  one_shot.update(input, sizeof(input) - 1);
  EXPECT_EQ(0xCBF43926u, one_shot.value());

  mesh::storage::Crc32 chunked;
  chunked.update(input, 2);
  chunked.update(input + 2, 3);
  chunked.update(input + 5, 4);
  EXPECT_EQ(one_shot.value(), chunked.value());
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
