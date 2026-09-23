#include <gtest/gtest.h>

#include <initializer_list>
#include <vector>

#include "helpers/OfflineQueueSync.h"

namespace {

struct Frame {
  uint8_t len = 0;
  uint8_t buf[16] = {};
  uint32_t ui_generation = 0;
  uint8_t ui_flags = 0;
};

struct FakeSerial {
  size_t accepted = 0;
  unsigned calls = 0;
  std::vector<uint8_t> last;

  size_t writeFrame(const uint8_t* frame, size_t len) {
    ++calls;
    last.assign(frame, frame + len);
    return accepted > len ? len : accepted;
  }
};

struct Harness {
  Frame queue[3] = {};
  int count = 0;
  FakeSerial serial;
  unsigned commits = 0;
  unsigned hooks = 0;
  uint32_t hook_generation = 0;
  uint8_t hook_flags = 0;
  uint8_t out[16] = {};

  void push(std::initializer_list<uint8_t> bytes, uint32_t generation,
            uint8_t flags) {
    Frame& frame = queue[count++];
    frame.len = static_cast<uint8_t>(bytes.size());
    unsigned i = 0;
    for (uint8_t byte : bytes) frame.buf[i++] = byte;
    frame.ui_generation = generation;
    frame.ui_flags = flags;
  }

  mesh::companion::OfflineSyncOutcome sync() {
    return mesh::companion::syncNextOfflineFrame(
        out, 0x7f,
        [this](uint8_t* dest, uint32_t& generation, uint8_t& flags) {
          return mesh::companion::peekOfflineFrame(
              queue, count, dest, generation, flags);
        },
        [this](const uint8_t* frame, size_t len) {
          return serial.writeFrame(frame, len);
        },
        [this]() {
          ++commits;
          mesh::companion::commitOfflineFrame(queue, count);
        },
        [this](uint32_t generation, uint8_t flags) {
          ++hooks;
          hook_generation = generation;
          hook_flags = flags;
        });
  }
};

}  // namespace

TEST(OfflineQueueSync, ZeroAcceptancePreservesHeadAndUnreadState) {
  Harness h;
  h.push({0x11, 0x22, 0x33}, 41u, 0x01u);
  h.serial.accepted = 0;

  EXPECT_EQ(mesh::companion::OfflineSyncOutcome::backpressured, h.sync());
  EXPECT_EQ(1, h.count);
  EXPECT_EQ(0u, h.commits);
  EXPECT_EQ(0u, h.hooks);
  EXPECT_EQ(41u, h.queue[0].ui_generation);
}

TEST(OfflineQueueSync, PartialAcceptancePreservesHeadAndUnreadState) {
  Harness h;
  h.push({0x11, 0x22, 0x33}, 42u, 0x03u);
  h.serial.accepted = 2;

  EXPECT_EQ(mesh::companion::OfflineSyncOutcome::backpressured, h.sync());
  EXPECT_EQ(1, h.count);
  EXPECT_EQ(0u, h.commits);
  EXPECT_EQ(0u, h.hooks);
  EXPECT_EQ(42u, h.queue[0].ui_generation);
}

TEST(OfflineQueueSync, FullAcceptanceCommitsOnceAndReportsTypedGeneration) {
  Harness h;
  h.push({0x11, 0x22, 0x33}, 43u, 0x03u);
  h.push({0x44}, 44u, 0x00u);
  h.serial.accepted = 3;

  EXPECT_EQ(mesh::companion::OfflineSyncOutcome::committed, h.sync());
  EXPECT_EQ(1, h.count);
  EXPECT_EQ(1u, h.commits);
  EXPECT_EQ(1u, h.hooks);
  EXPECT_EQ(43u, h.hook_generation);
  EXPECT_EQ(0x03u, h.hook_flags);
  EXPECT_EQ(44u, h.queue[0].ui_generation);
  EXPECT_EQ((std::vector<uint8_t>{0x11, 0x22, 0x33}), h.serial.last);
}

TEST(OfflineQueueSync, EmptyQueueWritesNoMoreResponseWithoutCommitOrHook) {
  Harness h;
  h.serial.accepted = 1;

  EXPECT_EQ(mesh::companion::OfflineSyncOutcome::empty, h.sync());
  EXPECT_EQ(0, h.count);
  EXPECT_EQ(0u, h.commits);
  EXPECT_EQ(0u, h.hooks);
  ASSERT_EQ(1u, h.serial.last.size());
  EXPECT_EQ(0x7fu, h.serial.last[0]);
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
