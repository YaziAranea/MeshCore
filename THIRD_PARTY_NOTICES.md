# Third-party notices / сторонние компоненты

Этот файл дополняет, но не заменяет основной [LICENSE](LICENSE).

## MeshCore

Проект является неофициальной производной работой MeshCore и ветки `PowerSaving-v16`:

- upstream проекта: <https://github.com/meshcore-dev/MeshCore>
- использованная база: <https://github.com/IoTThinks/MeshCore>
- лицензия: MIT
- исходное уведомление: `Copyright (c) 2025 Scott Powell / rippleradios.com`

Полный текст MIT и исходное copyright notice сохранены в `LICENSE` и `license.txt`.

Упоминание MeshCore, IoTThinks и владельцев сторонних компонентов не означает их одобрение этой модификации.

## Встроенные bitmap-шрифты

`src/helpers/ui/EmbeddedBitmapFonts.h` содержит растровые данные, сгенерированные из следующих шрифтов. Они используются для T096 и T114 и распространяются на условиях SIL Open Font License 1.1.

| Семейство-источник | Copyright из OFL-файла | Лицензия в репозитории |
|---|---|---|
| Roboto Condensed | Copyright 2011 The Roboto Project Authors | [`licenses/fonts/OFL-RobotoCondensed.txt`](licenses/fonts/OFL-RobotoCondensed.txt) |
| Noto Sans Condensed | Copyright 2022 The Noto Project Authors | [`licenses/fonts/OFL-NotoSans.txt`](licenses/fonts/OFL-NotoSans.txt) |
| Open Sans | Copyright 2020 The Open Sans Project Authors | [`licenses/fonts/OFL-OpenSans.txt`](licenses/fonts/OFL-OpenSans.txt) |
| PT Sans Narrow | Copyright (c) 2010 ParaType Ltd.; Reserved Font Names “PT Sans” and “ParaType” | [`licenses/fonts/OFL-PTSansNarrow.txt`](licenses/fonts/OFL-PTSansNarrow.txt) |
| Oswald | Copyright 2016 The Oswald Project Authors | [`licenses/fonts/OFL-Oswald.txt`](licenses/fonts/OFL-Oswald.txt) |

SIL OFL разрешает использование, изучение, модификацию и распространение Font Software при соблюдении условий лицензии, включая сохранение OFL и ограничения Reserved Font Names. Растровые данные не продаются отдельно от программы.

Названия шрифтов в UI используются для идентификации выбранного визуального профиля. Они не означают одобрение проекта авторами шрифтов.

## OLED bitmap table

`src/helpers/ui/Utf8Cyrillic5x7.h` и связанные spacing styles входят в исходный код этой модификации и распространяются вместе с ним по основной лицензии проекта, если в самом файле не указано иное.

## Библиотеки PlatformIO

Сборка загружает библиотеки, перечисленные в `platformio.ini` и variant-конфигурациях, включая RadioLib, Crypto, RTClib, Adafruit display/sensor libraries, CustomLFS, MicroNMEA и base64. Каждая такая библиотека сохраняет собственную лицензию в установленном пакете или исходном репозитории. Основная MIT-лицензия этого репозитория не меняет их условий.

Полный воспроизводимый список конкретной цели можно получить командой:

```text
pio pkg list -e Heltec_t096_companion_radio_ble_femon
pio pkg list -e Heltec_t114_companion_radio_ble
pio pkg list -e ProMicro_ra62_companion_radio_ble
```

## Изображения документации

PNG в `docs/assets/ui` и `docs/assets/qa` являются результатами локального симулятора интерфейса и документируют эту модификацию. Они не являются фотографиями оборудования и не заменяют аппаратные испытания.
