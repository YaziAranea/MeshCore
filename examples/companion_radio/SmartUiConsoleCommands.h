#pragma once

#include <stddef.h>

namespace smartui {

using SmartUiConsoleExecute = bool (*)(const char*, char*, size_t);

// Human-facing aliases for the local companion console. The callback MUST be
// the production ui dispatcher, including its readonly/busy/storage gates.
// Returns false for commands owned by another dispatcher. Replies fit CMD66's
// 156-byte payload. An undersized reply buffer is rejected before any callback.
bool handleSmartUiConsoleCommand(const char* command, char* reply, size_t capacity,
                                 SmartUiConsoleExecute execute);

}  // namespace smartui
