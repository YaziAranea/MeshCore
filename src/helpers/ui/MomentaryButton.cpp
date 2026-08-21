#include "MomentaryButton.h"

#define MULTI_CLICK_WINDOW_MS  280

#ifndef MOMENTARY_BUTTON_FORCE_INTERNAL_PULL
  #define MOMENTARY_BUTTON_FORCE_INTERNAL_PULL 0
#endif

MomentaryButton::MomentaryButton(int8_t pin, int long_press_millis, bool reverse, bool pulldownup, bool multiclick) { 
  _pin = pin;
  _reverse = reverse;
  _pull = pulldownup;
  down_at = 0; 
  prev = _reverse ? HIGH : LOW;
  cancel = 0;
  _long_millis = long_press_millis;
  _threshold = 0;
  _click_count = 0;
  _last_click_time = 0;
  _multi_click_window = multiclick ? MULTI_CLICK_WINDOW_MS : 0;
  _pending_click = false;
  _immediate_click_until = 0;
}

MomentaryButton::MomentaryButton(int8_t pin, int long_press_millis, int analog_threshold) {
  _pin = pin;
  _reverse = false;
  _pull = false;
  down_at = 0;
  prev = LOW;
  cancel = 0;
  _long_millis = long_press_millis;
  _threshold = analog_threshold;
  _click_count = 0;
  _last_click_time = 0;
  _multi_click_window = MULTI_CLICK_WINDOW_MS;
  _pending_click = false;
  _immediate_click_until = 0;
}

void MomentaryButton::begin() {
  reconfigure();
  resetState(false);
}

void MomentaryButton::reconfigure() {
  if (_pin >= 0 && _threshold == 0) {
#if MOMENTARY_BUTTON_FORCE_INTERNAL_PULL
    pinMode(_pin, _reverse ? INPUT_PULLUP : INPUT_PULLDOWN);
#else
    pinMode(_pin, _pull ? (_reverse ? INPUT_PULLUP : INPUT_PULLDOWN) : INPUT);
#endif
  }
}

void MomentaryButton::resetState(bool suppress_current_press) {
  if (_pin < 0) return;
  int btn = _threshold > 0 ? (analogRead(_pin) < _threshold) : digitalRead(_pin);
  prev = btn;
  cancel = suppress_current_press ? 1 : 0;
  down_at = (!suppress_current_press && isPressed(btn)) ? millis() : 0;
  _click_count = 0;
  _last_click_time = 0;
  _pending_click = false;
}

void MomentaryButton::preferImmediateClickUntil(unsigned long until) {
  _immediate_click_until = until;
}

int MomentaryButton::rawLevel() const {
  if (_pin < 0) return -1;
  return _threshold > 0 ? (analogRead(_pin) < _threshold) : digitalRead(_pin);
}

bool  MomentaryButton::isPressed() const {
  int btn = rawLevel();
  return isPressed(btn);
}

void MomentaryButton::cancelClick() {
  cancel = 1;
  down_at = 0;
  _click_count = 0;
  _last_click_time = 0;
  _pending_click = false;
}

bool MomentaryButton::isPressed(int level) const {
  if (_threshold > 0) {
    return level;
  }
  if (_reverse) {
    return level == LOW;
  } else {
    return level != LOW;
  }
}

int MomentaryButton::check(bool repeat_click) {
  if (_pin < 0) return BUTTON_EVENT_NONE;

  int event = BUTTON_EVENT_NONE;
  int btn = _threshold > 0 ? (analogRead(_pin) < _threshold) : digitalRead(_pin);
  if (btn != prev) {
    if (isPressed(btn)) {
      down_at = millis();
    } else {
      // button UP
      unsigned long now = millis();
      bool immediate_click = _multi_click_window == 0 ||
                             (_immediate_click_until != 0 &&
                              (long)(_immediate_click_until - now) > 0);
      if (_long_millis > 0) {
        if (down_at > 0 && (unsigned long)(now - down_at) < _long_millis) {  // only a CLICK if still within the long_press millis
          if (immediate_click) {
            event = cancel ? BUTTON_EVENT_NONE : BUTTON_EVENT_CLICK;
            if (!cancel) _immediate_click_until = 0;
            _click_count = 0;
            _last_click_time = 0;
            _pending_click = false;
          } else {
            _click_count++;
            _last_click_time = now;
            _pending_click = true;
          }
        }
      } else {
        if (immediate_click) {
          event = cancel ? BUTTON_EVENT_NONE : BUTTON_EVENT_CLICK;
          if (!cancel) _immediate_click_until = 0;
          _click_count = 0;
          _last_click_time = 0;
          _pending_click = false;
        } else {
          _click_count++;
          _last_click_time = now;
          _pending_click = true;
        }
      }
      if (event == BUTTON_EVENT_CLICK && cancel) {
        event = BUTTON_EVENT_NONE;
        _click_count = 0;
        _last_click_time = 0;
        _pending_click = false;
      }
      down_at = 0;
    }
    prev = btn;
  }
  if (!isPressed(btn) && cancel) {   // always clear the pending 'cancel' once button is back in UP state
    cancel = 0;
  }

  if (_long_millis > 0 && down_at > 0 && (unsigned long)(millis() - down_at) >= _long_millis) {
    if (_pending_click) {
      // long press during multi-click detection - cancel pending clicks
      cancelClick();
    } else {
      event = BUTTON_EVENT_LONG_PRESS;
      down_at = 0;
      _click_count = 0;
      _last_click_time = 0;
      _pending_click = false;
    }
  }
  if (down_at > 0 && repeat_click) {
    unsigned long diff = (unsigned long)(millis() - down_at);
    if (diff >= 700) {
      event = BUTTON_EVENT_CLICK;   // wait 700 millis before repeating the click events
    }
  }

  if (_pending_click && (millis() - _last_click_time) >= _multi_click_window) {
    if (down_at > 0) {
      // still pressed - wait for button release before processing clicks
      return event;
    }
    switch (_click_count) {
      case 1:
        event = BUTTON_EVENT_CLICK;
        break;
      case 2:
        event = BUTTON_EVENT_DOUBLE_CLICK;
        break;
      case 3:
        event = BUTTON_EVENT_TRIPLE_CLICK;
        break;
      default:
        // For 4+ clicks, treat as triple click?
        event = BUTTON_EVENT_TRIPLE_CLICK;
        break;
    }
    _click_count = 0;
    _last_click_time = 0;
    _pending_click = false;
  }

  return event;
}
