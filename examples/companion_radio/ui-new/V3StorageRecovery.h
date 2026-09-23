#pragma once

// Included only by opt-in ESP32 SmartUI startup paths. This is not normal UI:
// preferences, mesh identity and BLE may not be initialized yet. Historical
// v3* function names remain for source compatibility.
#include <SHA256.h>
#include <esp_partition.h>
#include <esp_spiffs.h>
#include <SPIFFS.h>
#include "StorageRecoveryPolicy.h"

namespace smartui {

// Exact factory-empty SPIFFS shipped by our pinned fresh-install packager.
// A failed mount alone, erased flash, or a partial match NEVER grants
// permission to format. Release validation binds the selected hash/layout to
// both merged storage bytes and the application image.
#if UI_V3_STORAGE_RECOVERY
static constexpr char kV3FactorySpiffsSha256Hex[] =
    "debe417f42a5bdda6c6e81539f9a3519b4653ab70cefeba01885ecc4b2d3cf5b";
static constexpr size_t kFactorySpiffsOffset = 0x670000;
static constexpr size_t kFactorySpiffsSize = 0x180000;
static constexpr size_t kFactoryFlashMinimum = 0x7f0000;
static constexpr char kStorageRecoveryBoard[] = "V3";
#elif UI_SAFE_STORAGE_RECOVERY && defined(HELTEC_LORA_V4)
static constexpr char kV3FactorySpiffsSha256Hex[] =
    "ec202a958aea323b1e5f8388ab92814695b85d5ac9c77227fdf47ed850fff7fe";
static constexpr size_t kFactorySpiffsOffset = 0xc90000;
static constexpr size_t kFactorySpiffsSize = 0x360000;
static constexpr size_t kFactoryFlashMinimum = 0xff0000;
static constexpr char kStorageRecoveryBoard[] = "V4.3";
#elif UI_SAFE_STORAGE_RECOVERY && defined(HELTEC_WIRELESS_PAPER)
static constexpr char kV3FactorySpiffsSha256Hex[] =
    "debe417f42a5bdda6c6e81539f9a3519b4653ab70cefeba01885ecc4b2d3cf5b";
static constexpr size_t kFactorySpiffsOffset = 0x670000;
static constexpr size_t kFactorySpiffsSize = 0x180000;
static constexpr size_t kFactoryFlashMinimum = 0x7f0000;
static constexpr char kStorageRecoveryBoard[] = "Paper";
#else
  #error "Safe SPIFFS recovery has no reviewed board layout/hash"
#endif

static esp_err_t v3StorageMountError = ESP_FAIL;

static bool v3TryMountStorage() {
  if (SPIFFS.begin(false)) {
    v3StorageMountError = ESP_OK;
    return true;
  }
  // Arduino's bool discards the reason. A non-formatting SDK retry preserves
  // an actionable error code for the normal recovery screen and USB log.
  const esp_vfs_spiffs_conf_t conf = {"/spiffs", nullptr, 10, false};
  v3StorageMountError = esp_vfs_spiffs_register(&conf);
  if (v3StorageMountError == ESP_OK) {
    // The SDK probe does not initialize Arduino's VFS mountpoint. Release only
    // our successful probe before asking the Arduino wrapper to mount again.
    v3StorageMountError = esp_vfs_spiffs_unregister(nullptr);
    if (v3StorageMountError == ESP_OK) {
      if (SPIFFS.begin(false)) return true;
      v3StorageMountError = ESP_FAIL;
    }
  }
  Serial.printf("[%s FS2] mount error=%s (0x%X) heap=%u flash=%u\r\n",
      kStorageRecoveryBoard, esp_err_to_name(v3StorageMountError), (unsigned)v3StorageMountError,
      ESP.getFreeHeap(), ESP.getFlashChipSize());
  return false;
}

static bool v3HasExactFactoryEmptyStorage() {
  esp_partition_iterator_t it = esp_partition_find(
      ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_SPIFFS, nullptr);
  if (!it) return false;
  const esp_partition_t partition = *esp_partition_get(it);
  it = esp_partition_next(it);
  if (it) {
    esp_partition_iterator_release(it);
    return false;
  }
  if (strcmp(partition.label, "spiffs") != 0 || partition.encrypted ||
      partition.address != kFactorySpiffsOffset || partition.size != kFactorySpiffsSize ||
      ESP.getFlashChipSize() < kFactoryFlashMinimum) return false;

  SHA256 hash;
  uint8_t chunk[512];
  for (size_t offset = 0; offset < partition.size; offset += sizeof(chunk)) {
    if (esp_partition_read(&partition, offset, chunk, sizeof(chunk)) != ESP_OK) return false;
    hash.update(chunk, sizeof(chunk));
    if ((offset & 0x1fff) == 0) delay(1);
  }
  uint8_t digest[32];
  hash.finalize(digest, sizeof(digest));
  static constexpr char hex[] = "0123456789abcdef";
  for (size_t i = 0; i < sizeof(digest); ++i) {
    if (hex[digest[i] >> 4] != kV3FactorySpiffsSha256Hex[2 * i] ||
        hex[digest[i] & 15] != kV3FactorySpiffsSha256Hex[2 * i + 1]) return false;
  }
  return true;
}

static void v3StorageStatus(DisplayDriver* display, const char* title,
                            const char* detail) {
  Serial.printf("[%s FS2] %s: %s\r\n", kStorageRecoveryBoard, title, detail);
  if (!display) return;
  display->startFrame();
  display->setTextSize(1);
  display->setColor(UIColor::warning_txt);
  display->drawTextCentered(display->width() / 2, 18, title);
  display->drawTextCentered(display->width() / 2, 34, detail);
  display->endFrame();
}

static void v3StorageMenu(DisplayDriver* display,
                          const StorageRecoveryPolicy& policy, bool identity_error) {
  if (!display) return;
  display->startFrame();
  display->setTextSize(1);
  display->setColor(UIColor::warning_txt);
  if (policy.confirmingReset()) {
    display->drawTextCentered(display->width() / 2, 0, "Стереть данные?");
    display->drawTextLeftAlign(2, 11, "Ключ, контакты,");
    display->drawTextLeftAlign(2, 21, "настройки - всё!");
    display->drawTextLeftAlign(2, 32, policy.selectedIndex() == 0 ? "> Отмена" : "  Отмена");
    display->drawTextLeftAlign(2, 42, policy.selectedIndex() == 1 ? "> Стереть" : "  Стереть");
  } else {
    char title[64];
    snprintf(title, sizeof(title), "FS2: память %04X", (unsigned)v3StorageMountError);
    display->drawTextCentered(display->width() / 2, 0,
        identity_error ? "FS2: ошибка ключа" : title);
    const char* choices[] = {"Повторить", "Сброс данных", "Выключить"};
    for (unsigned i = 0; i < 3; ++i) {
      char line[64];
      snprintf(line, sizeof(line), "%s %s", policy.selectedIndex() == i ? ">" : " ", choices[i]);
      display->drawTextLeftAlign(2, 15 + i * 11, line);
    }
  }
  display->drawTextLeftAlign(2, 55, "1x:далее 2с:выбор");
  display->endFrame();
}

static bool v3FormatAndMountStorage(DisplayDriver* display) {
  v3StorageStatus(display, "Подготовка памяти", "Не отключать!");
  SPIFFS.end();
  const bool formatted = SPIFFS.format();
  const bool mounted = formatted && v3TryMountStorage();
  Serial.printf("[%s FS2] native format=%d mount=%d heap=%u flash=%u\r\n",
      kStorageRecoveryBoard, formatted, mounted, ESP.getFreeHeap(), ESP.getFlashChipSize());
  if (!mounted) v3StorageStatus(display, "Память недоступна", "Сброс не помог");
  return mounted;
}

// Never invokes ui_task: a failed filesystem/identity cannot supply UI prefs.
// No reset is performed without a separately selected, held-and-released
// confirmation. An already-held BOOT button cannot select or confirm anything.
static bool v3StorageRecoveryMenu(DisplayDriver* display, bool identity_error) {
  pinMode(PIN_USER_BTN, INPUT_PULLUP);
  StorageRecoveryPolicy policy((uint32_t)millis(),
      digitalRead(PIN_USER_BTN) == USER_BTN_PRESSED);
  v3StorageMenu(display, policy, identity_error);
  uint32_t last_activity = millis();
  bool screen_awake = true;
  bool previous_button = digitalRead(PIN_USER_BTN) == USER_BTN_PRESSED;
  Serial.printf("[%s FS2] Recovery: click next, hold 2s then release to select. No automatic reset.\r\n",
      kStorageRecoveryBoard);
  for (;;) {
    serviceFatalBatterySafety();
    const bool pressed = digitalRead(PIN_USER_BTN) == USER_BTN_PRESSED;
    if (pressed != previous_button) {
      previous_button = pressed;
      last_activity = millis();
      if (display && !screen_awake) {
        display->turnOn();
        screen_awake = true;
        v3StorageMenu(display, policy, identity_error);
      }
    }
    if (display && screen_awake && static_cast<uint32_t>(millis() - last_activity) >= 30000) {
      display->turnOff();
      screen_awake = false;
    }
    const unsigned previous_selection = policy.selectedIndex();
    const bool previous_confirmation = policy.confirmingReset();
    const StorageRecoveryAction action = policy.update((uint32_t)millis(),
        pressed);
    if (action == StorageRecoveryAction::PowerOff) {
      board.powerOff();
    } else if (action == StorageRecoveryAction::RetryMount) {
      if (identity_error) board.reboot();
      if (v3TryMountStorage()) return true;
      v3StorageStatus(display, "Память недоступна", "Повтор не помог");
      delay(700);
      v3StorageMenu(display, policy, identity_error);
    } else if (action == StorageRecoveryAction::FormatStorage) {
      // A missing display must not turn unseen button presses into consent.
      if (display && v3FormatAndMountStorage(display)) {
        if (identity_error) board.reboot();
        return true;
      }
      delay(700);
      v3StorageMenu(display, policy, identity_error);
    } else if (previous_selection != policy.selectedIndex() ||
               previous_confirmation != policy.confirmingReset()) {
      v3StorageMenu(display, policy, identity_error);
    }
    delay(10); // service scheduler/watchdog, do not spin at full CPU power
  }
}

static bool v3MountStorage(DisplayDriver* display) {
  if (v3TryMountStorage()) return true;
  Serial.printf("[%s FS2] mount failed, heap=%u flash=%u; checking factory-empty image\r\n",
      kStorageRecoveryBoard, ESP.getFreeHeap(), ESP.getFlashChipSize());
  // Only a full match of the known-empty fresh-install bytes may trigger one
  // native initialization attempt. No user files can exist in those bytes.
  if (v3HasExactFactoryEmptyStorage() && v3FormatAndMountStorage(display)) return true;
  return v3StorageRecoveryMenu(display, false);
}

} // namespace smartui
