# SmartUI 0.11 API v1 — specification

> **Archived protocol.** This document applies to release 0.11, preserved with its
> Helper 1.4 and Developer Kit. SmartUI 0.12 does not advertise or accept opcode
> 201 (0xC9); inbox sync and API events are not active. New settings integrations
> should use [Companion CLI 0.12](SMARTUI_CLI_RU.md), CMD66/RESP29. This is a
> deliberate compatibility break, not an automatic transport substitution.

API v1 targets SmartUI 0.11. Discover `smartui_api:1` and inspect HELLO rather
than relying on the version string alone. These files do not claim external
publication or physical-device verification. The base protocol is unchanged.

SmartUI 0.11 adds ecosystem sync/events with `sync=1 events=1`, `stage=release`.
Published 0.10 does not contain these sync commands: it advertises `events=0`
and omits `sync`. Its base settings API remains compatible. Detect extension
features independently rather than relying only on the firmware version.

See the [Russian integration guide](SMARTUI_API_RU.md) for the full workflow and
the [Python reference client](../tools/smartui-api/README.md) for executable tests.

## Session and discovery

Use an existing companion session with its normal transport access. A fresh USB/TCP SDK
session sends standard `CMD_DEVICE_QUERY [22,3]`, then `CMD_GET_CUSTOM_VARS [40]`.
Custom-vars response starts with `21`, followed by comma-separated `key:value`
entries. Require the exact distinct entry `smartui_api:1` before sending `0xC9`.
Missing/unsupported discovery means no extension commands are sent to stock
firmware. Do not renegotiate an application's existing session independently.

Do not log raw companion traffic: standard DEVICE_INFO includes a BLE PIN
field. The supplied inspector does not display that packet.

## Transport envelope

| Transport | Host → device | Device → host |
| --- | --- | --- |
| BLE | Whole companion packet in RX write | Whole companion packet in TX notification |
| USB / TCP | `<` (`0x3C`) + `uint16_le length` + packet | `>` (`0x3E`) + `uint16_le length` + packet |

Length excludes the three envelope bytes. Existing companion maximum: 176 bytes
(179 with USB/TCP envelope). API v1 uses a narrower limit: 160-byte packet,
163 with USB/TCP envelope. A TCP read can contain a partial frame or multiple
frames. Never mix raw text-console lines with binary companion traffic.

BLE service UUID `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`, RX UUID
`6E400002-B5A3-F393-E0A9-E50E24DCCA9E`, TX UUID
`6E400003-B5A3-F393-E0A9-E50E24DCCA9E`. A complete 160-byte API notification requires
negotiated ATT MTU ≥163. Verify actual negotiated capacity, not just requested
MTU. Do not split requests into arbitrary characteristic writes: firmware treats
each write as a complete companion packet. The SDK core can use an existing BLE
dispatcher; this SDK does not bundle a BLE pairing/MTU adapter.

## Extension packet

All integers below are unsigned little-endian. No NUL or newline is transmitted.

Request, 8-byte header:

| Offset | Bytes | Meaning |
| ---: | ---: | --- |
| 0 | 1 | `C9` |
| 1 | 3 | ASCII `SUI` |
| 4 | 1 | Version `1` |
| 5 | 2 | Request ID, 1…65535 |
| 7 | 1 | Operation |
| 8 | variable | Operation payload |

- `0 HELLO`: no payload; new increasing ID.
- `1 EXEC`: 1…152 printable ASCII bytes (`0x20…0x7E`), e.g. `api get`.
- `2 READ_PAGE`: exactly two payload bytes, response offset; use last HELLO/EXEC ID.

Response, 13-byte header:

| Offset | Bytes | Meaning |
| ---: | ---: | --- |
| 0 | 5 | `C9 53 55 49 01` |
| 5 | 2 | Request ID |
| 7 | 1 | Request operation, including `2` for READ_PAGE |
| 8 | 1 | Status |
| 9 | 2 | Payload offset in full response |
| 11 | 2 | Total response-text length |
| 13 | 0…147 | ASCII response fragment |

