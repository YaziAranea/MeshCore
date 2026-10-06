# SmartUI 0.10 API v1 — specification

API v1 targets SmartUI 0.10. Discover `smartui_api:1` and inspect HELLO rather
than relying on the version string alone. These files do not claim external
publication or physical-device verification. The base protocol is unchanged.

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
OK api hello v=1 firmware=0.10 stage=release max_command=152 max_reply=479 max_frame=160 transport=ble|usb|wifi write=0|1 events=0 wifi_setup=0|1
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

BLE/USB/TCP share existing storage/rescue guards; HELLO `write` reports permission.
TCP supports settings writes with no added authentication or TLS. A network peer
can change settings when guards permit; use a trusted network and do not expose
the listener to the Internet. Wi-Fi provisioning uses BLE/USB so its test does not
destroy the controlling session; same-link TCP provisioning returns `transport`.
The existing USB helper/local UI remain available. Events are not implemented:
`events=0` is explicit, not an undocumented subscription feature.

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
retains up to 64 in `unsolicited`. It is not a background event loop. Production
apps should use one shared companion dispatcher that routes existing asynchronous
pushes and correlates API replies by magic, ID, operation and offset. Do not run
competing stream readers or independent request-ID allocators in one session.

The tests cover discovery refusal, byte order, bounds, pagination, same-ID replay,
timeouts, errors, push dispatch, split/coalesced frames and a real local socket
round-trip. These are not BLE/USB/Wi-Fi hardware acceptance or endurance tests.
