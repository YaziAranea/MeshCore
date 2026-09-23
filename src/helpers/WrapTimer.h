#pragma once

#include <stdint.h>

namespace mesh {
namespace timing {

inline bool elapsedAtLeast(uint32_t now, uint32_t since, uint32_t interval) {
  return static_cast<uint32_t>(now - since) >= interval;
}

}  // namespace timing
}  // namespace mesh
