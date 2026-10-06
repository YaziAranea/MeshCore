"""SmartUI 0.10 API v1. No third-party dependencies in the core.

An exchange accepts and returns one *deframed* companion packet. It must
serialize access to its session and dispatch unrelated companion push packets.
Never reconnect transparently after a timeout: the replay cache is session-local.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable

MAGIC = b"\xc9SUI"
VERSION = 1
MAX_COMMAND = 152
MAX_REPLY = 479
MAX_FRAME = 160
MAX_PAGE = 147
REQUEST = struct.Struct("<4sBHB")
RESPONSE = struct.Struct("<4sBHBBHH")


class Op(IntEnum):
    HELLO = 0
    EXEC = 1
    READ_PAGE = 2


class Status(IntEnum):
    OK = 0
    MALFORMED = 1
    BAD_VERSION = 2
    UNKNOWN_OP = 3
    BUSY = 4
    DENIED = 5
    STALE = 6
    COMMAND_FAILED = 7


class ProtocolError(ValueError):
    """Invalid or mismatched reply; a write's outcome may be unknown."""


class UnsupportedError(RuntimeError):
    """Discovery did not advertise the supported extension version."""


class PendingRequestError(RuntimeError):
    """Resolve the last request before allocating another request ID."""


class ApiError(RuntimeError):
    def __init__(self, status: Status, text: str, request_id: int):
        self.status = status
        self.text = text
        self.request_id = request_id
        super().__init__(f"SmartUI status {int(status)} ({status.name}): {text}")


@dataclass(frozen=True)
class Page:
    request_id: int
    op: Op
    status: Status
    offset: int
    total: int
    payload: bytes


def encode_request(request_id: int, op: Op, payload: bytes = b"") -> bytes:
    if not 1 <= request_id <= 65535:
        raise ValueError("request ID must be in 1..65535")
    op = Op(op)
    if op == Op.HELLO and payload:
        raise ValueError("HELLO has no payload")
    if op == Op.EXEC and (
        not 1 <= len(payload) <= MAX_COMMAND
        or any(byte < 0x20 or byte > 0x7E for byte in payload)
    ):
        raise ValueError("EXEC requires 1..152 printable ASCII bytes, without NUL/newline")
    if op == Op.READ_PAGE and len(payload) != 2:
        raise ValueError("READ_PAGE requires a uint16 little-endian offset")
    return REQUEST.pack(MAGIC, VERSION, request_id, op) + payload


def decode_page(packet: bytes) -> Page:
    if not RESPONSE.size <= len(packet) <= MAX_FRAME:
        raise ProtocolError("response length outside 13..160")
    magic, version, request_id, op, status, offset, total = RESPONSE.unpack_from(packet)
    if magic != MAGIC or version != VERSION or request_id == 0:
        raise ProtocolError("invalid response magic, version, or request ID")
    try:
        op, status = Op(op), Status(status)
    except ValueError as exc:
        raise ProtocolError("unknown response operation or status") from exc
    payload = packet[RESPONSE.size:]
    if total > MAX_REPLY or offset > total or offset + len(payload) > total:
        raise ProtocolError("invalid response offset or total length")
    if not payload and offset < total:
        raise ProtocolError("empty page would prevent pagination progress")
    return Page(request_id, op, status, offset, total, payload)


def parse_record(text: str, prefix: str) -> dict[str, str]:
    """Read an additive key=value record; preserve unknown fields for callers."""
    if text != prefix and not text.startswith(prefix + " "):
        raise ProtocolError(f"expected {prefix!r} record")
    fields: dict[str, str] = {}
    for item in text[len(prefix):].split():
        if "=" not in item:
            raise ProtocolError("record contains a non key=value field")
        key, value = item.split("=", 1)
        if not key or not value or key in fields:
            raise ProtocolError("empty or duplicate record field")
        fields[key] = value
    return fields


