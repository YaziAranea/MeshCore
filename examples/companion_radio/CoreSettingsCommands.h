#pragma once
#include <stddef.h>
#include <stdint.h>

namespace smartui {
class MeshCoreCli;
// Small ASCII records for forms in either USB service or companion mode.
// Mutations use the original MeshCore CLI setters, never a parallel save path.
bool handleCoreSettingsCommand(const char* command, char* reply, size_t capacity,
                               bool allow_mutation, MeshCoreCli& cli,
                               const char* node_name, int8_t max_tx);
}
