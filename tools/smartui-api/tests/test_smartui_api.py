import pathlib
import socket
import struct
import sys
import threading
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from smartui_api import (ApiError, MAGIC, MAX_PAGE, Op, PendingRequestError,
                        ProtocolError, REQUEST, RESPONSE, SmartUIClient, Status,
                        UnsupportedError, decode_page, encode_request,
                        melody_name, parse_record)
from transports import FrameDecoder, StreamExchange, frame_to_device


HELLO = ("OK api hello v=1 firmware=0.11 stage=release max_command=152 max_reply=479 "
         "max_frame=160 transport=usb write=1 events=1 sync=1 wifi_setup=1")


def reply(request_id, op, text=b"OK api get", *, offset=0, total=None, status=0):
    if isinstance(text, str):
        text = text.encode("ascii")
    if total is None:
        total = len(text)
    return RESPONSE.pack(MAGIC, 1, request_id, op, status, offset, total) + text


def wire(packet):
    return b">" + len(packet).to_bytes(2, "little") + packet


class MockDevice:
    """Contract simulator, not a replacement for firmware/hardware tests."""

    def __init__(self):
        self.hello_text = HELLO
        self.requests = []
        self.last_id = 0
        self.original = None
        self.data = b""
        self.status = Status.OK
        self.command_status = Status.OK
        self.command_text = "OK api get battery_mv=3800"
        self.writes = 0
        self.advertised = True
        self.timeout_once = False

    def __call__(self, request):
        self.requests.append(request)
        if request == bytes([40]):
            return b"\x15gps_source:HW,smartui_api:1" if self.advertised else b"\x15gps_source:HW"
        _, _, request_id, op = REQUEST.unpack_from(request)
        if op == Op.READ_PAGE:
            offset = int.from_bytes(request[8:], "little")
            if request_id != self.last_id or offset >= len(self.data):
                return reply(request_id, op, b"", status=Status.STALE)
        else:
            offset = 0
            if request_id == self.last_id and request == self.original:
                pass
            elif request_id <= self.last_id:
                return reply(request_id, op, b"", status=Status.STALE)
            else:
                self.last_id, self.original = request_id, request
                self.data = (self.hello_text if op == Op.HELLO else self.command_text).encode("ascii")
                self.status = Status.OK if op == Op.HELLO else self.command_status
                if op == Op.EXEC and request[8:].startswith(b"api set "):
                    self.writes += 1
        result = reply(request_id, op, self.data[offset:offset + MAX_PAGE],
                       offset=offset, total=len(self.data), status=self.status)
        if self.timeout_once:
            self.timeout_once = False
            raise TimeoutError("reply lost after execution")
        return result


