# MeshCore Smart UI — PowerSaving17

Неофициальная русскоязычная прошивка MeshCore Companion с компактным экранным интерфейсом для пяти плат:

- Heltec T096 с включённым FEM/LNA;
- Heltec T114 с цветным TFT;
- ProMicro nRF52840 + Heltec RA62 + OLED 128×64;
- Heltec V4.3 OLED с включённым FEM/LNA;
- Heltec Wireless Paper с e-paper 250×122.

Текущий предварительный GitHub Release показывает маркер `SmartUI 2.1.0-dev.1`. Hotfix добавляет крупную автоматическую страницу активного BLE PIN на всех пяти платах и заменяет предыдущий `v2.1.0-dev`, но не заменяет RC-линию `v2.0.0-rc1`.

[⬇ Скачать SmartUI v2.1.0-dev.1](https://github.com/YaziAranea/MeshCore/releases/tag/v2.1.0-dev.1) · [Как выбрать файл](RELEASE_NOTES_v2.1.0-dev.1_RU.md#какой-файл-скачать) · [Инструкция по прошивке](docs/FLASHING_RU.md)

![Обзор интерфейса на трёх платах](docs/assets/ui/ui-overview-three-boards.png)

| Heltec V4.3 OLED | Heltec Wireless Paper WOOD |
|---|---|
| ![Часы V4.3 OLED с GPS и тишиной](docs/assets/ui/v4-3-oled-clock.png) | ![Большие часы Wireless Paper](docs/assets/ui/wireless-paper-wood-clock.png) |

[Открыть проект на GitHub](https://github.com/YaziAranea/MeshCore)

> Это независимая модификация. Она не является официальным выпуском MeshCore или IoTThinks. Порт закреплён на коммите [`a3b9ad91`](https://github.com/IoTThinks/MeshCore/commit/a3b9ad91a5bf04e7e00713595469dc868de53628) ветки `PowerSaving-v17` проекта IoTThinks/MeshCore. Новые цели V4.3/Wireless Paper пока проверены сборкой и точной симуляцией, но не объявлены физически испытанными.

Стабильный RC находится в ветке [`smartui-ps17.1`](https://github.com/YaziAranea/MeshCore/tree/smartui-ps17.1). Текущие исправления и новые платы находятся в [`smartui-ps17.2-dev`](https://github.com/YaziAranea/MeshCore/tree/smartui-ps17.2-dev); разницу можно смотреть обычным GitHub compare без ручного переноса файлов.

## Что умеет интерфейс

- Часы, сеть, чат, непрочитанные ЛС, анонс, настройки и выключение без пустых страниц.
- Русский компактный UI, понятные статусы и аккуратное сокращение длинных строк через `...`.
- Экранная клавиатура в быстрых ответах.
- Адресная отправка набранного сообщения в известный чат или companion-контакту; ретрансляторы из списка контактов исключены.
- Окно непрочитанных показывает только личные сообщения, сгруппированные по отправителям.
- Одна общая мелодия важных уведомлений; серия ограничена двумя проигрываниями.
- Ночной запрос тишины в 23:30 с отключением звука до 07:30.
- Выбор шрифта и темы отдельными списками.
- Аппаратный GPS на T096/T114/V4.3 с понятными состояниями `GPS ON/OFF`; на ProMicro и Wireless Paper GPS скрыт.
- Исправлен выход ProMicro из сна: первое нажатие будит OLED без обязательного Reset.
- Калибровка измерения АКБ доступна на всех поддерживаемых платах.
- Исправлены потерянные при PS17-переносе настройки зуммера, чтение ключей `prefs.json`, содержащих цифры, и полная синхронизация времени назад вместе с timestamp сообщений.
- Wireless Paper имеет рекомендуемый профиль `WOOD` и отдельный `FULL` с экранной клавиатурой.
- Случайный активный BLE PIN автоматически и крупно показывается до подключения на всех пяти платах; после связи страница исчезает.

## Поддерживаемые платы

| Плата | Дисплей | GPS в этой цели | Формат development-сборки |
|---|---:|---:|---|
| Heltec T096 FEM ON | TFT 160×80 | Аппаратный | UF2 |
| Heltec T114 с дисплеем | ST7789 240×135 | Аппаратный | UF2 |
| ProMicro nRF52840 + Heltec RA62 | SSD1306 OLED 128×64 | Нет | UF2 |
| Heltec V4.3 OLED FEM ON | SSD1306 OLED 128×64 | Аппаратный | merged + update BIN |
| Heltec Wireless Paper | e-paper 250×122 | Нет | merged + update BIN |

Это не прошивка для FakeTec/HT-RA62, V4 TFT, T114 без дисплея или произвольной ProMicro-распайки. Подробности: [поддерживаемое оборудование](docs/SUPPORTED_BOARDS_RU.md).

## Быстрый старт

Для исправлений зуммера/настроек/времени, калибровки ADC, новых плат и исправленного первого BLE-сопряжения используйте [предварительный Release v2.1.0-dev.1](https://github.com/YaziAranea/MeshCore/releases/tag/v2.1.0-dev.1). Предыдущий `v2.1.0-dev` заменён этим hotfix; [v2.0.0-rc1](https://github.com/YaziAranea/MeshCore/releases/tag/v2.0.0-rc1) остаётся неизменным baseline для T096/T114/ProMicro.

1. Откройте [GitHub Releases](https://github.com/YaziAranea/MeshCore/releases) или артефакты нужного CI-run и скачайте файл строго для своей платы.
2. Из Release берите опубликованный рядом `SHA256SUMS.txt`. В CI-артефакте nRF52 он называется `SHA256SUMS.txt`, в ESP32-S3-артефакте — `SHA256SUMS-ESP32.txt`.
3. Подключите плату исправным USB-кабелем с передачей данных.
4. Для nRF52 переведите плату в UF2-загрузчик быстрым двойным нажатием **Reset**. Для ESP32-S3 используйте Web Flasher или `esptool`.
5. На nRF52 скопируйте UF2 на USB-диск. На V4.3/Wireless Paper используйте `freshInstall-merged.bin` по адресу `0x0` или `update.bin` по адресу `0x10000`.
6. Подключитесь из совместимого MeshCore-клиента. До связи нода автоматически показывает крупную страницу BLE PIN; введите эти шесть цифр, когда клиент или система просит PIN/passkey.

Полная инструкция: [прошивка](docs/FLASHING_RU.md) и [проверка SHA-256](docs/VERIFY_RU.md).

## Управление одной кнопкой

| Действие | Результат |
|---|---|
| Один щелчок | Следующий экран или пункт |
| Двойной щелчок | Предыдущий экран или пункт |
| Долгое нажатие | Выбрать / открыть / подтвердить |
| Долгое нажатие на часах | Включить или выключить тишину |
| Тройной щелчок | Вернуться на главный экран |

Если дисплей погас, первое нажатие может только разбудить его. В первые 8 секунд после старта долгое нажатие включает CLI Rescue, а не выбирает пункт. Полная карта: [управление](docs/CONTROLS_RU.md).

## Сборка из исходников

Установите [PlatformIO](https://platformio.org/install), откройте корень репозитория и выполните нужную команду:

```text
pio run -e Heltec_t096_companion_radio_ble_femon -t create_uf2
pio run -e Heltec_t114_companion_radio_ble -t create_uf2
pio run -e ProMicro_ra62_companion_radio_ble -t create_uf2
pio run -e heltec_v4_3_companion_radio_ble_femon_smartui -t mergebin
pio run -e Heltec_Wireless_Paper_companion_radio_ble_smartui_wood -t mergebin
pio run -e Heltec_Wireless_Paper_companion_radio_ble_smartui_full -t mergebin
```

Для nRF52 получится `firmware.uf2`. Для ESP32-S3 нужны оба файла: `firmware-merged.bin` и `firmware.bin`. Подробная воспроизводимая процедура: [сборка](docs/BUILD_RU.md).

## Важные предупреждения

- Свежие настройки используют радиопрофиль `869.618 MHz / BW 62.5 kHz / SF8 / CR5`. Это не означает, что профиль разрешён в вашей стране.
- T096 работает с внешним FEM; не передавайте без подходящей антенны и не повышайте мощность без измерений.
- Импорт и экспорт приватного ключа включены на уровне companion-протокола. Никому не отправляйте экспортированный ключ и не добавляйте его в Git.
- Phone GPS намеренно не поддерживается: телефон не отдаёт координаты ноде без отдельного приложения или сервиса.
- Обычная прошивка может сохранить старые настройки ноды. Перед обновлением сохраните идентичность безопасным способом и проверьте радиопараметры после запуска.
- На Wireless Paper GPIO45/VEXT питает одновременно дисплей и LoRa-тракт. Не включайте display auto-off и не переносите туда настройки обычного OLED.
- V4.3 и Wireless Paper не имеют заявленного физического зуммера; tone GPIO для них намеренно не выдуман.

Подробнее: [безопасность и радио](docs/SECURITY_RADIO_RU.md).

## Проверки и статус разработки

Локальная QA-проверка hotfix `SmartUI 2.1.0-dev.1` от 2026-08-23:

- Linux/WSL native-тесты: core `69 / 69`, KISS modem `8 / 8`;
- статический контракт: `88 PASS / 0 FAIL`;
- точные framebuffer-симуляции: core/T096/T114 `470 / 470`, V4.3 + ProMicro OLED `25 / 25`, Wireless Paper `180 / 180`.

PIN-страница проверена всеми пятью семействами плат и всеми публичными шрифтами; на OLED 128×64 подсказка компактно пишется «код в приложении».

Финальные локальные размеры hotfix `v2.1.0-dev.1` (`6 / 6 SUCCESS`):

| Плата | RAM | Flash |
|---|---:|---:|
| T096 FEM ON | 63,7% | 77,9% |
| T114 | 64,3% | 78,4% |
| ProMicro RA62 | 62,8% | 93,4% |
| Heltec V4.3 OLED FEM ON | 8,4% | 22,9% |
| Wireless Paper WOOD | 53,2% | 38,8% |
| Wireless Paper FULL | 53,2% | 38,9% |

Read-only CI повторяет сборку, Linux native-тесты, все три набора UI QA, проверку UF2 и трёх ESP32-S3 BIN-пар. T096 симулируется с реальными bitmap-метриками, T114 — через фактическое логическое масштабирование 128×64 → 240×135, OLED-платы — по встроенным glyph-таблицам, Wireless Paper — в физической геометрии 250×122. Приложенные изображения фиксируют визуальный контракт, но не заменяют проверку на реальном устройстве. Новые V4.3/Wireless Paper-профили пока имеют статус development; стабильный `v2.0.0-rc1` не изменён.

## Документация

- [Полное описание проекта](README_RU.md)
- [Поддерживаемые платы](docs/SUPPORTED_BOARDS_RU.md)
- [Управление](docs/CONTROLS_RU.md)
- [Экраны, меню, шрифты и симуляции](docs/SCREENS_RU.md)
- [Прошивка готового UF2 или BIN](docs/FLASHING_RU.md)
- [Сборка из исходников](docs/BUILD_RU.md)
- [Проверка SHA-256](docs/VERIFY_RU.md)
- [Безопасность и радиопараметры](docs/SECURITY_RADIO_RU.md)
- [История изменений](CHANGELOG.md)
- [Примечания к v2.1.0-dev.1](RELEASE_NOTES_v2.1.0-dev.1_RU.md)
- [Примечания к v2.1.0-dev](RELEASE_NOTES_v2.1.0-dev_RU.md)
- [Примечания к v2.0.0-rc1](RELEASE_NOTES_v2.0.0-rc1_RU.md)

## Лицензии и авторство

MeshCore и эта производная работа распространяются по лицензии MIT; исходное уведомление Scott Powell / rippleradios.com сохранено в [LICENSE](LICENSE). Встроенные растровые варианты шрифтов созданы из Roboto Condensed под Apache License 2.0 и четырёх гарнитур под SIL Open Font License 1.1. Полный список и ссылки на тексты лицензий находятся в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
