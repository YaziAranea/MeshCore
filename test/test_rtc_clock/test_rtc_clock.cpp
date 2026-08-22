#include <gtest/gtest.h>

#include <MeshCore.h>

class FakeRTCClock : public mesh::RTCClock {
  uint32_t _now;

public:
  explicit FakeRTCClock(uint32_t now) : _now(now) { }

  uint32_t getCurrentTime() override { return _now; }
  void setCurrentTime(uint32_t time) override { _now = time; }
};

TEST(RTCClock, BackwardCorrectionRebasesUniqueTimestampFloor) {
  FakeRTCClock clock(2000);

  EXPECT_EQ(2000U, clock.getCurrentTimeUnique());
  EXPECT_EQ(2001U, clock.getCurrentTimeUnique());

  clock.setCurrentTimeAndRebaseUnique(1000);

  EXPECT_EQ(1000U, clock.getCurrentTime());
  EXPECT_EQ(1000U, clock.getCurrentTimeUnique());
  EXPECT_EQ(1001U, clock.getCurrentTimeUnique());
}

TEST(RTCClock, OrdinaryClockSetPreservesUniqueTimestampFloor) {
  FakeRTCClock clock(2000);

  EXPECT_EQ(2000U, clock.getCurrentTimeUnique());
  EXPECT_EQ(2001U, clock.getCurrentTimeUnique());

  clock.setCurrentTime(1000);

  EXPECT_EQ(2002U, clock.getCurrentTimeUnique());
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
