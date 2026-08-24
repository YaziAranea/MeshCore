# Сборка прошивки из исходников

## Требования

- Git.
- Python 3, доступный PlatformIO.
- PlatformIO Core `6.1.19` (проверенная версия) или расширение PlatformIO IDE для Visual Studio Code.
- Интернет при первой сборке для загрузки toolchain и библиотек.
- Несколько гигабайт свободного места под `.pio` и пакеты PlatformIO.

Репозиторий фиксирует `nordicnrf52@10.11.0`, nRF52 framework fork и ключевые Git-ссылки через `platformio.ini`. Часть библиотек из PlatformIO Registry задана совместимыми диапазонами версий, поэтому побитовое совпадение сборок на разных датах не обещается. Не заменяйте зависимости вручную перед первой успешной сборкой. Для CLI проверенную версию можно установить командой `python -m pip install platformio==6.1.19`.

Закреплённая upstream-база порта: IoTThinks/MeshCore `PowerSaving-v17`, commit `a3b9ad91a5bf04e7e00713595469dc868de53628`. Обновление базы — отдельная миграция, а не часть воспроизводимой сборки.

## Получение исходников

```powershell
git clone https://github.com/YaziAranea/MeshCore.git
Set-Location MeshCore
git switch smartui-ps17.2-dev
```

Стабильный RC находится в `smartui-ps17.1`; исправления и пять плат — в `smartui-ps17.2-dev`. Не копируйте поверх клона старую папку `.pio`: PlatformIO пересоздаст её локально.

## Целевые сборки

| Плата | Environment | Формат |
|---|---|---|
| T096 FEM ON | `Heltec_t096_companion_radio_ble_femon` | UF2 |
| T114 | `Heltec_t114_companion_radio_ble` | UF2 |
| ProMicro RA62 | `ProMicro_ra62_companion_radio_ble` | UF2 |
| Heltec V4.3 OLED FEM ON | `heltec_v4_3_companion_radio_ble_femon_smartui` | merged + update BIN |
| Wireless Paper WOOD | `Heltec_Wireless_Paper_companion_radio_ble_smartui_wood` | merged + update BIN |
| Wireless Paper FULL | `Heltec_Wireless_Paper_companion_radio_ble_smartui_full` | merged + update BIN |

FakeTec, V4 TFT и обычный Heltec V3 в область этой ветки не входят.

## Сборка UF2

Из корня репозитория:

```powershell
pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2
pio run -e Heltec_t114_companion_radio_ble -t create_uf2
pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2
```

Не запускайте несколько тяжёлых PlatformIO-сборок одновременно на компьютере с небольшим объёмом RAM. В конце каждой команды должна быть строка `SUCCESS`.

Ожидаемые файлы:

```text
.pio/build/Heltec_t096_companion_radio_ble_femon/firmware.uf2
.pio/build/Heltec_t114_companion_radio_ble/firmware.uf2
.pio/build/ProMicro_ra62_companion_radio_ble/firmware.uf2
```

`create_uf2.py` использует family ID `0xADA52840` и преобразует итоговый HEX в UF2.

## Сборка ESP32-S3 BIN

Собирайте последовательно; особенно Wireless Paper безопаснее собирать с `-j 1`:

```powershell
pio run -e heltec_v4_3_companion_radio_ble_femon_smartui -t mergebin
pio run -e Heltec_Wireless_Paper_companion_radio_ble_smartui_wood -t mergebin -j 1
pio run -e Heltec_Wireless_Paper_companion_radio_ble_smartui_full -t mergebin -j 1
```

Для каждого environment получаются:

```text
.pio/build/<environment>/firmware-merged.bin
.pio/build/<environment>/firmware.bin
```

`firmware-merged.bin` — чистая установка/Web Flasher по адресу `0x00000`. `firmware.bin` — update/application по адресу `0x10000`. Это ESP32 BIN, не UF2. Проверка пары выполняется `python tools/validate_release_esp32.py firmware` после копирования под публичными именами.