Maximum response text: 479 bytes (`max_reply=479`). Firmware reserves one NUL
byte in its 480-byte storage. NUL is not sent. First
offset is zero. Request subsequent pages at the number of bytes already received
(normally 147, 294, then 441), keeping the original ID. Validate magic/version,
ID/op/offset, unchanged total/status and all bounds. Reject non-progressing or
overlapping pages. Do not issue a new command before finishing/retrying the old
response: a new command replaces the only cached response.

HELLO ID `0x1234`: `C9 53 55 49 01 34 12 00`.
USB/TCP `api get`, ID 2:
`3C 0F 00 C9 53 55 49 01 02 00 01 61 70 69 20 67 65 74`.

| Status | Meaning |
| ---: | --- |
| 0 | OK |
| 1 | Malformed request |
| 2 | Unsupported version |
| 3 | Unknown operation |
| 4 | Busy |
| 5 | Denied by transport/access/read-only policy |
| 6 | Stale ID, conflicting last ID or unavailable cached request |
| 7 | Command failed; inspect `ERR api CODE` |

Error payloads may be empty. Preserve numeric status. Typical domain codes:
`invalid`, `range`, `unsupported`, `readonly`, `measurement`, `stale`, `storage`,
`unavailable`, `internal`. Never infer success solely from payload text.
Connection setup also uses `transport`, `unconfigured` and `buffer`.
An explicit `busy` reply is a known rejection and is itself cached; replaying
its ID returns the same busy result. Once the condition clears, an operator may
deliberately issue a new attempt with a new ID. This differs from a timeout.

## IDs, replay and disconnection

Serialize requests. New HELLO/EXEC IDs increase strictly within the session;
do not wrap at 65535. Repeating the exact last request bytes with the same ID
returns the cached response without re-executing writes or other side effects.
Older IDs and a conflicting last ID are rejected. READ_PAGE only reads that
last request. USB console changes alone do not clear this transport cache;
actual session disconnection does. ADC preview tokens have independent validity.

A timeout means unknown outcome. Retry the same frame/ID on the same session;
never automatically allocate a new ID for a side effect. After disconnection,
the cache guarantee is gone: reconnect, inspect state, and obtain an operator
decision before repeating an action. A sound test cannot be verified just by
reading persistent settings. The SDK never reconnects or retries automatically.

## Commands and metadata

HELLO schema (values separated by `|` below are alternatives):

```text
OK api hello v=1 firmware=0.11 stage=release max_command=152 max_reply=479 max_frame=160 transport=ble|usb|wifi write=0|1 events=1 sync=1 wifi_setup=0|1
```

Parse additive `key=value` fields without depending on order. Accept unknown
fields. `write` describes this session, not hardware support.
`wifi_setup=1` means Wi-Fi provisioning is supported through this BLE/USB
session; it is zero for TCP and boards without Wi-Fi.

`api caps` fields: `v adc sound board_led unread_led vibration gps
battery_protection display melody_max adc_min adc_max agc_reset fem_lna fem_pa
bridge melody_names`. Capability flags, including `bridge`, are 0/1. `melody_max` is
inclusive; `adc_min`/`adc_max` bound the ADC multiplier, not voltage.

`api get` fields: `battery_mv adc_multiplier adc_default sound_quiet volume
melody board_led unread_led vibration gps battery_protection shutdown_mv muted
agc_reset fem_lna fem_pa bridge`. A zero value does not replace a capability check.

`api connection` fields are `selected via caps wifi_configured wifi_associated
ip readonly`: selected mode, actual request transport, transport capabilities,
Wi-Fi configured/associated flags, IP and read-only. Selected mode and actual
transport are distinct. No SSID,
password, PIN or credentials are returned. Mode changes use `api mode`.
`caps` is a decimal transport bitmask: BLE=1, USB=2, Wi-Fi=4. This is distinct
from the `api caps` record. `selected` is `ble`, `usb` or `wifi`; `via` may also
be `none`. Wi-Fi flags and `readonly` are 0/1; a missing IP is `none`.

