"""Synthetic transports only. Never opens USB, BLE, TCP or a physical node."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smartui_cli import CliClient, CliError, decode_reply, discover, encode_command, matches, record, is_friendly, mutates, EXTENDED_KEYS
from transports import FrameDecoder, StreamTransport

UPSTREAM_WRITES = ("set name Дача", "set pin 654321", "set tx 20", "set af 2.5", "set dutycycle 10",
                   "set rxdelay 1.5", "set multi.acks 2", "set path.hash.mode 1", "set radio.rxgain on",
                   "set tz.offset 5.5", "set radio 869.618,62.5,8,8")
UPSTREAM_READS = ("get freq", "get tx", "get af", "get dutycycle", "get rxdelay", "get multi.acks",
                  "get path.hash.mode", "get radio.rxgain", "get tz.offset", "get wifi.status", "get wifi.ip")
FRIENDLY_READS = ("get volume", "get vibration", "get melody", "get sound_quiet", "get muted", "get board_led",
                  "get unread_led", "get gps", "get battery_protection", "get agc_reset", "get fem.lna",
                  "get fem.pa", "get sound.bridge", "get adc", "get adc.multiplier", "get adc.default",
                  "get battery", "get battery_mv", "get shutdown_mv", "get advert", "caps adc", "get caps fem.lna",
                  "help", "help sound 2", "help adc 3", "help radio 2", "help connection 2", "help system",
                  "help advert", "help led", "help gps", "help fem", "melody 1", "melodies", "adc manual",
                  "adc service", "adc service stop")
FRIENDLY_WRITES = ("set volume 5", "set vibration on", "set vibration off", "set vibration 1", "set vibration 0",
                   "set melody 1", "set sound_quiet 1", "set muted on", "set board_led off", "set unread_led 1",
                   "set gps 0", "set battery_protection on", "set agc_reset 1", "set fem.lna on", "set fem.pa off",
                   "set sound.bridge on", "set adc 4.9", "set adc.multiplier 4.900000", "set advert 120",
                   "test notification", "adc preview 3800", "adc apply 7", "adc reset", "adc service start")

class ExtendedCommands(unittest.TestCase):
    def test_all_extended_keys_are_bounded_and_classified(self):
        for key in EXTENDED_KEYS.split('|'):
            for cmd in ('get '+key, 'set '+key+' 1'):
                self.assertTrue(is_friendly(cmd))
                self.assertTrue(encode_command('AA',cmd).startswith(b'B'))
            self.assertTrue(mutates('set '+key+' 1'))
        for cmd in ('ui name 6162','ui tx set 20','ui reply set 1 6162'):
            self.assertTrue(mutates(cmd))
        self.assertTrue(is_friendly('set vibe_pin -1'))
        with self.assertRaises(CliError):
            encode_command('AA','set tone_pin 2\nreboot')


class Board:
    def __init__(self, readonly=False, discovery="smartui_cli:1", meshcore=None, console=None):
        self.requests, self.closed = [], False
        self.readonly, self.discovery, self.error, self.timeout = readonly, discovery, None, False
        self.meshcore, self.name, self.tx = meshcore, "Тестовая нода", "20"
        self.console = console

    def close(self):
        self.closed = True

    def exchange(self, request, accept):
        if self.closed:
            raise AssertionError("I/O after close")
        self.requests.append(request)
        if self.timeout:
            raise TimeoutError()
        if request[0] == 22:
            reply = bytes([13, 14 if self.meshcore else 13])
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
                    if self.meshcore is not None:
                        text += f" meshcore={self.meshcore}"
                    if self.console is not None:
                        text += f" console={self.console}"
                elif self.console == 1 and is_friendly(command):
                    text = "OK" if mutates(command) else "> 7"
                    if command == "melody 1":
                        text = "> 1: Трель"
                elif self.meshcore == 1 and command in UPSTREAM_READS:
                    text = "> " + (self.tx if command == "get tx" else "1")
                elif self.meshcore == 1 and command.startswith("set "):
                    key, value = command[4:].split(" ", 1)
                    if self.readonly:
                        text = "Error: readonly"
                    else:
                        if key == "name":
                            self.name = value
                        elif key == "tx":
                            self.tx = value
                        text = "> pin is now " + value if key == "pin" else "OK"
                elif command.startswith("ui get "):
                    text = "OK ui get key=" + command[7:] + " value=7"
                elif command == "get name":
                    text = "> " + self.name if self.meshcore == 1 else self.name
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

    def test_friendly_discovery_independent_from_upstream_and_utf8_reply(self):
        client, board = self.connected(console=1)
        self.assertEqual(client.hello["console"], "1")
        for command in FRIENDLY_READS + FRIENDLY_WRITES:
            self.assertRegex(client.execute(command), r"^(?:OK|> )")
        self.assertEqual(client.execute("melody 1"), "> 1: Трель")
        self.assertEqual(client.field("get", "volume"), "7")
        with self.assertRaises(CliError) as error:
            client.execute("get tx")
        self.assertEqual(error.exception.code, "meshcore_unsupported")

    def test_console_discovery_gate_preserves_014_upstream_compatibility(self):
        for marker in (None, 0, 2):
            client, board = self.connected(console=marker, meshcore=1)
            before = len(board.requests)
            for command in FRIENDLY_READS + FRIENDLY_WRITES:
                with self.assertRaises(CliError) as error:
                    client.execute(command)
                self.assertEqual(error.exception.code, "console_unsupported")
            self.assertEqual(len(board.requests), before)
            self.assertFalse(client.uncertain)
            self.assertEqual(client.execute("get tx"), "> 20")
            self.assertEqual(client.field("get", "volume"), "7")

    def test_friendly_readonly_includes_adc_token_creation_but_allows_service_stop(self):
        client, board = self.connected(console=1, readonly=True)
        before = len(board.requests)
        for command in FRIENDLY_WRITES + ("ui adc preview 3800",):
            with self.assertRaises(CliError) as error:
                client.execute(command)
            self.assertEqual(error.exception.code, "readonly")
        self.assertEqual(len(board.requests), before)
        for command in FRIENDLY_READS:
            self.assertTrue(client.execute(command).startswith("> "))
        self.assertFalse(client.uncertain)

    def test_friendly_grammar_remains_bounded(self):
        for command in FRIENDLY_READS + FRIENDLY_WRITES:
            self.assertTrue(encode_command("00", command))
        for command in ("set volume ５", "set vibration yes", "set fem 1", "set adc NaN", "set adc Infinity",
                        "set adc 1e2", "help reboot", "get wifi.password", "get pin", "set battery_mv 4000",
                        "adc service erase", "help sound\nreboot", "melody -1", "get volume extra"):
            with self.subTest(command=command), self.assertRaises(CliError) as error:
                encode_command("00", command)
            self.assertEqual(error.exception.code, "input")

    def test_friendly_error_codes_and_timeout_never_repeat_write(self):
        client, board = self.connected(console=1)
        for reason in ("range", "readonly", "unsupported", "source", "stale", "storage"):
            board.error = "Error: " + reason
            before = len(board.requests)
            with self.assertRaises(CliError) as error:
                client.execute("set volume 5")
            self.assertEqual(error.exception.reason, reason)
            self.assertEqual(len(board.requests), before + 1)
            self.assertFalse(client.uncertain)
        board.timeout = True
        with self.assertRaises(CliError) as error:
            client.execute("set volume 5")
        self.assertEqual(error.exception.code, "timeout")
        before = len(board.requests)
        with self.assertRaises(CliError) as error:
            client.execute("set volume 5")
        self.assertEqual(error.exception.code, "uncertain")
        self.assertEqual(len(board.requests), before)

    def test_protocol_14_extra_hello_and_supported_upstream_read_write(self):
        client, board = self.connected(meshcore=1)
        self.assertEqual(client.hello["meshcore"], "1")
        self.assertEqual(client.field("get", "volume"), "7")
        for command in UPSTREAM_READS:
            self.assertTrue(client.execute(command).startswith("> "))
        for command in UPSTREAM_WRITES:
            self.assertRegex(client.execute(command), r"^(?:OK|> pin is now)")
        self.assertEqual(client.execute("get name"), "> Дача")
        self.assertEqual(client.execute("get tx"), "> 20")

    def test_upstream_capability_gate_and_readonly_every_write(self):
        for capability in (None, 0, 2):
            client, board = self.connected(meshcore=capability)
            before = len(board.requests)
            for command in UPSTREAM_READS + UPSTREAM_WRITES:
                with self.assertRaises(CliError) as error:
                    client.execute(command)
                self.assertEqual(error.exception.code, "meshcore_unsupported")
            self.assertEqual(len(board.requests), before)
            self.assertFalse(client.uncertain)
            self.assertEqual(client.field("get", "volume"), "7")
        client, board = self.connected(meshcore=1, readonly=True)
        before = len(board.requests)
        for command in UPSTREAM_WRITES:
            with self.assertRaises(CliError) as error:
                client.execute(command)
            self.assertEqual(error.exception.code, "readonly")
        self.assertEqual(len(board.requests), before)
        for command in UPSTREAM_READS:
            self.assertTrue(client.execute(command).startswith("> "))

    def test_utf8_names_count_bytes_and_whitelist_stays_bounded(self):
        self.assertEqual(encode_command("ab", "set name Дача")[4:].decode(), "set name Дача")
        exact = "set name " + "я" * 73 + "a"
        self.assertEqual(len(encode_command("ab", exact)), 160)
        for command in (exact + "a", "set name \ud800", "set name X\nreboot", "ui имя", "set tx ２０",
                        "set wifi.pwd secret", "get wifi.pwd", "set unknown 1", "get unknown",
                        "reboot", "poweroff", "shutdown", "erase", "rm /prefs.json"):
            with self.subTest(command=repr(command)), self.assertRaises(CliError) as error:
                encode_command("00", command)
            self.assertEqual(error.exception.code, "input")

    def test_upstream_error_variants_redacted_no_retry_and_lost_ack_uncertain(self):
        client, board = self.connected(meshcore=1)
        for message in ("Error, secret invalid", "ERROR: secret invalid", "Error: secret storage"):
            board.error = message
            before = len(board.requests)
            with self.assertRaises(CliError) as error:
                client.execute("set tx 23")
            self.assertEqual(error.exception.code, "failed")
            self.assertNotIn("secret", str(error.exception))
            self.assertEqual(len(board.requests), before + 1)
            self.assertFalse(client.uncertain)
        board.timeout = True
        with self.assertRaises(CliError) as error:
            client.execute("set tx 20")
        self.assertEqual(error.exception.code, "timeout")
        before = len(board.requests)
        with self.assertRaises(CliError) as error:
            client.execute("get tx")
        self.assertEqual(error.exception.code, "uncertain")
        self.assertEqual(len(board.requests), before)

    def test_terminal_commands_never_sent_or_mistaken_for_success(self):
        client, board = self.connected(meshcore=1)
        before = len(board.requests)
        for command in ("reboot", "poweroff", "shutdown"):
            with self.assertRaises(CliError) as error:
                client.execute(command)
            self.assertEqual(error.exception.code, "input")
        self.assertEqual(len(board.requests), before)
        self.assertFalse(client.uncertain)

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
        for command in ("ui set volume 2", "ui test", "ui sound preview", "ui adc apply 7", "ui adc reset",
                        "ui wifi begin", "ui wifi password 74657374", "ui mode ble",
                        "ui radio set 868731 62500 7 7 2", "ui advert set 120", "ui adc service start",
                        "ui adc set 1.815000"):
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

    def test_adc_manual_probe_readonly_and_explicit_write(self):
        client, board = self.connected(readonly=True)
        board.error = "OK ui adc_manual supported=1"
        self.assertEqual(record(client.execute("ui adc manual"), "OK ui adc_manual"), {"supported": "1"})
        writable, device = self.connected()
        device.error = "OK ui adc_set"
        self.assertEqual(writable.execute("ui adc set 1.815000"), "OK ui adc_set")
        device.error = "OK ui get key=adc_multiplier value=1.815000"
        self.assertEqual(writable.field("get", "adc_multiplier"), "1.815000")

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
