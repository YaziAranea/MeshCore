#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

namespace mesh {
namespace companion {

enum class OfflineSyncOutcome : uint8_t {
  empty,
  backpressured,
  committed
};

// Frame must expose len, buf, ui_generation and ui_flags.  The helper is kept
// independent of MyMesh so the exact queue transition can run in host tests.
template <typename Frame>
int peekOfflineFrame(const Frame frames[], int count, uint8_t dest[],
                     uint32_t& generation, uint8_t& flags) {
  generation = 0;
  flags = 0;
  if (frames == nullptr || dest == nullptr || count <= 0) return 0;
  const Frame& head = frames[0];
  if (head.len == 0) return 0;
  memcpy(dest, head.buf, head.len);
  generation = head.ui_generation;
  flags = head.ui_flags;
  return head.len;
}

template <typename Frame>
void commitOfflineFrame(Frame frames[], int& count) {
  if (frames == nullptr || count <= 0) return;
  --count;
  for (int i = 0; i < count; ++i) frames[i] = frames[i + 1];
}

// Transport acceptance is intentionally the commit point supported by the
// current companion protocol.  It protects against immediate queue
// backpressure.  A disconnect after acceptance still needs a future app ACK
// protocol for end-to-end delivery and deduplication.
template <typename Peek, typename Write, typename Commit, typename OnCommitted>
OfflineSyncOutcome syncNextOfflineFrame(uint8_t out_frame[],
                                        uint8_t no_more_code,
                                        Peek peek, Write write,
                                        Commit commit,
                                        OnCommitted on_committed) {
  uint32_t generation = 0;
  uint8_t flags = 0;
  const int len = peek(out_frame, generation, flags);
  if (len <= 0) {
    out_frame[0] = no_more_code;
    write(out_frame, 1);
    return OfflineSyncOutcome::empty;
  }

  if (write(out_frame, static_cast<size_t>(len)) !=
      static_cast<size_t>(len)) {
    return OfflineSyncOutcome::backpressured;
  }

  commit();
  on_committed(generation, flags);
  return OfflineSyncOutcome::committed;
}

}  // namespace companion
}  // namespace mesh
