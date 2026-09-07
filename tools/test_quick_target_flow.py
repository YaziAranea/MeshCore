#!/usr/bin/env python3
"""Execute the firmware's real keyboard/target methods with an in-memory mesh.

No radio, BLE, device or credentials are accessed. The methods and fields are
extracted verbatim, not reimplemented as an independent state-machine model.
"""
from pathlib import Path
import argparse
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

PRELUDE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <vector>
#include "QuickTargetUi.h"
#define UI_QUICK_REPLY_KEYBOARD 1
#define UI_QUICK_REPLY_KEYBOARD_TEXT_MAX 140
#define PUB_KEY_SIZE 32
#define ADV_TYPE_CHAT 1
#define KEY_LEFT '<'
#define KEY_PREV 'p'
#define KEY_NEXT 'n'
#define KEY_RIGHT '>'
#define KEY_ENTER '\r'
#define KEY_SELECT 's'
struct ContactInfo { struct { uint8_t pub_key[32] = {}; } id; char name[32] = {}; int type = 1; };
struct ChannelDetails { struct { uint8_t secret[32] = {}; } channel; char name[32] = {}; };
struct FakeMesh {
  std::vector<ContactInfo> contacts;
  std::vector<ChannelDetails> channels;
  int sent = 0; int last_contact = -1; int last_channel = -1;
  bool getContactByIdx(uint32_t i, ContactInfo& out) {
    if (i >= contacts.size()) return false;
    out = contacts[i]; return true;
  }
  ContactInfo* lookupContactByPubKey(const uint8_t* key, int n) {
    for (auto& c : contacts) if (!memcmp(c.id.pub_key, key, n)) return &c;
    return nullptr;
  }
  int getQuickReplyContactCount() {
    int n = 0; for (auto& c : contacts) if (c.type == ADV_TYPE_CHAT && c.name[0]) ++n; return n;
  }
  int getQuickReplyChannelCount() {
    int n = 0; for (auto& c : channels) if (c.name[0]) ++n; return n;
  }
  bool getQuickReplyChannel(uint16_t index, uint8_t& id, ChannelDetails& out) {
    int seen = 0; for (size_t i = 0; i < channels.size(); ++i) if (channels[i].name[0]) {
      if (seen++ == index) { id = i; out = channels[i]; return true; }
    } return false;
  }
  bool getChannel(int id, ChannelDetails& out) {
    if (id < 0 || id >= (int)channels.size() || !channels[id].name[0]) return false;
    out = channels[id]; return true;
  }
  bool sendQuickReplyToContactPubKey(const uint8_t* key, const char* text) {
    auto c = lookupContactByPubKey(key, 32);
    if (!c || c->type != ADV_TYPE_CHAT || !text[0]) return false;
    ++sent; last_contact = c->id.pub_key[0]; return true;
  }
  bool sendQuickReplyToChannelId(uint8_t id, const char* text) {
    ChannelDetails ch;
    if (!text[0] || !getChannel(id, ch)) return false;
    ++sent; last_channel = id; return true;
  }
} the_mesh;
enum class UIEventType { ack };
struct FakeTask {
  char alert[80] = {};
  void showAlert(const char* text, int) { snprintf(alert, sizeof(alert), "%s", text); }
  void notify(UIEventType) {}
};
'''

TESTS = r'''
int checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::cerr << "FAIL line " << __LINE__ << ": " #x << "\n"; return 1; } } while (0)
ContactInfo contact(const char* name, uint8_t id, int type = 1) {
  ContactInfo c; snprintf(c.name, sizeof(c.name), "%s", name); c.id.pub_key[0] = id;
  c.id.pub_key[31] = id; c.type = type; return c;
}
void seed() {
  the_mesh = FakeMesh{};
  the_mesh.contacts = {contact("Anna", 1), contact("RELAY", 9, 2), contact("Bob", 2), contact("Анна", 3), contact("123", 4)};
  ChannelDetails ch; strcpy(ch.name, "Public"); ch.channel.secret[0] = 7;
  the_mesh.channels.push_back(ch);
}
void typing(Home& h) { h.openQuickKeyboard(); strcpy(h._quick_keyboard_text, "ТЕСТ"); h._quick_reply_open = true; }
void contactsHome(Home& h) { h._quick_target_mode = QR_TARGET_KIND; h._quick_target_cursor = 1; h.selectQuickTarget(); }
int main() {
  seed(); Home h;
  CHECK(h.quickReplyKeyboardIndex() == 0);
  CHECK(!strcmp(h.quickReplyLabel(), "Написать..."));
  for (int i = 0; i < quick_reply_count; ++i) {
    h._quick_reply_idx = i + 1; CHECK(!strcmp(h.quickReplyLabel(), quick_reply_texts[i]));
  }
  h._quick_reply_idx = h.quickReplyBackIndex(); CHECK(!strcmp(h.quickReplyLabel(), "Назад"));
  typing(h); contactsHome(h);
  CHECK(h._quick_target_mode == QR_TARGET_CONTACT_HOME);
  CHECK(h.quickTargetTotalCount() == 3);
  h.selectQuickTarget(); // All contacts
  CHECK(h._quick_target_mode == QR_TARGET_CONTACT);
  CHECK(h.quickContactCount() == 4); // repeater excluded
  CHECK(h._quick_target_contact_pubkey[0] == 1);
  h.selectQuickTarget();
  CHECK(h._quick_confirm_open); CHECK(the_mesh.sent == 0);
  h.handleQuickTargetInput(KEY_NEXT); h.handleQuickTargetInput(KEY_ENTER); // explicit Back
  CHECK(!h._quick_confirm_open); CHECK(the_mesh.sent == 0); CHECK(h._quick_keyboard_text[0]);
  h.selectQuickTarget(); h.selectQuickTarget();
  CHECK(the_mesh.sent == 1); CHECK(the_mesh.last_contact == 1);
  CHECK(!h._quick_keyboard_text[0]); CHECK(!h._quick_keyboard_open);
  CHECK(h._quick_recent_contacts.count() == 1);

  // Recent recipient is a public key, not a mutable list ordinal.
  typing(h); contactsHome(h);
  CHECK(h.quickTargetTotalCount() == 4);
  CHECK(h._quick_target_contact_pubkey[0] == 1);
  std::swap(the_mesh.contacts[0], the_mesh.contacts[2]);
  h.selectQuickTarget(); h.selectQuickTarget();
  CHECK(the_mesh.last_contact == 1); CHECK(the_mesh.sent == 2);
  CHECK(h._quick_recent_contacts.count() == 1);

  // Removal while selected must not send to the replacement row.
  typing(h); contactsHome(h);
  CHECK(h._quick_target_contact_pubkey[0] == 1);
  for (auto it = the_mesh.contacts.begin(); it != the_mesh.contacts.end(); ++it)
    if (it->id.pub_key[0] == 1) { the_mesh.contacts.erase(it); break; }
  h.selectQuickTarget(); CHECK(h._quick_confirm_open);
  h.selectQuickTarget(); CHECK(the_mesh.sent == 2); CHECK(h._quick_keyboard_text[0]);
  CHECK(!strcmp(h.task.alert, "Ошибка отправки"));
  CHECK(h.quickRecentContactCount() == 0);

  // Changing the selected companion's role also rejects transmission.
  typing(h); contactsHome(h); h.selectQuickTarget(); h.selectQuickTarget();
  CHECK(h._quick_confirm_open);
  auto chosen = the_mesh.lookupContactByPubKey(h._quick_target_contact_pubkey, 32);
  CHECK(chosen != nullptr); chosen->type = 2;
  h.selectQuickTarget(); CHECK(the_mesh.sent == 2);

  // Initial picker handles Cyrillic and #, and all names remain reachable.
  seed(); Home a; typing(a); contactsHome(a);
  a._quick_target_cursor = 1; a.selectQuickTarget();
  CHECK(a._quick_target_mode == QR_TARGET_INITIAL); CHECK(a._quick_initial_count == 4);
  bool found = false;
  for (uint8_t i = 0; i < a._quick_initial_count; ++i) {
    if (a._quick_initials[i] == smartui::contactInitialGroup("Анна")) { a._quick_target_cursor = i; found = true; break; }
  }
  CHECK(found); a.selectQuickTarget(); CHECK(a.quickContactCount() == 1);
  CHECK(a._quick_target_contact_pubkey[0] == 3);
  a.selectQuickTarget(); CHECK(the_mesh.sent == 0); a.selectQuickTarget();
  CHECK(the_mesh.last_contact == 3); CHECK(the_mesh.sent == 1);

  // Channel slot edits between visible selection and confirmation are guarded.
  Home ch; typing(ch); ch._quick_target_mode = QR_TARGET_KIND; ch._quick_target_cursor = 0;
  ch.selectQuickTarget(); ch.selectQuickTarget(); CHECK(ch._quick_confirm_open);
  the_mesh.channels[0].channel.secret[0] = 8;
  ch.selectQuickTarget(); CHECK(the_mesh.sent == 1); CHECK(!strcmp(ch.task.alert, "Чат изменился"));
  the_mesh.channels[0].channel.secret[0] = 7; strcpy(the_mesh.channels[0].name, "Different");
  ch.selectQuickTarget(); CHECK(the_mesh.sent == 1);
  strcpy(the_mesh.channels[0].name, "Public"); ch.selectQuickTarget();
  CHECK(the_mesh.sent == 2); CHECK(the_mesh.last_channel == 0);

  // A deleted final row cannot hide Back or change the selected identity.
  seed(); Home last; typing(last);
  last._quick_target_mode = QR_TARGET_CONTACT; last._quick_target_cursor = 3;
  CHECK(last.captureQuickTargetIdentity());
  the_mesh.contacts.pop_back();
  CHECK(last.quickContactCount() == 3);
  CHECK(last.quickTargetTotalCount() == 5); // pinned row plus a distinct Back
  last.handleQuickTargetInput(KEY_NEXT);
  CHECK(last._quick_target_cursor == 3); CHECK(!last._quick_target_identity_valid);
  CHECK(last.quickTargetTotalCount() == 4);
  last.selectQuickTarget(); CHECK(last._quick_target_mode == QR_TARGET_CONTACT_HOME);
  CHECK(the_mesh.sent == 0);

  // Explicit keyboard exit clears its existing input buffer (no drafts).
  typing(ch); ch._quick_keyboard_cursor = 23; ch.selectQuickKeyboardKey();
  CHECK(!ch._quick_keyboard_open); CHECK(!ch._quick_keyboard_text[0]);
  CHECK(ch._quick_reply_idx == 0);
  typing(ch); ch._quick_keyboard_page = 1; ch._quick_keyboard_cursor = 14;
  ch._quick_keyboard_text[0] = 0; ch.selectQuickKeyboardKey();
  CHECK(!strcmp(ch._quick_keyboard_text, "Ё"));
  std::cout << checks << " actual keyboard/target-flow checks passed\n";
}
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'qa_outputs/experimental1/target_flow')
    args = parser.parse_args()
    source = (ROOT / 'examples/companion_radio/ui-new/UITask.cpp').read_text(encoding='utf-8')
    constants = source[source.index('static const char* quick_reply_texts[]'):source.index('static ColorVal uiSemanticColor(')]
    start = source.index('  bool _quick_keyboard_open;', source.index('class HomeScreen'))
    fields = source[start:source.index('#endif', start)]
    start = source.index('  uint8_t quickReplyMenuCount() const')
    methods = source[start:source.index('  void drawQuickKeyboardKey(', start)] + '\n#endif\n'
    body = PRELUDE + constants + '''
class Home { public:
  FakeTask task; FakeTask* _task = &task;
  bool _quick_reply_open = false; uint8_t _quick_reply_idx = 0;
''' + fields + methods + '\n};\n' + TESTS
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cpp = out / 'target_flow.cpp'
    cpp.write_text(body, encoding='utf-8')
    include = ROOT / 'examples/companion_radio/ui-new'
    if shutil.which('g++'):
        exe = out / 'target_flow'
        subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-I', str(include), str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    else:
        def linux(p):
            return subprocess.check_output(['wsl', '--exec', 'wslpath', '-a', str(p)]).decode().strip()
        exe = linux(out) + '/target_flow'
        subprocess.run(['wsl', '--exec', 'g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-I', linux(include), linux(cpp), '-o', exe], check=True)
        subprocess.run(['wsl', '--exec', exe], check=True)

if __name__ == '__main__':
    main()
