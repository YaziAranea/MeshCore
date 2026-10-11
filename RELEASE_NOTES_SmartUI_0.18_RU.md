# Smart UI 0.18 — внешний зуммер на ESP32

Готовые сборки для семи плат, **USB Helper 2.5** и Developer Kit 0.18.
Выпуск добавляет запрос [#5: внешний зуммер](https://github.com/YaziAranea/MeshCore/issues/5).

## Что изменилось

- На **V3 OLED, V4.3 OLED R2, V4 R8 OLED и Wireless Paper FULL** звук можно
  вывести на свободный GPIO через меню, CLI или USB Helper, без пересборки.
- Выход по умолчанию выключен (`tone_pin=-1`). Назначение и отключение
  сохраняются после перезагрузки. Переназначение останавливает старый выход.
- Активный зуммер использует «Пульс» (`melody=0`), пассивный — мелодии 1–30.
  `sound preview` прослушивает выбранную мелодию; `test` проверяет уведомление.
- Для каждой платы задан отдельный список GPIO. Занятые LED/вибрацией выводы
  исключаются; линии GPS V4.3 и кварца Paper в список звука не входят.
- Helper 2.5 позволяет выбрать выход до появления `caps sound=1` и обновляет
  возможности после изменения. Команды 0.17 и формат сохранённых настроек сохранены.
- T096/T114/ProMicro сохраняют прежние звуковые возможности. Для Paper добавлен
  внешний звук; вибрация и переназначение штатного LED не добавлены.
- На Paper отрисовка e-paper откладывается на время мелодии, чтобы обновление
  панели не растягивало импульс. Обработка радио, CLI и защиты батареи сохраняется.

## Подключение и команды

Начните с [инструкции по внешнему зуммеру](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/docs/EXTERNAL_BUZZER_RU.md).
Обозначение «3 В» не определяет допустимый ток GPIO: используйте подходящий
драйвер излучателя с входом логики 3.3 В и общей землёй.

`schema tone_pin` показывает варианты своей платы; `set tone_pin N` назначает,
`set tone_pin -1` отключает. Для активного зуммера — `set melody 0`, затем
`sound preview`. Для уведомлений также нужны звуковой канал и снятый mute.

## Выбор файла

| Плата | Файлы |
| --- | --- |
| T096 FEM ON | `T096_UI_0.18.uf2` |
| T114 | `T114_UI_0.18.uf2` |
| ProMicro RA62 | `ProMicro_RA62_UI_0.18.uf2` |
| Heltec V3 OLED | `Heltec_V3_UI_0.18-merged.bin` / `-update.bin` |
| Heltec V4.3 OLED R2 | `Heltec_V4.3_UI_0.18-merged.bin` / `-update.bin` |
| Heltec V4 R8 OLED | `Heltec_V4_R8_UI_0.18-merged.bin` / `-update.bin` |
| Wireless Paper FULL | `Paper_UI_0.18-merged.bin` / `-update.bin` |

Для ESP32 **update** обновляет приложение с сохранением состояния;
**merged** предназначен для чистой установки и содержит пустую файловую систему.
Не используйте merged, если требуется сохранить данные устройства.

`SmartUI_0.18_all-boards.zip` объединяет полный комплект. Helper ZIP и Developer
Kit содержат инструкции, справочник и матрицу команд. Контрольные суммы и
`RELEASE-MANIFEST.json` привязывают файлы к одному коммиту исходников.

## Проверки и совместимость

Публикация разрешается после полного CI: сборки семи плат и headless-профилей,
проверки nRF52, C++-тесты внешнего звука, CLI/хранилища, браузерные проверки
Helper, симуляция дисплеев и проверка всех одиннадцати образов прошивки.
Физические испытания зуммеров и экземпляров плат не заявляются.

Предыдущий [Smart UI 0.17](https://github.com/YaziAranea/MeshCore/releases/tag/smartui-0.17)
сохранён отдельно. Протокол Companion CLI, совместимость старых команд и
сохранённые пользовательские настройки не требуют миграции.

## Документация

- [Внешний зуммер: подключение и настройка](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/docs/EXTERNAL_BUZZER_RU.md).
- [Команды по семи платам](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/docs/CLI_BOARD_MATRIX_RU.md).
- [Все команды и примеры](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/docs/CONSOLE_COMMANDS_RU.md).
- [Контракт приложения](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/docs/SMARTUI_CLI_RU.md).
- [USB Helper](https://github.com/YaziAranea/MeshCore/blob/smartui-0.18/tools/usb-helper/README_RU.md).