Публичные stems hotfix `v2.1.0-dev.1`:

```text
Heltec_V4.3_OLED_FEMON_SmartUI_2.1.0-dev.1
Heltec_Wireless_Paper_WOOD_SmartUI_2.1.0-dev.1
Heltec_Wireless_Paper_FULL_SmartUI_2.1.0-dev.1
```

К каждому stem добавляются `-freshInstall-merged.bin` и `-update.bin`.

## Сразу писать публичные имена

Переменная `UF2_FILE_PATH` позволяет задать выходное имя. В PowerShell:

```powershell
New-Item -ItemType Directory -Force firmware | Out-Null

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/T096_FEM_SmartUI_2.1.0-dev.1.uf2'
pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/T114_SmartUI_2.1.0-dev.1.uf2'
pio run -e Heltec_t114_companion_radio_ble -t create_uf2

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/ProMicro_RA62_SmartUI_2.1.0-dev.1.uf2'
pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2

Remove-Item Env:UF2_FILE_PATH
```

На Linux/macOS:

```bash
mkdir -p firmware
UF2_FILE_PATH="$PWD/firmware/T096_FEM_SmartUI_2.1.0-dev.1.uf2" \
  pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2
UF2_FILE_PATH="$PWD/firmware/T114_SmartUI_2.1.0-dev.1.uf2" \
  pio run -e Heltec_t114_companion_radio_ble -t create_uf2
UF2_FILE_PATH="$PWD/firmware/ProMicro_RA62_SmartUI_2.1.0-dev.1.uf2" \
  pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2
```

## Контрольные сборки без создания UF2

```powershell
pio run -e Heltec_t096_companion_radio_ble_femon
pio run -e Heltec_t114_companion_radio_ble
pio run -e ProMicro_ra62_companion_radio_ble
```

Это проверяет компиляцию и линковку, но для GitHub Release всё равно создавайте UF2 через `-t create_uf2`.

## Генерация checksum-манифестов

PowerShell:

```powershell
$uf2Rows = Get-ChildItem .\firmware\*.uf2 |
  Sort-Object Name |
  ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
  }
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'firmware/SHA256SUMS.txt'),
  ([string]::Join("`n", $uf2Rows) + "`n"),
  [System.Text.UTF8Encoding]::new($false)
)

$espRows = Get-ChildItem .\firmware\*.bin |
  Sort-Object Name |
  ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
  }
[System.IO.File]::WriteAllText(
  (Join-Path $PWD 'firmware/SHA256SUMS-ESP32.txt'),
  ([string]::Join("`n", $espRows) + "`n"),
  [System.Text.UTF8Encoding]::new($false)
)
```

Linux/macOS:

```bash
cd firmware
sha256sum *.uf2 > SHA256SUMS.txt
sha256sum *.bin > SHA256SUMS-ESP32.txt
cd ..
```

После генерации обязательно выполните обратную проверку по [VERIFY_RU.md](VERIFY_RU.md).

## UI QA

SmartUI использует особые модели дисплеев. Для изменений интерфейса нельзя подменять их обычным условным шрифтом:

- T096: 160×80, реальные glyph bitmap и `xAdvance`, threshold 104;
- T114: logical 128×64 → physical 240×135, scale `1.875 × 2.109375`, `Y_OFFSET=1`, threshold 92;
- ProMicro: 128×64, реальные массивы `Utf8Cyrillic5x7.h`, пять spacing styles.
- V4.3 OLED: та же реальная OLED glyph-table, но отдельная GPS/mute/battery матрица.
- Wireless Paper: физические 250×122, 1-bit, реальные пять E213 renderer-profile и e-paper clipping.

Базовые инструменты UI QA:

```powershell
python tools/audit_smartui_ps17_contract.py
python tools/simulate_smartui_ps17_qa.py
python tools/simulate_v4_3_oled_qa.py
python tools/simulate_wireless_paper_ps17_qa.py
```

