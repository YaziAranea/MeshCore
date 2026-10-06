# SmartUI 0.12 Local CLI SDK

Локальные CMD66/RESP29 для настроек подключённой ноды. Companion protocol 13
сохранён. SDK не работает с удалённой LoRa-CLI и не поддерживает API201, sync/events
из SmartUI 0.11.

[Русская спецификация](../../docs/SMARTUI_CLI_RU.md).
Обычному пользователю достаточно USB Helper 1.5.

## Состав

- `smartui_cli.py`: кодек и последовательный клиент с prefix correlation.
- `transports.py`: явные USB/TCP адаптеры; TCP использует только стандартную библиотеку.
- `inspect_device.py`: пример только для чтения, без автоматического поиска устройств.
- `../../tools/usb-helper/api.js`: общий JS-кодек и Web Serial клиент, UMD/CommonJS.
- JS-фикстура и тесты включены в Developer Kit. Готового npm/TypeScript-пакета нет.

## Проверки без устройства

Из корня репозитория или распакованного Developer Kit:

~~~sh
python -B -m unittest discover -s tools/smartui-cli/tests -v
node --test tools/usb-helper/test_api.js
~~~

Тесты не открывают реальные USB/BLE/TCP и не означают проверку физической платы.

## Подключение только по явному выбору

Закройте другое приложение, владеющее тем же портом. Для USB выберите на ноде
USB-компаньон, не сервисную консоль. USB требует необязательный пакет `pyserial`,
установленный пользователем; SDK ничего не устанавливает сам.

~~~sh
python tools/smartui-cli/inspect_device.py --usb COM6
python tools/smartui-cli/inspect_device.py --tcp 192.168.1.50 --port 5000
~~~

Это примеры адресов, не указание подключиться к ним. TCP не имеет отдельной
аутентификации/TLS: только доверенная LAN. Не открывайте порт в интернет.
BLE адаптер здесь не поставляется: интегрируйте кодек в общую очередь существующего
BLE клиента, с одним читателем и целыми companion-кадрами подходящего MTU.

## Встраивание Python

~~~python
from smartui_cli import CliClient
import transports

transport = transports.usb("COM6")  # Только после выбора пользователем.
client = CliClient(transport.exchange, transport.close)
try:
    hello = client.connect()  # CMD22/40, marker smartui_cli:1, ui hello.
    print(client.field("get", "volume"))
    # Запись только после подтверждения пользователя:
    # client.execute("ui set volume 5")
    # assert client.field("get", "volume") == "5"
finally:
    client.close()
~~~

`CliClient` не повторяет команды. Тайм-аут означает неизвестный результат:
закройте транспорт, создайте новое подключение и перечитайте состояние.
`ERR ui unsupported` можно пропустить для необязательного поля; readonly не
обходить. Префиксы не переиспользуются в сессии. Не запускайте второй клиент
поверх того же stream и не выводите сырой ответ, команды с паролем или DeviceInfo.

## Встраивание JavaScript

~~~js
const {encodeCommand, decodeReply, matches} = require('../usb-helper/api.js');
const request = encodeCommand('a9', 'ui get volume');
// Передайте request своей ЕДИНОЙ очереди companion; не создавайте второй reader.
// Когда совпал matches(request, response):
// const text = decodeReply(response, 'a9');
~~~

В браузере тот же файл создаёт `SmartUiCli`. `CliClient` владеет Web Serial портом
целиком; для уже работающего приложения используйте кодеки в его собственной очереди.
Теги выбирайте уникально на всю сессию, не копируйте постоянный `a9` из примера.
`decodeReply` допускает UTF-8 штатных команд только с третьим аргументом `false`;
для `ui` оставляйте проверку ASCII.

Для ommesh конкретные точки TS/Rust интеграции приведены в спецификации.
Никакие изменения в сторонний репозиторий этот SDK не вносит.
