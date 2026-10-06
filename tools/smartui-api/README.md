# SmartUI 0.10 API — Python reference client

API v1 targets SmartUI 0.10. Discover `smartui_api:1` and inspect HELLO rather
than relying only on the firmware version. Source, protocol tests and examples
are not a claim of physical-device verification or external publication.

The core uses Python 3.10+ and the standard library. The optional USB adapter
requires `pyserial`; nothing is installed automatically. TCP uses the standard
library. There is no bundled BLE adapter: integrate the core with an existing
authenticated BLE companion dispatcher. Do not use USB text-console commands
inside a framed companion session.

- [Russian integration guide](../../docs/SMARTUI_API_RU.md)
- [English wire specification](../../docs/SMARTUI_API_EN.md)
- `smartui_api.py`: discovery, HELLO, framing validation, pagination, explicit replay.
- `transports.py`: strict incremental USB/TCP framing and push dispatch.
- `inspect_device.py`: read-only example; no setting or Wi-Fi configuration writes.
- `tests/`: mocked protocol tests and a fragmented local socket round-trip.

## Run tests

From the repository root:

```sh
python -B -m unittest discover -s tools/smartui-api/tests -v
```

## Inspect a development build

Close any app already owning the same companion session. Select the transport
on the device first. Wi-Fi must already be configured. Opening a serial port can
reset some boards.
Replace `HOST`, `PORT` and `SERIAL_PORT` below with your own values:

```sh
python tools/smartui-api/inspect_device.py tcp HOST PORT
python tools/smartui-api/inspect_device.py usb SERIAL_PORT
```

The inspector sends a standard read-only `DEVICE_QUERY`, then custom-variable
discovery. It sends no `0xC9` extension command unless `smartui_api:1` is present.
It prints only HELLO, capabilities, settings and sanitized connection metadata.
It does not print the raw standard `DEVICE_INFO` packet, which includes a BLE
PIN field in the base companion protocol.

TCP permits settings writes under the same storage/rescue guards, without added
authentication or TLS. Use only a trusted network; do not publish the listener
to the Internet. Wi-Fi credentials are staged/tested/saved through this API over
BLE/USB so the provisioning session survives the network test. The USB helper
also remains supported. Mode changes are available through all transports and
can disconnect the current client after its response drains.

## Embed the core

From a script with `tools/smartui-api` on its module path:

```python
from smartui_api import SmartUIClient

# Existing companion session, already authenticated/approved by its transport.
# exchange(packet) sends one deframed packet and waits for its matching reply.
# It must dispatch unrelated companion pushes without treating them as replies.
client = SmartUIClient(exchange)
hello = client.hello()          # Includes safe feature discovery.
capabilities = client.caps()
settings = client.get()
connection = client.connection()
```

Create one `SmartUIClient` per session and serialize requests. Do not share its
session with another extension client using independent request IDs. Do not
reset IDs or create another client merely because a call timed out.

After a timeout, the command **may already have executed**. `retry_last()` sends
the exact original request on the same session and reads its cached pages.
It never reconnects. If the connection was lost, the replay guarantee ended:
reconnect, read the resulting state and ask the operator before repeating a
side effect. See the full guide for ADC calibration and error handling.

## Wi-Fi setup and mode changes

`wifi_begin()`, `wifi_ssid(value)`, `wifi_password(value)`, `wifi_test()`,
`wifi_status()`, `wifi_save()` and `wifi_cancel()` expose the staged workflow.
Poll until `state=test_ok`, ask for confirmation, then explicitly save. No method
automatically tests/saves credentials or switches the transport. Never log the
password, its hex encoding, raw request frames or `last_request`; Python strings
and bytes cannot be securely erased. Empty password explicitly means open Wi-Fi.

`set_mode("ble" | "usb" | "wifi")` returns `state=pending` until deferred
application. That response is not proof of successful persistence or reconnection;
verify selected mode on the new session. Unconfigured Wi-Fi cannot be selected by
this command. Read the guides before integrating these side effects.

## Current limits

No events/subscriptions, no credential readback, no Wi-Fi provisioning over the
same TCP link being reconfigured, no automatic retries/background reconnection,
and no BLE pairing/MTU management. Bridge control follows the board capability.
BLE applications must supply correct whole-packet
delivery and adequate negotiated ATT payload size. Unit tests validate SDK
behavior; device acceptance and transport endurance tests are separate work.