Для симулятора и шрифтового инструментария установите зафиксированные версии Pillow и fonttools:

```powershell
python -m pip install -r requirements-qa.txt
```

После изменения UI пересоздайте публичную галерею и новые QA-матрицы:

```powershell
python tools/generate_docs_assets.py
```

Результат записывается в `docs/assets/ui/` и `docs/assets/qa/`. Генератор сам вызывает V4.3 и Wireless Paper симуляторы, поэтому отдельное ручное копирование/переименование PNG не требуется.

При изменении UI проверьте не только отсутствие выхода за framebuffer, но и реальные фотографии платы. Симуляция — защита от регрессий, не замена железа.

Локальный QA hotfix `v2.1.0-dev.1` от 2026-08-23: статический контракт `88 / 88`, core/T096/T114 `470 / 470`, V4.3 + ProMicro OLED `25 / 25`, Wireless Paper `180 / 180`, native core `69 / 69`, KISS modem `8 / 8`. PIN-экран проверен всеми пятью семействами плат и всеми публичными шрифтами; подсказка OLED 128×64 — «код в приложении».

## Проверки перед релизом

1. Все три `create_uf2` и нужные ESP32 `mergebin` завершились `SUCCESS`.
2. Каждый UF2 и обе части каждой ESP32-пары существуют и имеют ненулевой размер.
3. Сгенерированы оба новых манифеста: `SHA256SUMS.txt` для UF2 и `SHA256SUMS-ESP32.txt` для BIN; старые манифесты не копировались автоматически.
4. Пройдены статический аудит и симуляция.
5. В исходниках и документации нет абсолютных путей пользователя, токенов, приватных ключей, координат и дампов.
6. `git status --short` содержит только намеренные файлы.
7. `git diff --check` не сообщает об ошибках пробелов.
8. `validate_release_uf2.py` и `validate_release_esp32.py` прошли без ошибок.
9. Тег и Release создаются только после этих проверок и нужной аппаратной проверки.

## Текущие размеры SmartUI 2.1.0-dev.1

Финальная локальная сборка hotfix дала `6 / 6 SUCCESS`:

| Цель | RAM | Flash |
|---|---:|---:|
| T096 FEM ON | 150100 / 235520 байт (63,7%) | 555404 / 712704 байт (77,9%) |
| T114 | 151524 / 235520 байт (64,3%) | 558552 / 712704 байт (78,4%) |
| ProMicro RA62 | 148004 / 235520 байт (62,8%) | 666040 / 712704 байт (93,4%) |
| Heltec V4.3 OLED FEM ON | 176348 / 2097152 байт (8,4%) | 1503193 / 6553600 байт (22,9%) |
| Wireless Paper WOOD | 174264 / 327680 байт (53,2%) | 1296761 / 3342336 байт (38,8%) |
| Wireless Paper FULL | 174272 / 327680 байт (53,2%) | 1301789 / 3342336 байт (38,9%) |

Дополнительно локально в Linux/WSL прошли native core `69 / 69` и KISS modem `8 / 8`; GitHub Actions повторяет эти тесты. Аппаратная проверка новых V4.3/Wireless Paper-профилей до стабильного Release всё ещё обязательна.

## Стабильный baseline: размеры v2.0.0-rc1

Локальная финальная сборка от 2026-08-21 дала:

| Цель | RAM | Flash |
|---|---:|---:|
| T096 FEM ON | 150092 / 235520 байт (63,7%) | 554412 / 712704 байт (77,8%) |
| T114 | 151508 / 235520 байт (64,3%) | 556120 / 712704 байт (78,0%) |
| ProMicro RA62 | 147996 / 235520 байт (62,8%) | 664104 / 712704 байт (93,2%) |

T096 собирается с целевым `-Os`, сохраняя область extra-FS и все заявленные шрифты. Из трёх nRF52-целей RC наиболее близка к пределу flash ProMicro; после любых функциональных изменений её размер нужно проверять заново.
