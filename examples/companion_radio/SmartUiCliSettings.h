#pragma once

#include "DeviceSettings.h"

#include <stddef.h>

namespace smartui {

// One CMD66 request/reply must still fit the conservative 160-byte local
// companion frame when the transport adds its opcode and optional XX| prefix.
constexpr size_t SMARTUI_CLI_TEXT_MAX = 156;

// Handles the settings-only `ui` namespace. Connection, mode and Wi-Fi
// commands remain owned by the caller/ConnectionController. Returns false for
// every command outside this narrow namespace.
bool handleSmartUiSettingsCli(DeviceSettings& settings, const char* command,
                              char* reply, size_t capacity,
                              bool allow_mutation);

}  // namespace smartui
