"""Execute production menu membership and capability gates after the cleanup.

This verifies navigation data, not hardware button timing or the whole firmware.
"""
from pathlib import Path
import argparse

from test_ui_sessions_v006 import function, run_cpp

ROOT = Path(__file__).resolve().parents[1]


def code(source, sound, extras=True, advanced_tone=True):
    home = source[source.index('class HomeScreen'):]
    enum = source[source.index('  enum HomePage {'):]
    enum = enum[:enum.index('  };') + 4]
    count = home[home.index('  static const uint8_t COMPACT_SETTINGS_GROUP_COUNT ='):]
    count = count[:count.index(';') + 1]
    methods = '\n'.join(function(home, marker) for marker in (
        '  const char* compactSettingsGroupName(',
        '  const uint8_t* compactSettingsRawPages(',
        '  uint8_t compactSettingsItemCount(',
        '  uint8_t compactSettingsPageAt(',
        '  bool isSettingsItem(',
        '  bool isPageVisibleInCurrentMenu('))
    switches = ('UI_COMPACT_SETTINGS_MENU', 'UI_NOTIFICATION_SETTINGS',
                'UI_OFFLINE_DM_LED_PAGE', 'UI_APPEARANCE_MENU', 'UI_UNREAD_LED_PAGE',
                'UI_SMART_B12_TONE_LIST', 'UI_COLOR_APPEARANCE_MENU',
                'UI_BACKLIGHT_TIMEOUT_PAGE', 'UI_AUTO_ADVERT_PAGE', 'UI_CLIENT_REPEAT_PAGE',
                'ENV_INCLUDE_GPS', 'UI_CH2_RELAY_PAGE', 'UI_LINK_TEST_PAGE',
                'UI_TIMEZONE_PAGE', 'UI_BOARD_LEDS_PAGE', 'UI_LOW_BATTERY_SHUTDOWN_PAGE',
                'UI_TONE_8BIT_PAGE', 'UI_TONE_RESONANCE_PAGE', 'UI_TONE_BRIDGE_PAGE',
                'UI_ADC_MULTIPLIER_PAGE', 'UI_RECENT_PAGE', 'UI_CLOCK_PAGE_VISIBLE')
    prelude = '#include <cassert>\n#include <cstdint>\n#include <cstring>\n#include <cstdio>\n'
    prelude += '\n'.join(f'#define {name} 1' for name in switches) + '\n'
    if not advanced_tone:
        for name in ('UI_TONE_8BIT_PAGE', 'UI_TONE_RESONANCE_PAGE', 'UI_TONE_BRIDGE_PAGE'):
            prelude += f'#undef {name}\n#define {name} 0\n'
    prelude += f'#define UI_SMART_B11_EXTRAS {int(extras)}\n#define UI_SOUND_SETTINGS_GROUP {int(sound)}\n'
    prelude += '#define PIN_MSG_ALERT 45\n#define AUTO_SHUTDOWN_MILLIVOLTS 3200\n'
    if sound:
        prelude += '#define PIN_MSG_TONE 31\n'
    return prelude + enum + r'''
struct Task {
  bool hasUiFontChoices() const { return true; }
  bool hasUiThemeChoices() const { return true; }
};
struct Menu { Task task; const Task* _task=&task; bool _settings_open=false;
''' + count + '\n' + methods + r'''
};
int main() {
  Menu menu;
  assert(menu.COMPACT_SETTINGS_GROUP_COUNT == (UI_SOUND_SETTINGS_GROUP ? 6 : 5));
  assert(!strcmp(menu.compactSettingsGroupName(0), "Уведомления"));
  int seen[HomePage::Count]={};
  for(uint8_t group=0;group<menu.COMPACT_SETTINGS_GROUP_COUNT;++group) {
    assert(strcmp(menu.compactSettingsGroupName(group), "Избранное"));
    const unsigned count=menu.compactSettingsItemCount(group);
    assert(count>0);
    for(uint8_t row=0;row<count;++row) {
      const uint8_t page=menu.compactSettingsPageAt(group,row);
      assert(page<HomePage::Count && menu.isSettingsItem(page));
      assert(++seen[page]==1); // Each visible setting belongs to exactly one group.
#ifdef PIN_MSG_TONE
      if(page==HomePage::ALERT_SOUND || page==HomePage::ALERT_VOLUME ||
         page==HomePage::ALERT_TONE_PIN ||
#if UI_TONE_8BIT_PAGE
         page==HomePage::ALERT_TONE_STYLE ||
#endif
#if UI_TONE_RESONANCE_PAGE
         page==HomePage::ALERT_TONE_RESONANCE ||
#endif
#if UI_TONE_BRIDGE_PAGE
         page==HomePage::ALERT_TONE_BRIDGE ||
#endif
         page==HomePage::ALERT_VIBE_PIN)
        assert(!strcmp(menu.compactSettingsGroupName(group), "Звук и вибро"));
#endif
    }
    assert(menu.compactSettingsPageAt(group,count)==HomePage::SETTINGS);
  }
#if UI_SMART_B11_EXTRAS
  for(uint8_t retired: {uint8_t(HomePage::FAVORITE_SLOT_1),uint8_t(HomePage::FAVORITE_SLOT_2),
                       uint8_t(HomePage::FAVORITE_SLOT_3),uint8_t(HomePage::FAVORITE_PICKER),
                       uint8_t(HomePage::UNDO_SETTING)}) {
    assert(!seen[retired]);
    assert(!menu.isSettingsItem(retired)); // Not exposed by flat-menu fallback either.
    menu._settings_open=false;
    assert(!menu.isPageVisibleInCurrentMenu(retired)); // Not a main-carousel page.
    menu._settings_open=true;
    assert(!menu.isPageVisibleInCurrentMenu(retired));
  }
#endif
#ifdef PIN_MSG_TONE
  assert(seen[HomePage::ALERT_SOUND] && seen[HomePage::ALERT_VOLUME]);
  assert(seen[HomePage::ALERT_TONE_PIN]);
#if UI_TONE_8BIT_PAGE
  assert(seen[HomePage::ALERT_TONE_STYLE]);
#endif
#if UI_TONE_RESONANCE_PAGE
  assert(seen[HomePage::ALERT_TONE_RESONANCE]);
#endif
#if UI_TONE_BRIDGE_PAGE
  assert(seen[HomePage::ALERT_TONE_BRIDGE]);
#endif
  assert(seen[HomePage::ALERT_VIBE_PIN]);
#else
  assert(!seen[HomePage::ALERT_VIBE_PIN]); // Boards with the sound group disabled stay gated.
#endif
  assert(seen[HomePage::ADC] && seen[HomePage::ADC_RESET]);
  assert(seen[HomePage::LOW_BATT_SHUTDOWN] && seen[HomePage::TIMEZONE]);
  puts("PASS actual compact menu: no Favorites/Undo, sound settings grouped once, board gates retained");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT/'qa_outputs/compact-menu-cleanup')
    args = parser.parse_args()
    source = (ROOT/'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    for name, sound, extras, advanced_tone in [
            ('nrf_sound', True, True, True),
            ('promicro_sound', True, True, False),
            ('esp_no_sound', False, True, True),
            ('legacy_no_extras', True, False, True)]:
        generated = '#include <initializer_list>\n' + code(source, sound, extras, advanced_tone)
        print(run_cpp(generated, args.out.resolve(), name), end='')


if __name__ == '__main__':
    main()