| Command | Contract |
| --- | --- |
| `api caps` / `api get` / `api connection` | Read-only records |
| `api melody N` | `OK api melody id=N name_hex=...`; UTF-8 bytes as hex, not playback |
| `api set KEY VALUE` | Validate, persist and apply a supported setting |
| `api adc preview N` | External measured battery voltage, integer mV; returns temporary token |
| `api adc apply TOKEN` | Apply valid preview after explicit confirmation |
| `api adc reset` | Restore default ADC multiplier |
| `api test` | Physical notification test; has side effects |
| `api wifi ...` | Staged network provisioning, described below |
| `api mode ble\|usb\|wifi` | Deferred transport change after response drain |

Settings: booleans `sound_quiet board_led unread_led vibration gps
battery_protection muted agc_reset fem_lna fem_pa bridge`; `volume` 1…10; `melody`
0…`melody_max`. Sound settings require `sound`; other hardware settings require
their respective capability. `sound_quiet=1` disables direct-message notification
sound. Setting `gps` selects hardware GPS as the source. Setting `melody` uses
that melody for all notification types; `muted` also clears `night_quiet`.
These settings select the custom profile and persist, rather than merely changing
temporary UI state. Bridge control requires `caps.bridge=1`.

ADC calibration requires actual external measurement, `adc=1` and `write=1`.
Preview accepts 2500…4500 mV and returns `token sampled_mv measured_mv multiplier`.
Show the proposal before applying. Token expires after 60 seconds and is invalid
if the ADC baseline/settings have changed; successful settings commits may also
invalidate it. On `stale`, obtain a new preview. Read `api get` after success.
Never fabricate a measurement or automatically reset calibration after failure.

In 0.11 ProMicro calibration uses its last battery-only sample, at most 120000 ms
old and taken with the current multiplier: USB can alter the sensed supply.
`sampled_mv` is this reference, not the current USB reading. No eligible sample
returns `ERR api source` (`ERR settings source` in the console) without an apply
token. Run on battery until sampled, connect USB without resetting, then request
preview within two minutes. Resetting/changing the multiplier invalidates the
sample. Other boards retain live sampling. Limits are unchanged; verify the
result with USB disconnected and a meter on the battery itself.

BLE/USB/TCP share existing storage/rescue guards; HELLO `write` reports permission.
TCP supports settings writes with no added authentication or TLS. A network peer
can change settings when guards permit; use a trusted network and do not expose
the listener to the Internet. Wi-Fi provisioning uses BLE/USB so its test does not
destroy the controlling session; same-link TCP provisioning returns `transport`.
The existing USB helper/local UI remain available. Ecosystem commands require
their HELLO flags `sync=1` and/or `events=1`; missing flags mean unsupported.

## Staged Wi-Fi provisioning

Use BLE/USB for credential setup so the candidate-network test cannot break its
own control session. Other settings writes are allowed over TCP; this restriction
is about session continuity, not an added authentication requirement.

1. `api wifi begin` starts a transaction owned by the current session.
2. `api wifi ssid HEX`: 1…32 decoded UTF-8 bytes.
3. `api wifi password HEX`: 8…63 decoded passphrase bytes or a 64-ASCII-hex PSK;
   `api wifi password -` explicitly selects an open network. NUL/control bytes/DEL
   are rejected. A 64-character PSK still needs the outer hex encoding (128 bytes
   of command text); arbitrary 64-character non-hex passwords are invalid.
4. `api wifi test` begins an asynchronous test without persistence.
5. Poll `api wifi status`; only `state=test_ok` permits an explicit `api wifi save`
   while the candidate remains associated. Ask the user before saving.
6. `api wifi cancel` cancels an unfinished transaction and scrubs candidate data.

