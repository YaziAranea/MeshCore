# MeshCore SmartUI PS17 v2.1.0-dev.1

Hotfix-выпуск от 2026-08-24 для пяти плат. Он заменяет предыдущий предварительный Release `v2.1.0-dev`; история старого выпуска [сохранена](RELEASE_NOTES_v2.1.0-dev_RU.md).

Если вы уже скачали Wireless Paper WOOD или FULL из `v2.1.0-dev`, обновитесь на этот hotfix: старая сборка не показывала случайный активный PIN и блокировала первое BLE-сопряжение.

[Скачать файлы Release](https://github.com/YaziAranea/MeshCore/releases/tag/v2.1.0-dev.1) · [подробная прошивка](docs/FLASHING_RU.md) · [проверка SHA-256](docs/VERIFY_RU.md)

## Что исправлено

- Случайный активный BLE PIN теперь автоматически и крупно показывается на отдельной странице T096, T114, ProMicro RA62, Heltec V4.3 OLED и Wireless Paper.
- Когда клиент или система телефона просит `PIN`, `passkey` или «код сопряжения», нужно ввести именно эти шесть цифр.
- После успешной BLE-связи PIN-страница автоматически скрывается на всех пяти платах.
- Wireless Paper удерживает PIN на e-paper в idle-режиме и не затирает его часами или screensaver-экраном до подключения.
- Auto-home через 30 секунд, пробуждение дисплея и переход на главный экран больше не могут спрятать PIN до подключения; входящий popup сообщения при этом не теряется.
- Убран дублирующий старый экран `FIRST`: до сопряжения показывается одна однозначная страница с действующим кодом.

`123456` в build flags — не универсальный пароль. Если сохранённого PIN нет, прошивка создаёт случайный активный код на текущий сеанс.

![BLE PIN на Wireless Paper](docs/assets/ui/wireless-paper-ble-pin.png)

## Какой файл скачать

| Плата или сценарий | Файл |
|---|---|
| Heltec T096 FEM ON | `T096_FEM_SmartUI_2.1.0-dev.1.uf2` |
| Heltec T114 с TFT | `T114_SmartUI_2.1.0-dev.1.uf2` |
| ProMicro nRF52840 + RA62 | `ProMicro_RA62_SmartUI_2.1.0-dev.1.uf2` |
| Heltec V4.3, чистая установка / Web Flasher | `Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-dev.1-freshInstall-merged.bin` |
| Heltec V4.3, обновление | `Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-dev.1-update.bin` |
| Wireless Paper WOOD, чистая установка | `Heltec_Wireless_Paper_WOOD_SmartUI_2.1.0-dev.1-freshInstall-merged.bin` |
| Wireless Paper WOOD, обновление | `Heltec_Wireless_Paper_WOOD_SmartUI_2.1.0-dev.1-update.bin` |
| Wireless Paper FULL, чистая установка | `Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-dev.1-freshInstall-merged.bin` |
| Wireless Paper FULL, обновление | `Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-dev.1-update.bin` |
| Весь комплект | `MeshCore_SmartUI_2.1.0-dev.1_all-five-boards.zip` |

UF2: двойной Reset и копирование на USB-диск. ESP32-S3: `freshInstall-merged.bin` пишется с `0x00000`, `update.bin` — с `0x10000`. ProMicro-файл нельзя прошивать в FakeTec/HT-RA62.

Скачайте также `SHA256SUMS.txt` для UF2 или `SHA256SUMS-ESP32.txt` для BIN из того же Release. Контрольные суммы и размеры файлов здесь заранее не фиксируются: их нужно брать только из итогового Release.

## Проверка

- статический контракт: `88 / 88`;
- exact core/T096/T114 framebuffer QA: `470 / 470`;
- V4.3 + ProMicro OLED QA: `25 / 25`;
- Wireless Paper QA: `180 / 180`;
- native core: `69 / 69`;
- KISS modem: `8 / 8`.

PIN-экран включён в QA всех пяти семейств плат и всех публичных шрифтов. Это симуляционная и статическая проверка, а не заявление о физическом испытании каждой платы.

## Размеры сборки

| Цель | RAM | Flash |
|---|---:|---:|
| T096 FEM ON | 150100 / 235520 (63,7%) | 555404 / 712704 (77,9%) |
| T114 | 151524 / 235520 (64,3%) | 558552 / 712704 (78,4%) |
| ProMicro RA62 | 148004 / 235520 (62,8%) | 666040 / 712704 (93,4%) |
| Heltec V4.3 OLED FEM ON | 176348 / 2097152 (8,4%) | 1503193 / 6553600 (22,9%) |
| Wireless Paper WOOD | 174264 / 327680 (53,2%) | 1296761 / 3342336 (38,8%) |
| Wireless Paper FULL | 174272 / 327680 (53,2%) | 1301789 / 3342336 (38,9%) |

ProMicro остаётся самой тесной целью: запас области приложения — 46664 байт.

## Ограничения

- V4.3 и Wireless Paper проверены сборкой и точной симуляцией, но физическое испытание не заявляется.
- На V4.3 и Wireless Paper нет заявленного физического зуммера; фиктивный tone GPIO не назначается.
- Phone GPS отсутствует. Аппаратный GPS есть только на T096, T114 и V4.3.
- FakeTec, Heltec V3, V4 TFT, T114 без дисплея и T096 FEM OFF в этот Release не входят.
- Частота, мощность, duty cycle, антенна и допустимость радиопередачи остаются ответственностью пользователя.