class ProtocolTests(unittest.TestCase):
    def test_request_header_and_little_endian(self):
        self.assertEqual(encode_request(0x1234, Op.HELLO), b"\xc9SUI\x01\x34\x12\x00")
        self.assertEqual(encode_request(0x1234, Op.READ_PAGE, b"\xa3\x00")[-2:], b"\xa3\x00")

    def test_request_validation(self):
        for request_id in (0, 65536, -1):
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                encode_request(request_id, Op.HELLO)
        for data in (b"", b"x" * 153, b"api get\n", b"api\0get", b"\xff", b"\x7f"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                encode_request(1, Op.EXEC, data)
        self.assertEqual(len(encode_request(1, Op.EXEC, b"x" * 152)), 160)
        with self.assertRaises(ValueError):
            encode_request(1, Op.HELLO, b"x")
        with self.assertRaises(ValueError):
            encode_request(1, Op.READ_PAGE, b"x")

    def test_response_validation(self):
        bad = [b"", reply(0, 0), reply(1, 3), reply(1, 0, status=8),
               reply(1, 0, b"x" * 148), reply(1, 0, total=481),
               reply(1, 0, b"abc", total=2), reply(1, 0, b"", total=1),
               reply(1, 0, b"", offset=2, total=1),
               b"bad!" + reply(1, 0)[4:]]
        version = bytearray(reply(1, 0)); version[4] = 2
        bad.append(bytes(version))
        for packet in bad:
            with self.subTest(packet=packet), self.assertRaises(ProtocolError):
                decode_page(packet)

    def test_empty_error_reply(self):
        self.assertEqual(decode_page(reply(1, 1, b"", status=5)).status, Status.DENIED)

    def test_record_is_additive(self):
        self.assertEqual(parse_record("OK api caps v=1 future=2", "OK api caps"), {"v": "1", "future": "2"})
        for text in ("ERR api invalid", "OK api caps v=1 v=2", "OK api caps broken", "OK api caps key="):
            with self.subTest(text=text), self.assertRaises(ProtocolError):
                parse_record(text, "OK api caps")

    def test_melody_utf8(self):
        name = "Мелодия"
        self.assertEqual(melody_name("OK api melody id=2 name_hex=" + name.encode().hex()), name)
        for text in ("OK api melody id=1", "OK api melody name_hex=f", "OK api melody name_hex=ff", "OK api melody name_hex=gg"):
            with self.subTest(text=text), self.assertRaises(ProtocolError):
                melody_name(text)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.device = MockDevice()
        self.client = SmartUIClient(self.device)

    def ready(self):
        self.client.hello()

    def test_discovery_precedes_extension(self):
        self.assertEqual(self.client.hello()["v"], "1")
        self.assertEqual(self.device.requests[0], b"\x28")
        self.assertEqual(self.device.requests[1], encode_request(1, Op.HELLO))

    def test_released_011_hello_advertises_ecosystem_without_version_gating(self):
        fields = self.client.hello()
        self.assertEqual(fields["firmware"], "0.11")
        self.assertEqual(fields["stage"], "release")
        self.assertEqual((fields["events"], fields["sync"]), ("1", "1"))

    def test_historical_010_settings_api_remains_compatible(self):
        self.device.hello_text = HELLO.replace("firmware=0.11", "firmware=0.10").replace("events=1 sync=1", "events=0")
        fields = self.client.hello()
        self.assertEqual(fields["firmware"], "0.10")
        self.assertNotIn("sync", fields)
        self.assertEqual(self.client.get()["battery_mv"], "3800")

    def test_stock_fails_without_unknown_opcode(self):
        self.device.advertised = False
        with self.assertRaises(UnsupportedError):
            self.client.hello()
        self.assertEqual(self.device.requests, [b"\x28"])

    def test_no_substring_or_duplicate_discovery(self):
        for response in (b"\x15other:smartui_api:1", b"\x15smartui_api:10", b"\x15smartui_api:1,smartui_api:2"):
            calls = []
            client = SmartUIClient(lambda request: calls.append(request) or response)
            with self.assertRaises(UnsupportedError):
                client.hello()
            self.assertEqual(calls, [b"\x28"])

    def test_malformed_discovery(self):
        with self.assertRaises(ProtocolError):
            SmartUIClient(lambda _: b"\x01").hello()

    def test_requires_hello(self):
        with self.assertRaises(RuntimeError):
            self.client.execute("api get")
        self.assertFalse(self.device.requests)

    def test_monotonic_ids(self):
        self.ready()
        self.client.execute("api get")
        self.client.execute("api get")
        ids = [int.from_bytes(r[5:7], "little") for r in self.device.requests if r.startswith(MAGIC)]
        self.assertEqual(ids, [1, 2, 3])

    def test_pagination_to_maximum_total(self):
        self.ready()
        self.device.command_text = "OK api get value=" + "a" * (479 - len("OK api get value="))
        self.assertEqual(self.client.execute("api get"), self.device.command_text)
        pages = [r for r in self.device.requests if r.startswith(MAGIC) and r[7] == 2]
        self.assertEqual([int.from_bytes(r[8:], "little") for r in pages], [147, 294, 441])
        self.assertTrue(all(int.from_bytes(r[5:7], "little") == 2 for r in pages))

    def test_timeout_replay_does_not_repeat_write(self):
        self.ready()
        self.device.command_text = "OK api set key=volume value=5"
        self.device.timeout_once = True
        with self.assertRaises(TimeoutError):
            self.client.execute("api set volume 5")
        original = self.client.last_request
        self.assertTrue(self.client.pending)
        with self.assertRaises(PendingRequestError):
            self.client.execute("api get")
        with self.assertRaises(PendingRequestError):
            self.client.discover()
        self.assertEqual(self.client.retry_last(), self.device.command_text)
        self.assertEqual(self.device.requests[-1], original)
        self.assertEqual(self.device.writes, 1)
        self.assertFalse(self.client.pending)

    def test_hello_timeout_can_be_retried(self):
        self.device.timeout_once = True
        with self.assertRaises(TimeoutError):
            self.client.hello()
        self.client.retry_last()
        self.assertEqual(self.client.hello_info["transport"], "usb")

    def test_page_timeout_restarts_cached_response(self):
        self.ready()
        self.device.command_text = "OK api get value=" + "a" * 350
        exchange = self.device
        fail = [True]
        def lossy(request):
            response = exchange(request)
            if request[7] == 2 and fail[0]:
                fail[0] = False
                raise TimeoutError()
            return response
        self.client.exchange = lossy
        with self.assertRaises(TimeoutError):
            self.client.execute("api get")
        self.assertEqual(self.client.retry_last(), self.device.command_text)

    def test_status_errors_are_explicit(self):
        self.ready()
        for status in list(Status)[1:]:
            self.device.command_status = status
            self.device.command_text = "ERR api readonly"
            with self.subTest(status=status), self.assertRaises(ApiError) as caught:
                self.client.execute("api get")
            self.assertEqual(caught.exception.status, status)
            self.assertFalse(self.client.pending)

    def test_mismatched_reply_keeps_pending(self):
        self.ready()
        self.client.exchange = lambda _: reply(99, 1)
        with self.assertRaises(ProtocolError):
            self.client.execute("api get")
        self.assertTrue(self.client.pending)

    def test_changed_page_metadata_rejected(self):
        self.ready()
        self.device.command_text = "OK api get value=" + "a" * 300
        def exchange(request):
            data = bytearray(self.device(request))
            if request[7] == 2:
                struct.pack_into("<H", data, 11, 400)
            return bytes(data)
        self.client.exchange = exchange
        with self.assertRaises(ProtocolError):
            self.client.execute("api get")

    def test_page_cache_loss_preserves_numeric_error(self):
        self.ready()
        self.device.command_text = "OK api get value=" + "a" * 300
        def exchange(request):
            if request[7] == 2:
                return reply(int.from_bytes(request[5:7], "little"), 2, b"", status=6)
            return self.device(request)
        self.client.exchange = exchange
        with self.assertRaises(ApiError) as caught:
            self.client.execute("api get")
        self.assertEqual(caught.exception.status, Status.STALE)
        self.assertFalse(self.client.pending)

    def test_invalid_success_text_is_not_silently_accepted(self):
        self.ready()
        self.client.exchange = lambda r: reply(int.from_bytes(r[5:7], "little"), 1, b"ERR api invalid")
        with self.assertRaises(ProtocolError):
            self.client.execute("api get")
        self.assertTrue(self.client.pending)

    def test_no_id_wrap(self):
        client = SmartUIClient(self.device, first_id=65535)
        client.hello()
        with self.assertRaises(RuntimeError):
            client.execute("api get")
        self.assertEqual(self.device.last_id, 65535)

    def test_invalid_command_does_not_consume_id(self):
        self.ready()
        for command in ("reboot", "api get\n", "api привет", "api " + "x" * 149):
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.client.execute(command)
        self.client.execute("api get")
        self.assertEqual(self.device.last_id, 2)

    def test_replay_without_request_rejected(self):
        with self.assertRaises(RuntimeError):
            self.client.retry_last()

    def test_wifi_wrappers_encode_and_do_not_auto_commit(self):
        self.ready()
        self.device.command_text = "OK api wifi state=ssid"
        self.client.wifi_begin()
        self.client.wifi_ssid("Network")
        self.assertEqual(self.client.last_request[8:], b"api wifi ssid 4e6574776f726b")
        self.client.wifi_password("testpass")
        self.assertEqual(self.client.last_request[8:], b"api wifi password 7465737470617373")
        self.client.wifi_password("")
        self.assertEqual(self.client.last_request[8:], b"api wifi password -")
        self.client.wifi_test()
        self.assertFalse(any(r.endswith(b"api wifi save") for r in self.device.requests))
        self.client.wifi_save()
        self.assertTrue(self.client.last_request.endswith(b"api wifi save"))

    def test_wifi_secrets_validate_without_exposing_values(self):
        self.ready()
        for secret in ("short", "x" * 65, "x" * 64, "validpass\n", "valid\0pass"):
            with self.subTest(length=len(secret)), self.assertRaises(ValueError) as caught:
                self.client.wifi_password(secret)
            self.assertNotIn(secret, str(caught.exception))
        for ssid in ("", "x" * 33, "bad\nname"):
            with self.assertRaises(ValueError):
                self.client.wifi_ssid(ssid)

    def test_tcp_writes_allowed_but_provisioning_keeps_session(self):
        self.ready()
        self.client._hello_record(HELLO.replace("transport=usb", "transport=wifi"))
        self.device.command_text = "OK api set key=volume value=5"
        self.assertEqual(self.client.execute("api set volume 5"), self.device.command_text)
        with self.assertRaises(PermissionError):
            self.client.wifi_begin()

    def test_mode_validates_before_sending(self):
        self.ready()
        self.device.command_text = "OK api mode target=ble state=pending"
        with self.assertRaises(ValueError):
            self.client.set_mode("other")
        self.assertEqual(self.client.set_mode("ble"), self.device.command_text)
        self.client.hello_info["write"] = "0"
        with self.assertRaises(PermissionError):
            self.client.set_mode("usb")


class FramingTests(unittest.TestCase):
    def test_tcp_every_fragment_boundary(self):
        packets = [b"\x80push", b"\x15smartui_api:1", b"a" * 176]
        stream = b"".join(map(wire, packets))
        for position in range(len(stream) + 1):
            with self.subTest(position=position):
                decoder = FrameDecoder()
                self.assertEqual(decoder.feed(stream[:position]) + decoder.feed(stream[position:]), packets)

    def test_tcp_bytewise(self):
        decoder = FrameDecoder()
        decoded = []
        for value in wire(b"example"):
            decoded.extend(decoder.feed(bytes([value])))
        self.assertEqual(decoded, [b"example"])

    def test_invalid_frames_and_text_rejected(self):
        for data in (b"OK console\n", b">\0\0", b">\xb1\0", b">\xff\xff"):
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                FrameDecoder().feed(data)

    def test_host_envelope(self):
        self.assertEqual(frame_to_device(b"\x28"), b"<\x01\0\x28")
        for data in (b"", b"x" * 177):
            with self.assertRaises(ValueError):
                frame_to_device(data)

    def test_push_dispatch_and_coalesced_frames(self):
        pushed, sent = [], []
        chunks = iter([wire(b"\x80push") + wire(b"\x15smartui_api:1") + wire(b"\x81more"), wire(b"\x0d\x03")])
        transport = StreamExchange(sent.append, lambda n, t: next(chunks), on_packet=pushed.append)
        self.assertEqual(transport.exchange(b"\x28"), b"\x15smartui_api:1")
        transport.begin_companion_session()
        self.assertEqual(pushed, [b"\x80push", b"\x81more"])
        self.assertEqual(sent, [b"<\x01\0\x28", b"<\x02\0\x16\x03"])

    def test_delayed_duplicate_page_dispatched(self):
        request = encode_request(2, Op.READ_PAGE, struct.pack("<H", 147))
        packets = wire(reply(2, 2, b"x", offset=0, total=148)) + wire(reply(2, 2, b"x", offset=147, total=148))
        pushed = []
        transport = StreamExchange(lambda _: None, lambda n, t: packets, on_packet=pushed.append)
        self.assertEqual(decode_page(transport.exchange(request)).offset, 147)
        self.assertEqual(len(pushed), 1)

    def test_page_error_zero_offset_is_matched(self):
        request = encode_request(2, Op.READ_PAGE, struct.pack("<H", 147))
        error = reply(2, 2, b"", status=6)
        transport = StreamExchange(lambda _: None, lambda n, t: wire(error))
        self.assertEqual(transport.exchange(request), error)

    def test_reentrant_exchange_rejected(self):
        transport = None
        def callback(packet):
            with self.assertRaises(RuntimeError):
                transport.exchange(b"\x28")
        transport = StreamExchange(lambda _: None, lambda n, t: wire(b"\x80push") + wire(b"\x15x:y"), on_packet=callback)
        self.assertEqual(transport.exchange(b"\x28"), b"\x15x:y")

    def test_socket_fragmented_roundtrip(self):
        left, right = socket.socketpair()
        received, failures = [], []
        def device():
            try:
                right.settimeout(2)
                data = b""
                while len(data) < 4:
                    data += right.recv(4 - len(data))
                received.append(data)
                for byte in wire(b"\x80push") + wire(b"\x15smartui_api:1"):
                    right.sendall(bytes([byte]))
            except Exception as exc:
                failures.append(exc)
            finally:
                right.close()
        thread = threading.Thread(target=device, daemon=True)
        thread.start()
        def read(size, remaining):
            left.settimeout(remaining)
            data = left.recv(size)
            if not data:
                raise ConnectionError("EOF")
            return data
        try:
            transport = StreamExchange(left.sendall, read, timeout=2)
            self.assertEqual(transport.exchange(b"\x28"), b"\x15smartui_api:1")
            self.assertEqual(list(transport.unsolicited), [b"\x80push"])
        finally:
            left.close()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(received, [b"<\x01\0\x28"])


if __name__ == "__main__":
    unittest.main()