Hex is reversible encoding, not encryption. Never log either credentials, hex,
raw API frames or SDK `last_request`; never use a command-line password argument.
No reply returns SSID/password. The old saved network is unchanged until a
successful transactional save. On storage failure it is retained and the candidate
can be retried until timeout if storage guards still permit writes. A disconnect scrubs the transaction; do not continue
it in a new session. The existing text wizard and API setup are mutually exclusive.

States: `idle ssid password ready testing test_ok saved failed timeout cancelled`.
Test deadline: 15 seconds. Transaction inactivity timeout: 120 seconds; status
polling does not extend it. Out-of-order steps return `stale`, competing setup
returns `busy`, unsupported hardware returns `unsupported`, unavailable writes
return `readonly`, and provisioning from Wi-Fi transport returns `transport`.

Status fields: `state owner supported configured associated ip ssid_set
password_set mode_pending last_mode_error`. Owner is `api`, `console` or `none`.
The set flags disclose only readiness, not field content; an explicitly open
network also has `password_set=1`. `configured` describes the saved configuration;
`associated` may describe a still-provisional candidate during testing.

SDK methods: `wifi_begin/ssid/password/test/status/save/cancel`. Obtain the password
from a hidden UI or `getpass.getpass()`. No wrapper auto-saves. Python immutable
string/bytes storage cannot be securely erased; minimize credential lifetime and
do not capture process-memory dumps or request history.

## Deferred mode change

`api mode ble|usb|wifi` returns `OK api mode target=... state=pending`, or
`state=active` for the already-selected mode. Wi-Fi requires saved credentials,
otherwise `ERR api unconfigured`. Only one operation can be pending.

Pending is not final success. Firmware waits for successful reply queueing,
at least 100 ms and an empty transport TX queue before saving/applying the mode.
If this cannot complete within two seconds, it cancels rather than switching
without an ACK. Session loss or a read-only transition cancels pending work.
Queue drain is not proof that the peer actually read the reply.

Application can disconnect the old transport. Reconnect using the new transport,
repeat discovery/HELLO and verify `api connection`. If it did not switch,
`api wifi status` exposes `mode_pending` and `last_mode_error`: `none`, `timeout`,
`cancelled`, `readonly`, `storage` or `apply`. Do not treat a queued reply as
successful persistence or automatically loop reconnects/new-ID writes.

## Optional ecosystem synchronization

This additive extension retains the base companion frame format and radio
protocol. Device state synchronization is not an over-the-air read receipt.
Legacy clients keep their existing behavior unless their session opts in.

Message identity is `(boot, id)`: boot is 16 lowercase hexadecimal digits,
nonzero; id is an 8-lowercase-hex nonzero generation within that boot. Never
substitute a timestamp, queue index or request ID. Sequence/revision/cursor are
decimal uint32 values, shared across all event categories. State is volatile:
32 records and 32 events, retained across transport reconnect but not reboot.
This is a bounded working set, not a complete chat archive.

Commands and representative response schemas (`BOOT`, `ID`, etc. are placeholders):

```text
api sync enable|disable|status
OK api sync boot=BOOT explicit=0|1 subscribed=MASK cursor=N oldest=N revision=N count=N capacity=32

api inbox snapshot
OK api inbox snapshot boot=BOOT revision=REV count=N cursor=N capacity=32
api inbox item BOOT REV INDEX
OK api inbox item boot=BOOT revision=REV index=INDEX id=ID flags=N state=N snooze=N snoozable=0|1

api inbox next
OK api inbox next boot=BOOT id=ID flags=N frame_hex=HEX
OK api inbox empty=1 boot=BOOT

api inbox received BOOT ID
api inbox read BOOT ID
api inbox dismiss BOOT ID
api inbox snooze BOOT ID SECONDS
OK api inbox read id=ID state=N changed=0|1

api notify status
OK api notify active=0|1 id=ID muted=0|1
```

