"""Optional SmartUI ecosystem synchronization, discovered independently of version.

No method silently acknowledges delivery, marks a message read, or retries a
mutation. Event hints are advisory; the bounded pull log is authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from smartui_api import (ApiError, MAGIC, MAX_FRAME, ProtocolError, RESPONSE,
                        SmartUIClient, UnsupportedError, VERSION, parse_record)

EVENT_HINT_OP = 3
RECEIVED, READ, DISMISSED, SNOOZED = 1, 2, 4, 8
MESSAGE_EVENTS, SETTING_EVENTS, CONNECTION_EVENTS, BATTERY_EVENTS = 1, 2, 4, 8
ALL_EVENTS = 15
MAX_RECORDS = 32
MAX_SNOOZE_SECONDS = 86400


class EventKind(IntEnum):
    MESSAGE = 1
    RECEIVED = 2
    READ = 3
    DISMISSED = 4
    SNOOZED = 5
    RESUMED = 6
    SETTING = 7
    CONNECTION = 8
    BATTERY = 9
    NOTIFICATION = 10


class BatterySampleState(IntEnum):
    """Informational cached-sample quality/level, not battery shutdown policy."""

    NORMAL = 1
    LOW = 2
    UNKNOWN = 3  # No cached sample or cached sample older than 120000 ms.


def _uint(value: str, name: str, maximum: int = 0xFFFFFFFF) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise ProtocolError(f"invalid unsigned decimal {name}")
    result = int(value)
    if result > maximum:
        raise ProtocolError(f"{name} out of range")
    return result


def _field(fields: dict[str, str], name: str, maximum: int = 0xFFFFFFFF) -> int:
    try:
        return _uint(fields[name], name, maximum)
    except KeyError as exc:
        raise ProtocolError(f"missing {name}") from exc


def _hex(value: str, digits: int, name: str) -> str:
    if len(value) != digits or any(char not in "0123456789abcdef" for char in value):
        raise ProtocolError(f"{name} must be {digits} lowercase hexadecimal digits")
    return value


def _boot(fields: dict[str, str]) -> str:
    try:
        value = _hex(fields["boot"], 16, "boot")
    except KeyError as exc:
        raise ProtocolError("missing boot") from exc
    if int(value, 16) == 0:
        raise ProtocolError("boot must be nonzero")
    return value


def _generation(fields: dict[str, str], *, allow_zero: bool = False) -> int:
    try:
        value = int(_hex(fields["id"], 8, "id"), 16)
    except KeyError as exc:
        raise ProtocolError("missing id") from exc
    if value == 0 and not allow_zero:
        raise ProtocolError("message id must be nonzero")
    return value


def _argument_uint(value: int, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in {minimum}..{maximum}")
    return value


@dataclass(frozen=True)
class MessageIdentity:
    """Stable only within one boot; never use a queue index or request ID."""

    boot: str
    generation: int

    def __post_init__(self):
        _boot({"boot": self.boot})
        _argument_uint(self.generation, "generation", 1, 0xFFFFFFFF)

    @property
    def id_hex(self) -> str:
        return f"{self.generation:08x}"


@dataclass(frozen=True)
class SyncStatus:
    boot: str
    explicit: bool
    subscribed: int
    cursor: int
    oldest: int
    revision: int
    count: int
    capacity: int


@dataclass(frozen=True)
class InboxRecord:
    identity: MessageIdentity
    revision: int
    index: int
    flags: int
    state: int
    snooze_seconds: int
    snoozable: bool = False  # Absent field is not proof of support.


@dataclass(frozen=True)
class InboxSnapshot:
    boot: str
    revision: int
    cursor: int
    records: tuple[InboxRecord, ...]
    capacity: int


@dataclass(frozen=True)
class InboxDelivery:
    identity: MessageIdentity
    flags: int
    frame: bytes  # Exact deframed existing companion message packet.


@dataclass(frozen=True)
class ActionResult:
    identity: MessageIdentity
    action: str
    state: int
    changed: bool
    tracked: bool = True


@dataclass(frozen=True)
class NotificationStatus:
    """Logical notification chain; not a real-time speaker/vibration pin probe."""

    active: bool
    generation: int  # Zero when no message identity is attached.
    muted: bool


@dataclass(frozen=True)
class Subscription:
    boot: str
    mask: int
    cursor: int


@dataclass(frozen=True)
class SyncEvent:
    boot: str
    seq: int
    generation: int  # Zero for non-message events.
    kind: int
    state: int
    flags: int
    value: int
    key: int

    @property
    def identity(self) -> MessageIdentity | None:
        return MessageIdentity(self.boot, self.generation) if self.generation else None


@dataclass(frozen=True)
class EventEnd:
    boot: str
    cursor: int


@dataclass(frozen=True)
class EventHint:
    boot: str
    cursor: int
    mask: int


class RecoveryRequired(RuntimeError):
    """Discard the incomplete baseline and obtain a fresh bounded snapshot."""


def decode_event_hint(packet: bytes) -> EventHint:
    """Decode push op=3, id=0 separately from ordinary request replies."""
    if not RESPONSE.size <= len(packet) <= MAX_FRAME:
        raise ProtocolError("invalid event hint length")
    magic, version, request_id, op, status, offset, total = RESPONSE.unpack_from(packet)
    if (magic != MAGIC or version != VERSION or request_id != 0
            or op != EVENT_HINT_OP or status != 0 or offset != 0
            or total != len(packet) - RESPONSE.size):
        raise ProtocolError("invalid event hint header")
    try:
        text = packet[RESPONSE.size:].decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("event hint is not ASCII") from exc
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in text):
        raise ProtocolError("event hint contains control characters")
    fields = parse_record(text, "EV api events")
    return EventHint(_boot(fields), _field(fields, "cursor"), _field(fields, "mask", ALL_EVENTS))


class HintMailbox:
    """A one-entry, coalescing hint mailbox. Safe to offer from a dispatcher.

    Never call a client method from the push callback. Take the hint afterwards
    and pull events from the last *applied* cursor, not from the hint's cursor.
    """

    def __init__(self):
        self._latest: EventHint | None = None

    def offer(self, packet: bytes) -> bool:
        if len(packet) < 8 or packet[:4] != MAGIC or packet[7] != EVENT_HINT_OP:
            return False
        hint = decode_event_hint(packet)
        previous = self._latest
        if previous is None or previous.boot != hint.boot:
            self._latest = hint
        else:
            self._latest = EventHint(hint.boot, max(previous.cursor, hint.cursor), previous.mask | hint.mask)
        return True

    def take(self) -> EventHint | None:
        hint, self._latest = self._latest, None
        return hint


class EventCursor:
    """Validate a contiguous pull stream; never advance on hints or duplicates.

    Call accept only after successfully applying the event to the app's state.
    Persist that state and cursor atomically if either is persisted at all.
    """

    def __init__(self, snapshot: InboxSnapshot):
        self.boot = snapshot.boot
        self.cursor = snapshot.cursor
        self.needs_snapshot = False

    def invalidate(self):
        self.needs_snapshot = True

    def next_event(self, sync: SmartUISync) -> SyncEvent | EventEnd:
        """Pull without advancing; mark a reported gap/reboot as needing recovery."""
        if self.needs_snapshot:
            raise RecoveryRequired("fresh snapshot required")
        try:
            event = sync.next_event(self.boot, self.cursor)
        except ApiError as exc:
            if exc.text.startswith(("ERR api gap ", "ERR api boot ")):
                self.invalidate()
            raise
        self.check(event)
        return event

    def check(self, event: SyncEvent | EventEnd) -> bool:
        if self.needs_snapshot:
            raise RecoveryRequired("fresh snapshot required")
        if event.boot != self.boot:
            self.invalidate()
            raise RecoveryRequired("device rebooted; discard old message identities")
        if isinstance(event, EventEnd):
            if event.cursor != self.cursor:
                self.invalidate()
                raise RecoveryRequired("end cursor skipped unapplied events")
            return False
        if event.seq <= self.cursor:
            return False  # Duplicate/older delivery, not a new UI action.
        if event.seq != self.cursor + 1:
            self.invalidate()
            raise RecoveryRequired("event sequence gap; obtain a fresh snapshot")
        return True

    def accept(self, event: SyncEvent | EventEnd) -> bool:
        if not self.check(event):
            return False
        self.cursor = event.seq
        return True


class SmartUISync:
    """Optional helpers on the same SmartUIClient and request-ID allocator."""

    def __init__(self, client: SmartUIClient):
        self.client = client

    def _require(self, feature: str):
        if self.client.hello_info is None:
            raise RuntimeError("call hello() on this session first")
        if self.client.hello_info.get(feature) != "1":
            raise UnsupportedError(f"HELLO does not advertise {feature}=1")

    def _execute(self, command: str, feature: str = "sync") -> str:
        self._require(feature)
        return self.client.execute(command)

    def _write_guard(self):
        self._require("sync")
        if self.client.hello_info.get("write") != "1":
            raise PermissionError("session does not permit mutations")

    @staticmethod
    def _status(text: str) -> SyncStatus:
        fields = parse_record(text, "OK api sync")
        capacity = _field(fields, "capacity", MAX_RECORDS)
        count = _field(fields, "count", capacity)
        if not capacity:
            raise ProtocolError("zero inbox capacity")
        return SyncStatus(_boot(fields), bool(_field(fields, "explicit", 1)),
                          _field(fields, "subscribed", ALL_EVENTS), _field(fields, "cursor"),
                          _field(fields, "oldest"), _field(fields, "revision"), count, capacity)

    def status(self) -> SyncStatus:
        return self._status(self._execute("api sync status"))

    def notification_status(self) -> NotificationStatus:
        fields = parse_record(self._execute("api notify status"), "OK api notify")
        return NotificationStatus(bool(_field(fields, "active", 1)),
                                  _generation(fields, allow_zero=True), bool(_field(fields, "muted", 1)))

    def enable(self) -> SyncStatus:
        """Opt this session into explicit delivery/read acknowledgement."""
        self._write_guard()
        return self._status(self._execute("api sync enable"))

    def disable(self) -> SyncStatus:
        """Return this session to legacy behavior and unsubscribe its hints."""
        self._write_guard()
        return self._status(self._execute("api sync disable"))

    def subscribe(self, mask: int = ALL_EVENTS) -> Subscription:
        _argument_uint(mask, "mask", 0, ALL_EVENTS)
        fields = parse_record(self._execute(f"api events subscribe {mask}", "events"), "OK api events")
        actual = _field(fields, "subscribed", ALL_EVENTS)
        if actual != mask:
            raise ProtocolError("subscription mask mismatch")
        return Subscription(_boot(fields), actual, _field(fields, "cursor"))

    def snapshot(self, *, attempts: int = 3) -> InboxSnapshot:
        """Read at most 32 records, retrying only a changed/booted read snapshot.

        Bounded retries prevent starvation during sustained device activity.
        No mutation is retried. ApiError remains visible when retries exhaust.
        """
        _argument_uint(attempts, "attempts", 1, 10)
        for attempt in range(attempts):
            try:
                fields = parse_record(self._execute("api inbox snapshot"), "OK api inbox snapshot")
                boot = _boot(fields)
                revision, cursor = _field(fields, "revision"), _field(fields, "cursor")
                capacity = _field(fields, "capacity", MAX_RECORDS)
                count = _field(fields, "count", capacity)
                if not capacity or cursor != revision:
                    raise ProtocolError("invalid snapshot capacity or cursor")
                records = tuple(self.item(boot, revision, index) for index in range(count))
                if len({record.identity.generation for record in records}) != count:
                    raise ProtocolError("snapshot contains duplicate message identities")
                return InboxSnapshot(boot, revision, cursor, records, capacity)
            except ApiError as exc:
                recoverable = exc.text == "ERR api changed" or exc.text.startswith("ERR api boot ")
                if not recoverable or attempt + 1 == attempts:
                    raise
        raise AssertionError("unreachable")

    def item(self, boot: str, revision: int, index: int) -> InboxRecord:
        _boot({"boot": boot})
        _argument_uint(revision, "revision", 0, 0xFFFFFFFF)
        _argument_uint(index, "index", 0, MAX_RECORDS - 1)
        fields = parse_record(self._execute(f"api inbox item {boot} {revision} {index}"), "OK api inbox item")
        if (_boot(fields) != boot or _field(fields, "revision") != revision
                or _field(fields, "index", MAX_RECORDS - 1) != index):
            raise ProtocolError("snapshot item does not match requested boot, revision and index")
        snoozable = bool(_field(fields, "snoozable", 1)) if "snoozable" in fields else False
        return InboxRecord(MessageIdentity(boot, _generation(fields)), revision, index,
                           _field(fields, "flags", 255), _field(fields, "state", 255),
                           _field(fields, "snooze", MAX_SNOOZE_SECONDS), snoozable)

    def next_message(self) -> InboxDelivery | None:
        """Peek exact companion payload and identity; do NOT consume or mark read."""
        text = self._execute("api inbox next")
        if text.startswith("OK api inbox empty="):
            fields = parse_record(text, "OK api inbox")
            if _field(fields, "empty", 1) != 1:
                raise ProtocolError("invalid empty inbox marker")
            _boot(fields)
            return None
        fields = parse_record(text, "OK api inbox next")
        try:
            encoded = fields["frame_hex"]
            if not encoded or len(encoded) % 2 or len(encoded) > 352:
                raise ValueError("invalid frame hex length")
            if any(char not in "0123456789abcdefABCDEF" for char in encoded):
                raise ValueError("invalid frame hex")
            frame = bytes.fromhex(encoded)
        except (KeyError, ValueError) as exc:
            raise ProtocolError("invalid inbox companion frame") from exc
        return InboxDelivery(MessageIdentity(_boot(fields), _generation(fields)),
                             _field(fields, "flags", 255), frame)

    def _action(self, action: str, identity: MessageIdentity, seconds: int | None = None) -> ActionResult:
        self._write_guard()
        command = f"api inbox {action} {identity.boot} {identity.id_hex}"
        if seconds is not None:
            command += " " + str(_argument_uint(seconds, "seconds", 1, MAX_SNOOZE_SECONDS))
        fields = parse_record(self._execute(command), "OK api inbox " + action)
        if _generation(fields) != identity.generation:
            raise ProtocolError("action reply identity mismatch")
        tracked = bool(_field(fields, "tracked", 1)) if "tracked" in fields else True
        return ActionResult(identity, action, _field(fields, "state", 255), bool(_field(fields, "changed", 1)), tracked)

    def received(self, identity: MessageIdentity) -> ActionResult:
        """Acknowledge app receipt of this exact queue entry, not human reading."""
        return self._action("received", identity)

    def read(self, identity: MessageIdentity) -> ActionResult:
        """Explicit human-read acknowledgement; does not consume the queue entry."""
        return self._action("read", identity)

    def dismiss(self, identity: MessageIdentity) -> ActionResult:
        """Dismiss a notification without claiming the message was read."""
        return self._action("dismiss", identity)

    def snooze(self, identity: MessageIdentity, seconds: int) -> ActionResult:
        """Pause a supported retained preview; inspect item.snoozable first.

        Firmware remains authoritative if the preview changes after inspection.
        Channel/data support must not be inferred from a generic notification.
        """
        return self._action("snooze", identity, seconds)

    def next_event(self, boot: str, cursor: int) -> SyncEvent | EventEnd:
        _boot({"boot": boot})
        _argument_uint(cursor, "cursor", 0, 0xFFFFFFFF)
        text = self._execute(f"api events next {boot} {cursor}", "events")
        if text.startswith("OK api events "):
            fields = parse_record(text, "OK api events")
            if _field(fields, "end", 1) != 1 or _boot(fields) != boot:
                raise ProtocolError("invalid event end marker")
            return EventEnd(boot, _field(fields, "cursor"))
        fields = parse_record(text, "OK api event")
        if _boot(fields) != boot:
            raise ProtocolError("event boot does not match request")
        seq, kind = _field(fields, "seq"), _field(fields, "kind", 255)
        if not seq or not kind:
            raise ProtocolError("event sequence and kind must be nonzero")
        return SyncEvent(boot, seq, _generation(fields, allow_zero=True), kind,
                         _field(fields, "state", 255), _field(fields, "flags", 255),
                         _field(fields, "value"), _field(fields, "key", 65535))
