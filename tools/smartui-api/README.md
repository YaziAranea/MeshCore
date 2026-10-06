# SmartUI 0.11 API — Python reference client

> Archived with firmware 0.11. SmartUI 0.12 disables API201, sync and events.
> New integrations use the [local Companion CLI SDK](../smartui-cli/README.md).
> This directory is retained for reference; its firmware-integration tests must
> be run against the preserved 0.11 source, not the active 0.12 dispatcher.

API v1 targets SmartUI 0.11. Discover `smartui_api:1` and inspect HELLO rather
than relying only on the firmware version. Source, protocol tests and examples
are not a claim of physical-device verification or external publication.

SmartUI 0.11 adds the ecosystem extension. Require HELLO `sync=1` / `events=1`;
published 0.10 does not provide these sync commands (`sync` absent, `events=0`),
but its base settings API remains compatible. Tests do not imply physical validation.

The core uses Python 3.10+ and the standard library. The optional USB adapter
requires `pyserial`; nothing is installed automatically. TCP uses the standard
library. There is no bundled BLE adapter: integrate the core with an existing
authenticated BLE companion dispatcher. Do not use USB text-console commands
inside a framed companion session.

- [Russian integration guide](../../docs/SMARTUI_API_RU.md)
- [English wire specification](../../docs/SMARTUI_API_EN.md)
- `smartui_api.py`: discovery, HELLO, framing validation, pagination, explicit replay.
- `ecosystem.py`: exact message identities, explicit received/read ACKs, snapshots,
  dismiss/snooze, bounded hint mailbox and event cursor/gap recovery.
- `transports.py`: strict incremental USB/TCP framing and push dispatch.
- `inspect_device.py`: read-only example; no setting or Wi-Fi configuration writes.
- `tests/`: mocked protocol tests and a fragmented local socket round-trip.

## Run tests

From the repository root:

```sh
python -B -m unittest discover -s tools/smartui-api/tests -v
```

## Inspect a supported device

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

No credential readback, no Wi-Fi provisioning over the
same TCP link being reconfigured, no automatic retries/background reconnection,
and no BLE pairing/MTU management. Bridge control follows the board capability.
BLE applications must supply correct whole-packet
delivery and adequate negotiated ATT payload size. Unit tests validate SDK
behavior; device acceptance and transport endurance tests are separate work.

## Optional ecosystem integration

```python
from ecosystem import SmartUISync

sync = SmartUISync(client)  # Reuse the existing request-ID allocator.
if hello.get("sync") == "1":
    status = sync.status()       # Read-only; does not enable explicit mode.
    snapshot = sync.snapshot()   # Consistent bounded view, not chat history.
```

Call `enable()` deliberately before explicit message delivery/ACKs. `next_message()`
peeks an exact companion frame plus `(boot,generation)` and does not consume it.
After app storage/deduplication, `received(identity)` consumes that exact queue
entry but leaves unread. Only a real human read triggers `read(identity)`.
`dismiss` and `snooze` affect notification behavior, not reading. Snooze needs a
retained supported preview (`InboxRecord.snoozable`), currently a direct message.
A device-local
Read event updates app UI without sending an echo read command.

For events require `events=1`, subscribe to a bitmask, then use the pull log.
Push op3/id0 packets are hints only: route them into `HintMailbox` from the shared
dispatcher, pull outside its callback, and use `EventCursor` to detect gaps,
duplicates and reboot. Do not advance to a hint's cursor. Read the guides for
snapshot recovery and reconnect; both device records and log are bounded to 32.
Only human plaintext messages enter the record ledger; service/data frames have
exact delivery IDs too, but do not become unread inbox entries.
Use `transport.poll()` from the same owner loop for idle hints. No second reader
or background retry thread is started by the SDK.

Battery events are informational: `BatterySampleState` maps normal=1/low=2/unknown=3.
Unknown means a missing or older-than-120000ms cached measurement; ignore value as
a current voltage. Low ≤3300mV clears at 3400mV; this is not `shutdown_mv`. A 50mV
delta is measured from the last emitted event, not the immediately previous sample.

## Create a local development kit

From the repository root (packager is a source-tree tool, not bundled in the kit):

```sh
python -B tools/package_smartui_developer_kit.py OUTPUT_DIR --development --base-commit BASE_COMMIT
```

Replace BASE_COMMIT with the full 40-character provenance commit SHA. Output uses
the distinct `SmartUI_Developer_Kit_0.11-development.zip` name, development/local
manifest, base version/commit and hashes of actual working-tree bytes. It does
not claim these edited files are exact-source release files. Existing files
are not overwritten; nothing is uploaded or installed. Default release mode
remains separate and requires an exact-source validated release workflow; its
artifact is `SmartUI_Developer_Kit_0.11.zip` with `stage=release` and USB Helper 1.4 guidance.