The ACK response substitutes the actual action name for `read`. Additive
`tracked=0` is possible when received commits an exact still-queued frame whose
32-record ledger entry was evicted; it does not resurrect that entry. Unknown
objects return `ERR api gone`, never retargeting the queue head. Notification
status refers to the logical active/pending chain, not instantaneous audio or
vibration pin state. Its id can be zero; obtain boot from the current sync status.

`enable` opts this session into explicit receive/read behavior. It is required
for inbox next and actions, not snapshots or event reads. `disable` clears the
subscription too. Disconnect clears opt-in/subscription, not the per-boot log.
Use one coordinated message consumer after opting in, not an independent legacy
queue reader alongside it. Session opt-in is not a persistent board setting.
Enable/disable and ACK actions require `write=1`; snapshots/subscriptions do not.
Next/actions without opt-in return `ERR api negotiate`.

| Operation | Meaning | Does not imply |
| --- | --- | --- |
| next | Peek exact existing companion frame together with its identity | Delivery or reading |
| received | App accepted this exact frame; commit its delivery queue entry | Human read |
| read | Explicit human-read acknowledgement | Delivery queue consumption |
| dismiss | Dismiss notification | Read acknowledgement |
| snooze | Pause a supported retained preview, 1…86400 seconds | Read acknowledgement |

State bits: RECEIVED=1, READ=2, DISMISSED=4, SNOOZED=8. Read/dismiss clear snooze;
snooze clears dismiss. Repeating identical active snooze seconds is unchanged
and does not extend it, including across reconnect. Resume is internal expiry,
not an app command. Snapshot `snooze` is configured duration, not a remaining-time
countdown. `changed=0` is a successful no-op. Item `snoozable=1` means a supported
preview is still retained on the node (currently a direct message). Missing
field does not establish support; unsupported snooze has no side effect.
Read/dismiss also work for channel notifications. Firmware remains authoritative
if preview availability changes after the snapshot.

Persist/deduplicate a delivered frame and its `(boot,id)` before received. Only
send read on a UI action/visibility rule that represents actual human reading,
never merely on a BLE notification or background fetch. A device-local Read
event updates the app without an echo read command. Generation is assigned to
all queued frames for exact received ACKs, but only human plaintext messages
enter the 32-record ledger. Telemetry/CLI/data frames remain retrievable via
frame_hex without creating unread state or an inbox record. `flags=0` is ambiguous:
interpret human vs data using the ordinary companion frame parser. `frame_hex`
is exact deframed message data, not safe diagnostic metadata; do not log it.

### Snapshots, reconnect and gaps

Read snapshot metadata, then indices 0…count-1 with the same boot/revision.
`ERR api changed` invalidates the partial snapshot; restart a bounded number of
times. The SDK defaults to three read-only attempts, then surfaces failure.
Each individual paginated response is already stable in the normal API cache.
Snapshot cursor equals revision. Missing entries are evicted/unknown, not
automatically read; do not erase local chat history from this limited view.

Start by subscribing, taking an inbox snapshot, and reading settings/connection/
notification snapshots. Pull from the inbox snapshot cursor, apply events in
sequence, then advance the applied cursor. Store app state and cursor atomically
if persisted. A gap/reboot requires fresh snapshots; do not guess lost events
or mass-clear unread. A new transport session requires discovery/HELLO, opt-in
and subscription again. Same boot plus a persisted consistent app state/cursor
can resume from the log; otherwise snapshot. New boot invalidates old IDs even
when generation numbers happen to match.

Timeout/replay rules are unchanged: retry the exact last request only on the same
session; never automatically repeat a mutation with a new ID after reconnect.
Explicitly inspected read/received actions are idempotent, but this is not a
general permission to retry arbitrary side effects.

### Pull log and bounded push hints

