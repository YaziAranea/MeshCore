#pragma once

namespace mesh {
namespace storage {

// Persist an already-mutated live settings object.  On failure restore the
// exact pre-edit snapshot, then let the caller re-apply hardware/runtime state.
// This helper is for an immediate transaction; unlike delayed UI undo, no
// unrelated event can interleave between snapshot and commit.
template <typename State, typename Save, typename RestoreRuntime>
bool persistOrRollback(State& live, const State& before, Save save,
                       RestoreRuntime restore_runtime) {
  if (save()) return true;
  live = before;
  restore_runtime();
  return false;
}

template <typename State, typename Save>
bool persistOrRollback(State& live, const State& before, Save save) {
  if (save()) return true;
  live = before;
  return false;
}

}  // namespace storage
}  // namespace mesh
