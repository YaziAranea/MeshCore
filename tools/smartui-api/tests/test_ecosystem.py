"""Contract simulations; not physical-device acceptance tests."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ecosystem import (DISMISSED, READ, RECEIVED, SNOOZED, BatterySampleState, EventCursor, EventEnd,
                       EventHint, EventKind, HintMailbox, InboxSnapshot,
                       MessageIdentity, RecoveryRequired, SmartUISync,
                       SyncEvent, decode_event_hint)
from smartui_api import (ApiError, MAGIC, Op, ProtocolError, RESPONSE,
                        SmartUIClient, Status, UnsupportedError, encode_request)
from transports import StreamExchange
from test_smartui_api import MockDevice, reply, wire

BOOT = "0123456789abcdef"
OTHER_BOOT = "fedcba9876543210"


def hint_packet(cursor=1, mask=1, boot=BOOT):
    text = f"EV api events boot={boot} cursor={cursor} mask={mask}".encode("ascii")
    return RESPONSE.pack(MAGIC, 1, 0, 3, 0, 0, len(text)) + text


def event(seq, *, boot=BOOT, generation=1, kind=EventKind.READ, state=READ):
    return SyncEvent(boot, seq, generation, int(kind), state, 1, 0, 0)


class SyncDevice(MockDevice):
    """Small deterministic model of the specified command shapes, not firmware."""

    def __init__(self):
        super().__init__()
        self.boot = BOOT
        self.explicit = False
        self.mask = 0
        self.revision = 0
        self.records = {1: [1, 0, 0], 2: [2, 0, 0]}  # flags, state, snooze
        self.queue = [1, 2]
        self.events = []
        self.applied = []
        self.change_item_once = False
        self.always_change_item = False
        for generation in self.records:
            self.emit(generation, 1)

    def emit(self, generation, kind, *, state=0, value=0, key=0):
        self.revision += 1
        self.events.append((self.revision, generation, kind, state, value, key))
        self.events = self.events[-32:]

    def __call__(self, request):
        if (request.startswith(MAGIC) and request[7] == Op.EXEC
                and int.from_bytes(request[5:7], "little") > self.last_id):
            self.command_text = self.command(request[8:].decode("ascii"))
            self.command_status = Status.COMMAND_FAILED if self.command_text.startswith("ERR ") else Status.OK
        return super().__call__(request)

    def status_text(self):
        return (f"OK api sync boot={self.boot} explicit={int(self.explicit)} subscribed={self.mask} "
                f"cursor={self.revision} oldest={self.events[0][0] if self.events else 0} "
                f"revision={self.revision} count={len(self.records)} capacity=32")

    def command(self, command):
        parts = command.split()
        if parts[:2] == ["api", "sync"]:
            if parts[2] in ("enable", "disable"):
                self.explicit = parts[2] == "enable"
                if not self.explicit:
                    self.mask = 0
            return self.status_text()
        if parts[:3] == ["api", "events", "subscribe"]:
            self.mask = int(parts[3])
            return f"OK api events subscribed={self.mask} boot={self.boot} cursor={self.revision}"
        if command == "api inbox snapshot":
            return (f"OK api inbox snapshot boot={self.boot} revision={self.revision} "
                    f"count={len(self.records)} cursor={self.revision} capacity=32")
        if parts[:3] == ["api", "inbox", "item"]:
            if self.change_item_once or self.always_change_item:
                self.change_item_once = False
                self.emit(0, 7)
            if parts[3] != self.boot:
                return f"ERR api boot boot={self.boot}"
            if int(parts[4]) != self.revision:
                return "ERR api changed"
            index = int(parts[5])
            generation = list(self.records)[index]
            flags, state, snooze = self.records[generation]
            return (f"OK api inbox item boot={self.boot} revision={self.revision} index={index} "
                    f"id={generation:08x} flags={flags} state={state} snooze={snooze} snoozable={int(generation == 1)}")
        if command == "api inbox next":
            if not self.explicit:
                return "ERR api negotiate"
            if not self.queue:
                return f"OK api inbox empty=1 boot={self.boot}"
            generation = self.queue[0]
            return (f"OK api inbox next boot={self.boot} id={generation:08x} "
                    f"flags={self.records.get(generation, [0])[0]} frame_hex=0768656c6c6f")
        if parts[:2] == ["api", "inbox"] and parts[2] in ("received", "read", "dismiss", "snooze"):
            if not self.explicit:
                return "ERR api negotiate"
            if parts[3] != self.boot:
                return f"ERR api boot boot={self.boot}"
            action, generation = parts[2], int(parts[4], 16)
            if generation not in self.records:
                if action == "received" and generation in self.queue:
                    self.queue.remove(generation)
                    return f"OK api inbox received id={generation:08x} state=1 changed=1 tracked=0"
                return "ERR api gone"
            if action == "snooze" and generation != 1:
                return "ERR api unsupported"
            record = self.records[generation]
            bit = {"received": RECEIVED, "read": READ, "dismiss": DISMISSED, "snooze": SNOOZED}[action]
            value = int(parts[5]) if action == "snooze" else 0
            changed = not bool(record[1] & bit) or (action == "snooze" and record[2] != value)
            if changed:
                record[1] |= bit
                if action in ("read", "dismiss"):
                    record[1] &= ~SNOOZED
                    record[2] = 0
                if action == "snooze":
                    record[1] &= ~DISMISSED
                    record[2] = value
                if action == "received" and generation in self.queue:
                    self.queue.remove(generation)
                self.applied.append((action, generation, value))
                self.emit(generation, {"received": 2, "read": 3, "dismiss": 4, "snooze": 5}[action],
                          state=record[1], value=value)
            return f"OK api inbox {action} id={generation:08x} state={record[1]} changed={int(changed)}"
        if parts[:3] == ["api", "events", "next"]:
            if parts[3] != self.boot:
                return f"ERR api boot boot={self.boot}"
            cursor = int(parts[4])
            if self.events and cursor < self.events[0][0] - 1:
                return f"ERR api gap boot={self.boot} oldest={self.events[0][0]} cursor={self.revision}"
            pending = [item for item in self.events if item[0] > cursor]
            if not pending:
                return f"OK api events end=1 boot={self.boot} cursor={self.revision}"
            seq, generation, kind, state, value, key = pending[0]
            flags = self.records[generation][0] if generation else 0
            return (f"OK api event boot={self.boot} seq={seq} id={generation:08x} kind={kind} "
                    f"state={state} flags={flags} value={value} key={key}")
        if command == "api notify status":
            return "OK api notify active=0 id=00000000 muted=0"
        return "ERR api invalid"


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.device = SyncDevice()
        self.client = SmartUIClient(self.device)
        self.client.hello()
        self.client.hello_info.update(sync="1", events="1")
        self.sync = SmartUISync(self.client)

    def test_legacy_capability_refusal_sends_no_new_command(self):
        before = len(self.device.requests)
        self.client.hello_info.pop("sync")
        self.client.hello_info["events"] = "0"
        for operation in (self.sync.status, self.sync.enable, self.sync.subscribe):
            with self.assertRaises(UnsupportedError):
                operation()
        self.assertEqual(len(self.device.requests), before)

    def test_peek_does_not_ack_and_received_is_not_read(self):
        self.sync.enable()
        first = self.sync.next_message()
        self.assertEqual(first.frame, b"\x07hello")
        self.assertEqual(self.sync.next_message(), first)
        self.assertEqual(self.device.applied, [])
        received = self.sync.received(first.identity)
        self.assertEqual(received.state, RECEIVED)
        self.assertFalse(received.state & READ)
        self.assertEqual(self.sync.next_message().identity.generation, 2)
        self.assertEqual(self.sync.snapshot().records[0].state, RECEIVED)

    def test_read_does_not_consume_delivery_and_targets_exact_identity(self):
        self.sync.enable()
        first = self.sync.next_message()
        self.sync.read(first.identity)
        self.assertEqual(self.sync.next_message().identity, first.identity)
        self.sync.received(MessageIdentity(BOOT, 2))
        self.assertEqual(self.device.queue, [1])
        self.assertTrue(self.client.last_request.endswith(b"api inbox received 0123456789abcdef 00000002"))

    def test_dismiss_and_snooze_keep_unread_and_never_ack_delivery(self):
        self.sync.enable()
        identity = self.sync.next_message().identity
        self.assertEqual(self.sync.dismiss(identity).state, DISMISSED)
        self.assertEqual(self.sync.snooze(identity, 60).state, SNOOZED)
        self.assertFalse(self.device.records[1][1] & (READ | RECEIVED))
        self.assertEqual(self.device.queue, [1, 2])
        self.assertFalse(self.sync.snooze(identity, 60).changed)
        self.assertEqual(len(self.device.applied), 2)

    def test_action_timeout_replays_same_id_without_repeating_effect(self):
        self.sync.enable()
        identity = self.sync.next_message().identity
        self.device.timeout_once = True
        with self.assertRaises(TimeoutError):
            self.sync.snooze(identity, 60)
        original = self.client.last_request
        self.client.retry_last()
        self.assertEqual(self.device.requests[-1], original)
        self.assertEqual(self.device.applied, [("snooze", 1, 60)])

    def test_reconnect_keeps_message_identity_but_not_session_opt_in(self):
        self.sync.enable()
        identity = self.sync.next_message().identity
        self.sync.snooze(identity, 60)
        self.sync.subscribe(15)
        # A new transport session resets the API replay cache/subscription only.
        self.device.last_id, self.device.original = 0, None
        self.device.explicit, self.device.mask = False, 0
        new_client = SmartUIClient(self.device)
        new_client.hello()
        new_client.hello_info.update(sync="1", events="1")
        resumed = SmartUISync(new_client)
        self.assertFalse(resumed.status().explicit)
        self.assertEqual(resumed.status().subscribed, 0)
        resumed.enable()
        self.assertFalse(resumed.snooze(identity, 60).changed)
        self.assertEqual(resumed.snapshot().records[0].identity, identity)
        self.assertEqual(self.device.applied, [("snooze", 1, 60)])

    def test_subscription_does_not_filter_authoritative_pull_log(self):
        self.sync.subscribe(1)
        self.device.emit(0, 7, key=0, value=99)
        result = self.sync.next_event(BOOT, 2)
        self.assertEqual(result.kind, EventKind.SETTING)
        self.assertIsNone(result.identity)
        self.assertEqual(result.value, 99)
        self.sync.disable()
        self.assertEqual(self.device.mask, 0)

    def test_snapshot_restarts_on_revision_change(self):
        self.device.change_item_once = True
        snapshot = self.sync.snapshot()
        self.assertEqual(snapshot.revision, 3)
        self.assertEqual([record.revision for record in snapshot.records], [3, 3])
        starts = [r for r in self.device.requests if r.endswith(b"api inbox snapshot")]
        self.assertEqual(len(starts), 2)

    def test_snapshot_retry_is_bounded(self):
        self.device.always_change_item = True
        with self.assertRaises(ApiError) as caught:
            self.sync.snapshot(attempts=2)
        self.assertEqual(caught.exception.text, "ERR api changed")
        starts = [r for r in self.device.requests if r.endswith(b"api inbox snapshot")]
        self.assertEqual(len(starts), 2)

    def test_event_gap_invalidates_cursor_then_snapshot_recovers(self):
        cursor = EventCursor(self.sync.snapshot())
        for unused in range(33):
            self.device.emit(0, 7)
        with self.assertRaises(ApiError) as caught:
            cursor.next_event(self.sync)
        self.assertTrue(caught.exception.text.startswith("ERR api gap "))
        self.assertTrue(cursor.needs_snapshot)
        cursor = EventCursor(self.sync.snapshot())
        self.assertIsInstance(cursor.next_event(self.sync), EventEnd)

    def test_local_device_read_event_updates_app_without_echo_command(self):
        cursor = EventCursor(self.sync.snapshot())
        self.device.records[1][1] = READ
        self.device.emit(1, 3, state=READ)
        incoming = cursor.next_event(self.sync)
        self.assertEqual(incoming.identity, MessageIdentity(BOOT, 1))
        self.assertTrue(cursor.check(incoming))
        app_state = {incoming.identity: incoming.state}
        self.assertTrue(cursor.accept(incoming))
        self.assertEqual(app_state[MessageIdentity(BOOT, 1)], READ)
        self.assertEqual(self.device.applied, [])  # No echo `api inbox read`.

    def test_reboot_rejects_old_actions_and_requires_new_baseline(self):
        self.sync.enable()
        old = self.sync.next_message().identity
        cursor = EventCursor(self.sync.snapshot())
        self.device.boot = OTHER_BOOT
        with self.assertRaises(ApiError) as caught:
            self.sync.read(old)
        self.assertTrue(caught.exception.text.startswith("ERR api boot "))
        with self.assertRaises(ApiError):
            cursor.next_event(self.sync)
        self.assertTrue(cursor.needs_snapshot)
        self.assertEqual(self.device.applied, [])

    def test_invalid_arguments_do_not_consume_request_ids(self):
        count = len(self.device.requests)
        identity = MessageIdentity(BOOT, 1)
        for value in (0, -1, 86401, True, 1.5):
            with self.assertRaises(ValueError):
                self.sync.snooze(identity, value)
        for mask in (-1, 16, True):
            with self.assertRaises(ValueError):
                self.sync.subscribe(mask)
        with self.assertRaises(ProtocolError):
            self.sync.next_event("bad", 0)
        self.assertEqual(len(self.device.requests), count)

    def test_missing_message_is_not_retargeted_to_current_head(self):
        self.sync.enable()
        with self.assertRaises(ApiError) as caught:
            self.sync.received(MessageIdentity(BOOT, 99))
        self.assertEqual(caught.exception.text, "ERR api gone")
        self.assertEqual(self.device.queue, [1, 2])

    def test_receipt_of_evicted_record_commits_only_its_retained_frame(self):
        self.sync.enable()
        del self.device.records[2]
        result = self.sync.received(MessageIdentity(BOOT, 2))
        self.assertFalse(result.tracked)
        self.assertTrue(result.changed)
        self.assertEqual(result.state, RECEIVED)
        self.assertEqual(self.device.queue, [1])
        self.assertNotIn(2, self.device.records)

    def test_notification_status_allows_zero_identity_without_inventing_boot(self):
        status = self.sync.notification_status()
        self.assertFalse(status.active)
        self.assertEqual(status.generation, 0)
        self.assertFalse(status.muted)

    def test_snooze_capability_is_per_retained_preview(self):
        self.sync.enable()
        records = self.sync.snapshot().records
        self.assertTrue(records[0].snoozable)
        self.assertFalse(records[1].snoozable)
        with self.assertRaises(ApiError) as caught:
            self.sync.snooze(records[1].identity, 60)
        self.assertEqual(caught.exception.text, "ERR api unsupported")
        self.assertEqual(self.device.applied, [])

    def test_nonhuman_frame_receipt_does_not_create_inbox_record(self):
        self.sync.enable()
        self.device.queue = [99]
        delivery = self.sync.next_message()
        self.assertEqual(delivery.identity.generation, 99)
        self.assertEqual(delivery.flags, 0)
        self.assertFalse(self.sync.received(delivery.identity).tracked)
        self.assertEqual(self.device.queue, [])
        self.assertEqual([r.identity.generation for r in self.sync.snapshot().records], [1, 2])

    def test_readonly_session_can_inspect_but_not_opt_in_or_ack(self):
        self.client.hello_info["write"] = "0"
        self.assertEqual(self.sync.status().boot, BOOT)
        self.sync.subscribe(15)
        self.sync.snapshot()
        count = len(self.device.requests)
        for operation in (self.sync.enable, self.sync.disable,
                          lambda: self.sync.read(MessageIdentity(BOOT, 1))):
            with self.assertRaises(PermissionError):
                operation()
        self.assertEqual(len(self.device.requests), count)

    def test_explicit_opt_in_is_required_and_not_automatic(self):
        with self.assertRaises(ApiError) as caught:
            self.sync.next_message()
        self.assertEqual(caught.exception.text, "ERR api negotiate")
        self.assertFalse(self.device.explicit)

    def test_malformed_hex_and_mismatched_identity_rejected(self):
        self.sync.enable()
        original = self.device.command
        for encoded in ("", "f", "gg", "ff" * 177):
            self.device.command = lambda text, value=encoded: (
                f"OK api inbox next boot={BOOT} id=00000001 flags=1 frame_hex={value}")
            with self.subTest(encoded=encoded), self.assertRaises(ProtocolError):
                self.sync.next_message()
        self.device.command = lambda text: "OK api inbox read id=00000002 state=2 changed=1"
        with self.assertRaises(ProtocolError):
            self.sync.read(MessageIdentity(BOOT, 1))
        self.device.command = original

    def test_unknown_future_event_kind_is_preserved(self):
        self.device.emit(0, 200, key=123, value=456)
        result = self.sync.next_event(BOOT, 2)
        self.assertEqual((result.kind, result.key, result.value), (200, 123, 456))

    def test_battery_unknown_is_explicit_not_a_zero_or_current_reading(self):
        for key in BatterySampleState:
            self.device.emit(0, EventKind.BATTERY, key=key, value=3700)
            incoming = self.sync.next_event(BOOT, self.device.revision - 1)
            self.assertEqual(incoming.kind, EventKind.BATTERY)
            self.assertEqual(incoming.key, key)
            self.assertEqual(incoming.value, 3700)
            self.assertIsNone(incoming.identity)


class CursorTests(unittest.TestCase):
    def cursor(self):
        return EventCursor(InboxSnapshot(BOOT, 2, 2, (), 32))

    def test_duplicates_old_events_and_check_before_apply(self):
        cursor = self.cursor()
        self.assertTrue(cursor.check(event(3)))
        self.assertEqual(cursor.cursor, 2)
        self.assertTrue(cursor.accept(event(3)))
        self.assertFalse(cursor.accept(event(3)))
        self.assertFalse(cursor.accept(event(1)))
        self.assertEqual(cursor.cursor, 3)

    def test_out_of_order_future_event_does_not_silently_skip(self):
        cursor = self.cursor()
        with self.assertRaises(RecoveryRequired):
            cursor.accept(event(4))
        self.assertEqual(cursor.cursor, 2)
        with self.assertRaises(RecoveryRequired):
            cursor.accept(event(3))

    def test_boot_change_and_end_cursor_mismatch(self):
        for incoming in (event(3, boot=OTHER_BOOT), EventEnd(BOOT, 4)):
            cursor = self.cursor()
            with self.subTest(incoming=incoming), self.assertRaises(RecoveryRequired):
                cursor.accept(incoming)
            self.assertTrue(cursor.needs_snapshot)
        self.assertFalse(self.cursor().accept(EventEnd(BOOT, 2)))


class HintTests(unittest.TestCase):
    def test_valid_and_bounded_coalescing_without_cursor_advance(self):
        mailbox = HintMailbox()
        self.assertFalse(mailbox.offer(b"\x80normal push"))
        for seq in range(1, 1000):
            self.assertTrue(mailbox.offer(hint_packet(seq, 1)))
        mailbox.offer(hint_packet(100, 2))
        self.assertEqual(mailbox.take(), EventHint(BOOT, 999, 3))
        self.assertIsNone(mailbox.take())

    def test_hint_header_validation(self):
        valid = hint_packet()
        invalid = [b"", valid + b"x"]
        for position, value in ((4, 2), (5, 1), (7, 2), (8, 1), (9, 1), (11, 0)):
            changed = bytearray(valid)
            changed[position] = value
            invalid.append(bytes(changed))
        for packet in invalid:
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                decode_event_hint(packet)
        with self.assertRaises(ProtocolError):
            decode_event_hint(hint_packet(mask=16))

    def test_hint_is_not_a_reply_and_idle_poll_drains_buffered_hint(self):
        request = encode_request(2, Op.EXEC, b"api get")
        mailbox = HintMailbox()
        seen = []
        def dispatch(packet):
            if not mailbox.offer(packet):
                seen.append(packet)
        stream = wire(hint_packet(3)) + wire(reply(2, 1)) + wire(hint_packet(4))
        transport = StreamExchange(lambda _: None, lambda size, timeout: stream, on_packet=dispatch)
        self.assertEqual(transport.exchange(request), reply(2, 1))
        self.assertEqual(mailbox.take().cursor, 3)
        self.assertEqual(transport.poll(timeout=0), 1)
        self.assertEqual(mailbox.take().cursor, 4)
        self.assertEqual(seen, [])

    def test_poll_fragmentation_packet_budget_and_reentrancy(self):
        chunks = iter([wire(hint_packet(3))[:2], wire(hint_packet(3))[2:] + wire(hint_packet(4))])
        mailbox = HintMailbox()
        transport = None
        def dispatch(packet):
            with self.assertRaises(RuntimeError):
                transport.exchange(b"\x28")
            with self.assertRaises(RuntimeError):
                transport.poll()
            mailbox.offer(packet)
        transport = StreamExchange(lambda _: None, lambda size, timeout: next(chunks), on_packet=dispatch)
        self.assertEqual(transport.poll(), 0)
        self.assertEqual(transport.poll(max_packets=1), 1)
        self.assertEqual(mailbox.take().cursor, 3)
        self.assertEqual(transport.poll(timeout=0), 1)
        self.assertEqual(mailbox.take().cursor, 4)

    def test_poll_timeout_is_not_a_failed_request(self):
        def timeout(size, remaining):
            raise TimeoutError()
        transport = StreamExchange(lambda _: self.fail("poll must not send"), timeout)
        self.assertEqual(transport.poll(), 0)
        for value in (-1, float("nan"), float("inf"), 11):
            with self.assertRaises(ValueError):
                transport.poll(timeout=value)


if __name__ == "__main__":
    unittest.main()