```text
api events subscribe MASK
OK api events subscribed=MASK boot=BOOT cursor=N
api events next BOOT CURSOR
OK api event boot=BOOT seq=N id=ID kind=N state=N flags=N value=N key=N
OK api events end=1 boot=BOOT cursor=N
ERR api gap boot=BOOT oldest=N cursor=N
ERR api boot boot=BOOT
```

Mask bits: messages/notifications=1, settings=2, connection=4, battery=8; all=15,
unsubscribe=0. Mask filters push hints only. Pull returns **all** categories to
keep the cursor contiguous. Neither the subscription response cursor nor a hint
cursor may replace the last applied cursor. `end=1` is not a message read ACK.
The gap error cursor is the current log head, not permission to skip lost events;
obtain fresh snapshots before adopting a new baseline.

| kind | Meaning | value/key |
| ---: | --- | --- |
| 1 | Message | New record/frame |
| 2 | Received | App delivery acknowledged |
| 3 | Read | App or device-local human read |
| 4 | Dismissed | Notification dismissed |
| 5 | Snoozed | value = requested seconds |
| 6 | Resumed | Internal snooze expiry |
| 7 | Setting | key=0 invalidates settings snapshot; value is a fingerprint, not settings |
| 8 | Connection | value bits0–1 selected mode (BLE0/USB1/Wi-Fi2), bit2 client connected, bit3 associated, bit4 configured |
| 9 | Battery | value = cached mV; key1 normal/key2 low/key3 unknown |
| 10 | Notification | value0/1 inactive/active logical chain, key0 |

Setting observes the settings exposed by this API, not every screen-menu field.
The observer compares state once per second and can coalesce rapid changes.
It invalidates the settings view; it is not an audit log of each save. Brightness
and other fields not yet exposed by the API are outside this observation set.

Non-message events use id zero. Read `api get` for Setting, and `api connection`
for full connection metadata. Preserve/ignore additive future fields and kinds
safely rather than failing the entire stream. Individual short physical pulses
are not guaranteed as separate events.

Battery is informational, not shutdown policy. Key3 means no cached sample or
sample age greater than 120000ms; do not display its value as a current reading.
Low begins at ≤3300mV and remains low until 3400mV (hysteresis); this does not
replace `shutdown_mv`. Voltage delta events use 50mV relative to the last emitted
Battery event, allowing small successive sample changes to accumulate. The SDK
preserves numeric key; `BatterySampleState` names NORMAL1/LOW2/UNKNOWN3. API
polling does not require forcing a new ADC sample every time.

Push uses the usual 13-byte response header with **id=0, op=3, status=0,
offset=0**, total equal to its one ASCII body length (no READ_PAGE):

```text
EV api events boot=BOOT cursor=N mask=MASK
```

It fits the same 160-byte maximum. Hints are coalesced, subscription-only and
rate-limited to at most 4Hz. They only say to inspect the authoritative pull log.
Poll the log periodically even without hints; a lost hint must not stall sync.
Callbacks queue/coalesce hints and return. Pull from the main loop afterwards;
never make a reentrant API request from a push callback. Ordinary companion
pushes still go to their existing handler.

SDK: `SmartUISync(client)` reuses the same request-ID allocator. `status`,
`enable`, `disable`, `notification_status`, `subscribe`, `snapshot`, `item`,
`next_message`, `received`, `read`, `dismiss`, `snooze`, `next_event` expose the
commands. `HintMailbox` keeps one coalesced hint. `EventCursor(snapshot)` rejects
future sequence gaps/boot changes, ignores duplicate/older events, and does not
advance until `accept(event)`. Call `check(event)`, apply, then `accept(event)`.
`EventCursor.next_event(sync)` marks gap/boot API errors as needing a fresh
snapshot. `StreamExchange.poll(timeout=0.1)` processes idle incoming frames;
timeout zero drains buffered frames only. No background thread is created.

