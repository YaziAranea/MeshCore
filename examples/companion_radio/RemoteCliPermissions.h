#pragma once

#include <stddef.h>
#include <stdint.h>

namespace smartui {
// Local provisioning only. Remote command dispatch must reject this namespace.
using ReadRemoteCliPermission = bool (*)(const uint8_t key[32], bool& enabled);
using WriteRemoteCliPermission = bool (*)(const uint8_t key[32], bool enabled);
bool handleRemoteCliPermissionCommand(const char* command, char* reply, size_t capacity,
    bool writable, bool busy, ReadRemoteCliPermission read, WriteRemoteCliPermission write);
}
