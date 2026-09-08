#pragma once

#include <stdint.h>

namespace smartui {

enum class StorageRecoveryAction : uint8_t {
  None,
  RetryMount,
  FormatStorage,
  PowerOff,
};

// Pure input policy: no Arduino, filesystem, display, or power dependencies.
// Main menu: 0 Retry (default), 1 ResetData, 2 PowerOff.
// Reset confirmation: 0 Cancel (default), 1 EraseData.
// Every action requires a >=2s hold followed by a debounced release.
class StorageRecoveryPolicy {
 public:
  static constexpr uint32_t kDebounceMs = 30;
  static constexpr uint32_t kHoldMs = 2000;

  StorageRecoveryPolicy(uint32_t now, bool button_pressed)
      : raw_changed_at_(now), press_started_at_(now),
        raw_pressed_(button_pressed), stable_pressed_(button_pressed) {}

  uint8_t selectedIndex() const { return selected_; }
  bool confirmingReset() const { return confirming_reset_; }

  StorageRecoveryAction update(uint32_t now, bool button_pressed) {
    if (button_pressed != raw_pressed_) {
      raw_pressed_ = button_pressed;
      raw_changed_at_ = now;
    }
    // Unsigned elapsed time remains correct across the 32-bit millis wrap.
    if ((uint32_t)(now - raw_changed_at_) < kDebounceMs) {
      return StorageRecoveryAction::None;
    }

    // Entering recovery while BOOT is held must not select or erase anything.
    // Even an initially released input needs one stable release interval.
    if (waiting_for_initial_release_) {
      if (!raw_pressed_) {
        waiting_for_initial_release_ = false;
        stable_pressed_ = false;
      }
      return StorageRecoveryAction::None;
    }

    if (stable_pressed_ == raw_pressed_) return StorageRecoveryAction::None;
    stable_pressed_ = raw_pressed_;
    if (stable_pressed_) {
      press_started_at_ = raw_changed_at_;
      return StorageRecoveryAction::None;
    }

    // Use the edges that survived debounce, not the time of this poll. The
    // release debounce delay must not turn a 1999ms press into a 2s hold.
    const uint32_t held_ms = raw_changed_at_ - press_started_at_;
    if (held_ms < kHoldMs) {
      selected_ = (uint8_t)((selected_ + 1) % (confirming_reset_ ? 2 : 3));
      return StorageRecoveryAction::None;
    }

    if (confirming_reset_) {
      const bool erase_confirmed = selected_ == 1;
      resetMenu();
      return erase_confirmed ? StorageRecoveryAction::FormatStorage
                             : StorageRecoveryAction::None;
    }
    if (selected_ == 1) {
      confirming_reset_ = true;
      selected_ = 0;  // Cancel must be the first/default confirmation choice.
      return StorageRecoveryAction::None;
    }

    const StorageRecoveryAction action = selected_ == 2
        ? StorageRecoveryAction::PowerOff : StorageRecoveryAction::RetryMount;
    resetMenu();
    return action;
  }

 private:
  uint32_t raw_changed_at_;
  uint32_t press_started_at_;
  bool raw_pressed_;
  bool stable_pressed_;
  bool waiting_for_initial_release_ = true;
  bool confirming_reset_ = false;
  uint8_t selected_ = 0;

  void resetMenu() {
    confirming_reset_ = false;
    selected_ = 0;
  }
};

}  // namespace smartui