```python
from ecosystem import SmartUISync, EventCursor, EventEnd

sync = SmartUISync(api)  # Same already-discovered SmartUIClient.
if hello.get("sync") == "1" and hello.get("events") == "1":
    sync.enable()  # Deliberate session opt-in; not a persistent setting.
    sync.subscribe(15)
    baseline = sync.snapshot()
    replace_device_inbox_view(baseline)  # App hook; preserve chat history.
    cursor = EventCursor(baseline)
    for _ in range(32):  # Bounded work per event-loop iteration.
        event = cursor.next_event(sync)
        if isinstance(event, EventEnd):
            break
        if cursor.check(event):
            apply_device_event(event)  # App hook; no echo read command.
            cursor.accept(event)
```

Catch `ApiError` for gap/boot and `RecoveryRequired` for invalid sequence/epoch;
replace the cursor only after complete recovery. Read other category snapshots
too; the inbox snapshot is not a settings/connection snapshot. Integration hooks
above belong to the app, not the SDK. See the Russian guide for frame delivery
and acknowledgement examples.

## Python and application integration

Python 3.10+; standard-library core/TCP, optional `pyserial` for USB. From the
repository root, replacing placeholder arguments:

```sh
python tools/smartui-api/inspect_device.py tcp HOST PORT
python tools/smartui-api/inspect_device.py usb SERIAL_PORT
python -B -m unittest discover -s tools/smartui-api/tests -v
```

The inspector only reads. Select framed USB mode or preconfigure Wi-Fi.
Closing competing serial clients is required;
opening some USB serial ports can reset the board.

```python
from smartui_api import SmartUIClient

api = SmartUIClient(exchange)  # bytes -> bytes, deframed, same live session
hello = api.hello()            # Automatically performs safe discovery first.
capabilities = api.caps()
settings = api.get()
connection = api.connection()
```

`execute()` returns assembled ASCII text; convenience methods return dictionaries
of strings. Validate numbers and required fields in your UI. After an ambiguous
timeout, call `retry_last()` only if the original session is still alive; a new
request is blocked by `PendingRequestError`. `ApiError` exposes status, text and
request_id. Malformed/mismatched data raises `ProtocolError`.

The provided stream adapter routes unrelated packets through `on_packet`, or
retains up to 64 in `unsolicited`. Call `poll()` for idle reception; it is not a background event loop. Production
apps should use one shared companion dispatcher that routes existing asynchronous
pushes and correlates API replies by magic, ID, operation and offset. Do not run
competing stream readers or independent request-ID allocators in one session.

The tests cover discovery refusal, byte order, bounds, pagination, same-ID replay,
timeouts, errors, push dispatch, split/coalesced frames and a real local socket
round-trip. These are not BLE/USB/Wi-Fi hardware acceptance or endurance tests.
Ecosystem simulations additionally cover received vs read, exact ACK identity,
dismiss/snooze, local-read reverse sync, snapshot mutation/retry bounds, ring
overflow, reconnect/reboot, duplicates/gaps and coalesced/fragmented hints.

## Local development package

From the source root, supply the full 40-character base commit SHA:

```sh
python -B tools/package_smartui_developer_kit.py OUTPUT_DIR --development --base-commit BASE_COMMIT
```

Output is `SmartUI_Developer_Kit_0.11-development.zip`, never the release ZIP name.
Manifest fields include `stage=development`, `distribution=local`,
`base_firmware_version`, `base_source_commit`, `source_snapshot=working-tree`,
`exact_source_commit=false`. The base is provenance only, not an exact commit
claim for edited files. Per-file manifest/SHA256SUMS hashes identify actual bytes.

Only the explicit SDK/tests/guides/license allowlist is included; no recursive
collection of local notes, caches or credentials. Existing artifacts are never
overwritten. No commit, upload or flash occurs. Default release mode (`--commit
EXACT_SOURCE_COMMIT`, no `--development`) preserves the prior contract and relies
on the release workflow's exact-source validation. It creates
`SmartUI_Developer_Kit_0.11.zip` with `stage=release`. Do not use it to label an
arbitrarily changed development snapshot as an exact-source release kit.