def melody_name(text: str) -> str:
    fields = parse_record(text, "OK api melody")
    try:
        encoded = fields["name_hex"]
        if not encoded or len(encoded) % 2 or any(c not in "0123456789abcdefABCDEF" for c in encoded):
            raise ValueError("invalid hex")
        return bytes.fromhex(encoded).decode("utf-8")
    except (KeyError, ValueError, UnicodeError) as exc:
        raise ProtocolError("invalid UTF-8 melody name") from exc


class SmartUIClient:
    """One client per already-established companion session; not thread-safe.

    Call hello() before execute(). Discovery is automatic and fail-closed.
    Timeout/OSError/invalid replies leave the original request pending. Call
    retry_last() on the SAME session, or close and investigate before reconnecting.
    New requests are blocked while a prior request has an unknown outcome.
    """

    def __init__(self, exchange: Callable[[bytes], bytes], *, first_id: int = 1):
        if not 1 <= first_id <= 65535:
            raise ValueError("first_id must be in 1..65535")
        self.exchange = exchange
        self._next_id = first_id
        self._supported = False
        self._last: bytes | None = None
        self._pending = False
        self.hello_info: dict[str, str] | None = None

    @property
    def pending(self) -> bool:
        return self._pending

    @property
    def last_request(self) -> bytes | None:
        """Original HELLO/EXEC bytes, never the last pagination request."""
        return self._last

    def discover(self) -> bool:
        if self._pending:
            raise PendingRequestError("retry_last() required before discovery")
        packet = self.exchange(bytes([40]))  # Existing CMD_GET_CUSTOM_VARS.
        if not packet or packet[0] != 21:
            raise ProtocolError("expected RESP_CODE_CUSTOM_VARS (21)")
        entries = packet[1:].rstrip(b"\0").split(b",")
        values = [entry.split(b":", 1)[1] for entry in entries if entry.startswith(b"smartui_api:")]
        self._supported = values == [b"1"]
        return self._supported

    def hello(self) -> dict[str, str]:
        if not self._supported and not self.discover():
            raise UnsupportedError("smartui_api:1 not advertised; no extension request sent")
        return self._hello_record(self._request(Op.HELLO))

    def _hello_record(self, text: str) -> dict[str, str]:
        fields = parse_record(text, "OK api hello")
        expected = {"v": "1", "max_command": "152", "max_reply": "479", "max_frame": "160"}
        if any(fields.get(key) != value for key, value in expected.items()):
            raise ProtocolError("unsupported HELLO version or limits")
        if fields.get("write") not in ("0", "1") or fields.get("transport") not in ("ble", "usb", "wifi"):
            raise ProtocolError("invalid HELLO permissions or transport")
        self.hello_info = fields
        return fields

    def execute(self, command: str) -> str:
        if self.hello_info is None:
            raise RuntimeError("call hello() on this session first")
        if not command.startswith("api "):
            raise ValueError("only the api command namespace is supported")
        try:
            payload = command.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("commands must use printable ASCII") from exc
        # Validate before reserving an ID. Firmware remains the authority.
        encode_request(1, Op.EXEC, payload)
        return self._request(Op.EXEC, payload)

    def caps(self) -> dict[str, str]:
        return parse_record(self.execute("api caps"), "OK api caps")

    def get(self) -> dict[str, str]:
        return parse_record(self.execute("api get"), "OK api get")

    def connection(self) -> dict[str, str]:
        return parse_record(self.execute("api connection"), "OK api connection")

    def wifi_status(self) -> dict[str, str]:
        return parse_record(self.execute("api wifi status"), "OK api wifi")

    def wifi_begin(self) -> str:
        """Begin a session-bound transaction over BLE/USB, never over TCP."""
        self._wifi_write_guard()
        return self.execute("api wifi begin")

    def wifi_ssid(self, ssid: str) -> str:
        self._wifi_write_guard()
        value = ssid.encode("utf-8")
        self._validate_secret(value, 1, 32)
        return self.execute("api wifi ssid " + value.hex())

    def wifi_password(self, password: str) -> str:
        """Send a secret without echoing it. Empty string explicitly means open Wi-Fi.

        Do not log this call, the encoded command, exchange packets or last_request.
        Python immutable string/bytes memory cannot be securely erased by this SDK.
        """
        self._wifi_write_guard()
        value = password.encode("utf-8")
        self._validate_secret(value, 8 if value else 0, 64)
        if len(value) == 64 and any(byte not in b"0123456789abcdefABCDEF" for byte in value):
            raise ValueError("64-byte Wi-Fi password must be a hexadecimal PSK")
        return self.execute("api wifi password " + (value.hex() if value else "-"))

    def wifi_test(self) -> str:
        self._wifi_write_guard()
        return self.execute("api wifi test")

    def wifi_save(self) -> str:
        """Explicit commit after a polled test_ok; never auto-save from a test."""
        self._wifi_write_guard()
        return self.execute("api wifi save")

    def wifi_cancel(self) -> str:
        self._wifi_write_guard()
        return self.execute("api wifi cancel")

    def set_mode(self, mode: str) -> str:
        """Request a deferred transport change; pending is not final success."""
        if mode not in ("ble", "usb", "wifi"):
            raise ValueError("mode must be ble, usb or wifi")
        if not self.hello_info or self.hello_info.get("write") != "1":
            raise PermissionError("session does not permit mutations")
        return self.execute("api mode " + mode)

    def _wifi_write_guard(self):
        if not self.hello_info or self.hello_info.get("write") != "1":
            raise PermissionError("session does not permit mutations")
        if self.hello_info.get("transport") not in ("ble", "usb"):
            raise PermissionError("Wi-Fi provisioning needs BLE/USB to preserve its test session")

    @staticmethod
    def _validate_secret(value: bytes, minimum: int, maximum: int):
        if not minimum <= len(value) <= maximum or any(byte < 0x20 or byte == 0x7F for byte in value):
            raise ValueError("invalid Wi-Fi field length or control characters")

    def _request(self, op: Op, payload: bytes = b"") -> str:
        if self._pending:
            raise PendingRequestError("last outcome unknown; use retry_last() on the same session")
        if self._next_id > 65535:
            raise RuntimeError("request IDs exhausted; close and create a new session (do not wrap IDs)")
        frame = encode_request(self._next_id, op, payload)
        self._next_id += 1
        self._last = frame
        return self._perform(frame)

    def retry_last(self) -> str:
        """Explicit same-ID replay; no automatic retry or reconnect."""
        if self._last is None:
            raise RuntimeError("no request to retry")
        text = self._perform(self._last)
        if self._last[7] == Op.HELLO:
            self._hello_record(text)
        return text

    def _perform(self, frame: bytes) -> str:
        self._pending = True
        _, _, request_id, op = REQUEST.unpack_from(frame)
        page = self._checked_page(frame, request_id, Op(op), 0)
        data = bytearray(page.payload)
        total, status = page.total, page.status
        while len(data) < total:
            offset = len(data)
            request = encode_request(request_id, Op.READ_PAGE, struct.pack("<H", offset))
            page = self._checked_page(request, request_id, Op.READ_PAGE, offset)
            if page.status != Status.OK and page.total == 0:
                self._pending = False
                raise ApiError(page.status, "cached response page unavailable", request_id)
            if page.total != total or page.status != status:
                raise ProtocolError("reply metadata changed between pages")
            data.extend(page.payload)
        try:
            text = bytes(data).decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError("response is not ASCII") from exc
        if any(ord(char) < 0x20 or ord(char) > 0x7E for char in text):
            raise ProtocolError("response contains control characters")
        if status != Status.OK:
            self._pending = False
            raise ApiError(status, text, request_id)
        if not text.startswith("OK api "):
            raise ProtocolError("successful response is not an OK api record")
        self._pending = False
        return text

    def _checked_page(self, request: bytes, request_id: int, op: Op, offset: int) -> Page:
        page = decode_page(self.exchange(request))
        # Header-only errors (including stale READ_PAGE) use offset=total=0.
        empty_error = page.status != Status.OK and page.total == 0 and page.offset == 0
        if page.request_id != request_id or page.op != op or (page.offset != offset and not empty_error):
            raise ProtocolError("response request ID, operation, or offset does not match")
        return page
