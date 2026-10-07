"""Synthetic transports only. Never opens USB, BLE, TCP or a physical node."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smartui_cli import CliClient, CliError, decode_reply, discover, encode_command, matches, record
from transports import FrameDecoder, StreamTransport


class Board:
    def __init__(self, readonly=False, discovery="smartui_cli:1"):
        self.requests, self.closed = [], False
        self.readonly, self.discovery, self.error, self.timeout = readonly, discovery, None, False

    def close(self):
        self.closed = True

    def exchange(self, request, accept):
        if self.closed:
            raise AssertionError("I/O after close")
        self.requests.append(request)
        if self.timeout:
            raise TimeoutError()
        if request[0] == 22:
            reply = bytes([13, 13])
        elif request[0] == 40:
            reply = b"\x15" + self.discovery.encode()
        else:
            command = request[4:].decode()
            text = self.error
            self.error = None
            if text is None:
                if command == "ui hello":
                    text = ("OK ui hello version=1 firmware=0.12 max_command=156 max_reply=156 "
                            f"write={int(not self.readonly)} sync=0 events=0")
                elif command.startswith("ui get "):
                    text = "OK ui get key=" + command[7:] + " value=7"
                elif command == "get name":
                    text = "Тестовая нода"
                elif command == "ui test":
                    text = "OK ui test"
                else:
                    text = "Unknown command"
            reply = b"\x1d" + request[1:4] + text.encode()
        assert accept(reply)
        return reply


class CliTests(unittest.TestCase):
    def connected(self, **kwargs):
        board = Board(**kwargs)
        client = CliClient(board.exchange, board.close)
        client.connect()
        self.addCleanup(client.close)
        return client, board

    def test_exact_encoding_and_max_length(self):
        self.assertEqual(encode_command("a9", "ui get volume"), b"Ba9|ui get volume")
        self.assertEqual(len(encode_command("00", "ui " + "x" * 153)), 160)
        for command in ("ui " + "x" * 154, "api hello", "reboot", "ui \n", "ui имя"):
            with self.subTest(command=command), self.assertRaises(CliError):
                encode_command("00", command)

    def test_discovery_strict_and_old_api_not_accepted(self):
        discover(b"\x15foo:0,smartui_cli:1")
        for value in ("smartui_api:1", "smartui_cli:2", "smartui_cli:1,smartui_cli:1"):
            board = Board(discovery=value)
            client = CliClient(board.exchange, board.close)
            with self.assertRaises(CliError) as e:
                client.connect()
            self.assertEqual(e.exception.code, "unsupported")
            self.assertEqual([p[0] for p in board.requests], [22, 40])
            self.assertTrue(board.closed)

    def test_single_fields_and_no_message_drain(self):
        client, board = self.connected()
        self.assertEqual(client.field("get", "volume"), "7")
        self.assertTrue(all(p[0] in {22, 40, 66} for p in board.requests))
        self.assertEqual(client.execute("ui test"), "OK ui test")

    def test_standard_utf8_and_ui_ascii(self):
        client, _ = self.connected()
        self.assertEqual(client.execute("get name"), "Тестовая нода")
        with self.assertRaises(CliError):
            decode_reply(b"\x1dab|" + "Имя".encode(), "ab")

    def test_domain_errors_not_retried_or_poisoned(self):
        client, board = self.connected()
        for reason in ("unsupported", "invalid", "storage", "source", "stale", "range", "busy", "usb_required"):
            before = len(board.requests)
            board.error = "ERR ui " + reason
            with self.assertRaises(CliError) as e:
                client.field("get", "volume")
            self.assertEqual(e.exception.reason, reason)
            self.assertEqual(len(board.requests), before + 1)
            self.assertFalse(client.uncertain)
        self.assertEqual(client.field("get", "volume"), "7")

    def test_error_text_is_redacted_and_unknown_is_supported_failure(self):
        client, board = self.connected()
        for message in ("Error: secret must not appear", "Unknown command"):
            board.error = message
            with self.assertRaises(CliError) as e:
                client.execute("ui get volume")
            self.assertEqual(e.exception.code, "failed")
            self.assertNotIn("secret", str(e.exception))
            self.assertFalse(client.uncertain)

    def test_readonly_infers_writes(self):
        client, board = self.connected(readonly=True)
        for command in ("ui set volume 2", "ui test", "ui adc apply 7", "ui adc reset",
                        "ui wifi begin", "ui wifi password 74657374", "ui mode ble",
                        "ui radio set 868731 62500 7 7 2", "ui advert set 120", "ui adc service start"):
            before = len(board.requests)
            with self.assertRaises(CliError) as e:
                client.execute(command)
            self.assertEqual(e.exception.code, "readonly")
            self.assertEqual(len(board.requests), before)
        self.assertEqual(client.field("get", "volume"), "7")

    def test_adc_service_read_stop_are_allowed_readonly(self):
        client, board = self.connected(readonly=True)
        reply = "OK ui adc_service supported=1 active=0 remaining_ms=0 external=1"
        for command in ("ui adc service", "ui adc service stop"):
            board.error = reply
            self.assertEqual(client.execute(command), reply)
        board.error = "OK ui caps key=adc_service value=1"
        self.assertEqual(client.field("caps", "adc_service"), "1")

    def test_timeout_poison_and_no_after_close_io(self):
        client, board = self.connected()
        board.timeout = True
        with self.assertRaises(CliError) as e:
            client.execute("ui set volume 2")
        self.assertEqual(e.exception.code, "timeout")
        count = len(board.requests)
        with self.assertRaises(CliError) as e:
            client.execute("ui get volume")
        self.assertEqual(e.exception.code, "uncertain")
        client.close()
        with self.assertRaises(CliError):
            client.execute("ui get volume")
        self.assertEqual(len(board.requests), count)

    def test_no_tag_reuse(self):
        client, board = self.connected()
        for _ in range(3843):
            client.execute("ui test")
        self.assertEqual(len({p[1:3] for p in board.requests if p[0] == 66}), 3844)
        with self.assertRaises(CliError) as e:
            client.execute("ui test")
        self.assertEqual(e.exception.code, "exhausted")
        self.assertTrue(client.uncertain)

    def test_busy_has_no_competing_write(self):
        client, board = self.connected()
        self.assertTrue(client._lock.acquire())
        before = len(board.requests)
        try:
            with self.assertRaises(CliError) as e:
                client.execute("ui test")
            self.assertEqual(e.exception.code, "busy")
            self.assertEqual(len(board.requests), before)
        finally:
            client._lock.release()

    def test_wrong_tag_oversize_invalid_utf8_duplicate_fields(self):
        for reply in (b"\x1dzz|OK ui test", b"\x1d00|" + b"x" * 157, b"\x1d00|\xff",
                      b"\x1d00|OK ui test\n"):
            with self.assertRaises(CliError):
                decode_reply(reply, "00")
        with self.assertRaises(CliError):
            record("OK ui get key=x key=y", "OK ui get")
        with self.assertRaises(CliError):
            record("OK ui get key=x\tvalue=7", "OK ui get")
        request = encode_command("00", "ui test")
        self.assertFalse(matches(request, b"\x1d01|OK ui test"))
        self.assertFalse(matches(request, b"\x83"))
        self.assertTrue(matches(request, b"\x01\x06"))

    def test_stream_fragmented_push_wrong_tag_then_exact(self):
        packet = lambda body: b">" + len(body).to_bytes(2, "little") + body
        data = packet(b"\x83") + packet(b"\x1dZZ|OK ui test") + packet(b"\x1d00|OK ui test")
        chunks = [data[i:i + 2] for i in range(0, len(data), 2)]
        writes = []
        stream = StreamTransport(lambda remaining: chunks.pop(0), writes.append, lambda: None)
        request = encode_command("00", "ui test")
        self.assertEqual(stream.exchange(request, lambda p: matches(request, p)), b"\x1d00|OK ui test")
        self.assertEqual(writes, [b"<" + len(request).to_bytes(2, "little") + request])
        stream.close()
        with self.assertRaises(CliError):
            stream.exchange(request, lambda p: True)
        self.assertEqual(len(writes), 1)

    def test_stream_invalid_frame_and_timeout(self):
        for raw in (b"help\n", b">\xb1\0"):
            with self.assertRaises(CliError):
                FrameDecoder().feed(raw)
        writes = []
        stream = StreamTransport(lambda remaining: None, writes.append, lambda: None, timeout=0.001)
        with self.assertRaises(TimeoutError):
            stream.exchange(b"B00|ui test", lambda p: True)
        self.assertEqual(len(writes), 1)

    def test_field_wrong_key_poison(self):
        client, board = self.connected()
        board.error = "OK ui get key=muted value=0"
        with self.assertRaises(CliError):
            client.field("get", "volume")
        self.assertTrue(client.uncertain)


if __name__ == "__main__":
    unittest.main()
