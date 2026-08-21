# Сборка прошивки из исходников

## Требования

- Git.
- Python 3, доступный PlatformIO.
- PlatformIO Core `6.1.19` (проверенная версия) или расширение PlatformIO IDE для Visual Studio Code.
- Интернет при первой сборке для загрузки toolchain и библиотек.
- Несколько гигабайт свободного места под `.pio` и пакеты PlatformIO.

Репозиторий фиксирует `nordicnrf52@10.11.0`, nRF52 framework fork и версии ключевых библиотек через `platformio.ini`. Не заменяйте их случайными последними версиями перед первой успешной сборкой. Для CLI проверенную версию можно установить командой `python -m pip install platformio==6.1.19`.

Закреплённая upstream-база порта: IoTThinks/MeshCore `PowerSaving-v17`, commit `a3b9ad91a5bf04e7e00713595469dc868de53628`. Обновление базы — отдельная миграция, а не часть воспроизводимой сборки `v2.0.0-rc1`.

## Получение исходников

```powershell
git clone https://github.com/YaziAranea/MeshCore.git
Set-Location MeshCore
git switch smartui-ps17.1
```

Публикационный код PS17 находится в ветке `smartui-ps17.1`. Не копируйте поверх клона старую папку `.pio`: PlatformIO пересоздаст её локально.

## Три релизные цели

| Плата | Environment | Формат |
|---|---|---|
| T096 FEM ON | `Heltec_t096_companion_radio_ble_femon` | UF2 |
| T114 | `Heltec_t114_companion_radio_ble` | UF2 |
| ProMicro RA62 | `ProMicro_ra62_companion_radio_ble` | UF2 |

FakeTec и ESP32-цели в `v2.0.0-rc1` не входят.

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

## Сразу писать публичные имена

Переменная `UF2_FILE_PATH` позволяет задать выходное имя. В PowerShell:

```powershell
New-Item -ItemType Directory -Force firmware | Out-Null

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/T096_FEM_SmartUI_v2.0.0-rc1.uf2'
pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/T114_SmartUI_v2.0.0-rc1.uf2'
pio run -e Heltec_t114_companion_radio_ble -t create_uf2

$env:UF2_FILE_PATH = Join-Path $PWD 'firmware/ProMicro_RA62_SmartUI_v2.0.0-rc1.uf2'
pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2

Remove-Item Env:UF2_FILE_PATH
```

На Linux/macOS:

```bash
mkdir -p firmware
UF2_FILE_PATH="$PWD/firmware/T096_FEM_SmartUI_v2.0.0-rc1.uf2" \
  pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2
UF2_FILE_PATH="$PWD/firmware/T114_SmartUI_v2.0.0-rc1.uf2" \
  pio run -e Heltec_t114_companion_radio_ble -t create_uf2
UF2_FILE_PATH="$PWD/firmware/ProMicro_RA62_SmartUI_v2.0.0-rc1.uf2" \
  pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2
```

## Контрольные сборки без создания UF2

```powershell
pio run -e Heltec_t096_companion_radio_ble_femon
pio run -e Heltec_t114_companion_radio_ble
pio run -e ProMicro_ra62_companion_radio_ble
```

Это проверяет компиляцию и линковку, но для GitHub Release всё равно создавайте UF2 через `-t create_uf2`.

## Генерация SHA256SUMS.txt

PowerShell:

```powershell
$rows = Get-ChildItem .\firmware\*.uf2 |
  Sort-Object Name |
  ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
  }
[System.IO.File]::WriteAllLines(
  (Join-Path $PWD 'firmware/SHA256SUMS.txt'),
  $rows,
  [System.Text.UTF8Encoding]::new($false)
)
```

Linux/macOS:

```bash
cd firmware
sha256sum *.uf2 > SHA256SUMS.txt
cd ..
```

После генерации обязательно выполните обратную проверку по [VERIFY_RU.md](VERIFY_RU.md).

## UI QA

SmartUI 2.0.0-rc1 использует особые модели дисплеев. Для изменений интерфейса нельзя подменять их обычным условным шрифтом:

- T096: 160×80, реальные glyph bitmap и `xAdvance`, threshold 104;
- T114: logical 128×64 → physical 240×135, scale `1.875 × 2.109375`, `Y_OFFSET=1`, threshold 92;
- ProMicro: 128×64, реальные массивы `Utf8Cyrillic5x7.h`, пять spacing styles.

Базовые инструменты UI QA:

```powershell
python tools/audit_smartui_ps17_contract.py
python tools/simulate_smartui_ps17_qa.py
```

Для симулятора и шрифтового инструментария установите зафиксированные версии Pillow и fonttools:

```powershell
python -m pip install -r requirements-qa.txt
```

После изменения UI пересоздайте публичную галерею:

```powershell
python tools/generate_docs_assets.py
```

Результат записывается в `docs/assets/ui/`.

При изменении UI проверьте не только отсутствие выхода за framebuffer, но и реальные фотографии платы. Симуляция — защита от регрессий, не замена железа.

## Проверки перед релизом

1. Все три `create_uf2` завершились `SUCCESS`.
2. Каждый UF2 существует и имеет ненулевой размер.
3. Сгенерирован новый `SHA256SUMS.txt`; старый манифест не копировался автоматически.
4. Пройдены статический аудит и симуляция.
5. В исходниках и документации нет абсолютных путей пользователя, токенов, приватных ключей, координат и дампов.
6. `git status --short` содержит только намеренные файлы.
7. `git diff --check` не сообщает об ошибках пробелов.
8. Тег и Release создаются только после этих проверок.

## Замечания по размеру

Цифры PS16 нельзя переносить на PS17 как результат проверки. Для `v2.0.0-rc1` фиксируйте RAM и flash из свежего отчёта линковщика каждой цели. Особенно внимательно контролируйте T096: в стабильной PS16-линии он был близок к пределу области приложения.
