# MeshCore SmartUI PS17 v2.1.0-dev

Предварительный выпуск единого русского SmartUI для пяти плат. Основан на PowerSaving-v17 и не заменяет прежний `v2.0.0-rc1`.

[Скачать файлы Release](https://github.com/YaziAranea/MeshCore/releases/tag/v2.1.0-dev) · [подробная прошивка](docs/FLASHING_RU.md) · [проверка SHA-256](docs/VERIFY_RU.md)

## Что нового

- Исправлена реальная причина частичного сброса настроек: ключи `prefs.json` с цифрами теперь читаются корректно; добавлена одноразовая миграция SmartUI из PS16.
- Восстановлена штатная работа зуммера на T096, T114 и ProMicro без повторной перезаписи выбранного пользователем GPIO.
- Исправлена BLE-синхронизация времени назад вместе с внутренним timestamp сообщений.
- Калибровка АКБ/ADC доступна на всех пяти платах и сохраняется только после подтверждения.
- Добавлены Heltec V4.3 OLED FEM ON и Heltec Wireless Paper с двумя профилями.
- Wireless Paper получил точный UI 250×122. `WOOD` рекомендуется для обычной работы; `FULL` добавляет экранную клавиатуру и выбор адресата.

## Интерфейс

| T096 / T114 / ProMicro | Heltec V4.3 OLED | Wireless Paper WOOD |
|---|---|---|
| ![Обзор SmartUI](docs/assets/ui/ui-overview-three-boards.png) | ![Часы V4.3](docs/assets/ui/v4-3-oled-clock.png) | ![Часы Wireless Paper](docs/assets/ui/wireless-paper-wood-clock.png) |

## Какой файл скачать

| Плата или сценарий | Файл |
|---|---|
| Heltec T096 FEM ON | `T096_FEM_SmartUI_2.1.0-dev.uf2` |
| Heltec T114 с TFT | `T114_SmartUI_2.1.0-dev.uf2` |
| ProMicro nRF52840 + RA62 | `ProMicro_RA62_SmartUI_2.1.0-dev.uf2` |
| Heltec V4.3, чистая установка / Web Flasher | `Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-dev-freshInstall-merged.bin` |
| Heltec V4.3, обновление | `Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-dev-update.bin` |
| Wireless Paper WOOD, чистая установка | `Heltec_Wireless_Paper_WOOD_SmartUI_2.1.0-dev-freshInstall-merged.bin` |
| Wireless Paper WOOD, обновление | `Heltec_Wireless_Paper_WOOD_SmartUI_2.1.0-dev-update.bin` |
| Wireless Paper FULL, чистая установка | `Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-dev-freshInstall-merged.bin` |
| Wireless Paper FULL, обновление | `Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-dev-update.bin` |
| Весь комплект | `MeshCore_SmartUI_2.1.0-dev_all-five-boards.zip` |

UF2: двойной Reset и копирование на USB-диск. ESP32-S3: `freshInstall-merged.bin` пишется с `0x00000`, `update.bin` — с `0x10000`. Проверяйте SHA-256 по соответствующему манифесту. ProMicro-файл нельзя прошивать в FakeTec/HT-RA62.

## Проверка

- шесть целевых профилей: `6 / 6 SUCCESS`;
- native core: `69 / 69`;
- KISS modem: `8 / 8`;
- статический контракт: `76 / 76`;
- UI-симуляции: `455 / 455`, V4.3 `20 / 20`, Wireless Paper `160 / 160`;
- структура файлов: UF2 `3 / 3`, ESP32-S3 BIN-пары `3 / 3`;
- [GitHub Actions: 11 / 11 заданий](https://github.com/YaziAranea/MeshCore/actions/runs/32588029443).

SHA-256 общего ZIP:

```text
96F690CCB899B241312CF3779868D7AEF1D4D92002850AA25DD60A3D319BEE03
```

## Ограничения

- V4.3 и Wireless Paper проверены сборкой и точной симуляцией, но физическое испытание не заявляется.
- На V4.3 и Wireless Paper нет заявленного физического зуммера; фиктивный tone GPIO не назначается.
- Phone GPS отсутствует. Аппаратный GPS есть только на T096, T114 и V4.3.
- FakeTec, Heltec V3, V4 TFT, T114 без дисплея и T096 FEM OFF в этот Release не входят.
- ProMicro занимает 93,4% области приложения.
- Частота, мощность, duty cycle, антенна и допустимость радиопередачи остаются ответственностью пользователя.
