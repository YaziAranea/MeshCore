"""Local SmartUI CLI66 client. One queue owner; no retry, inbox or events."""
import re
import threading

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
READ_COMMANDS = {"board", "ver", "get name", "get radio"}
MESHCORE_READ_COMMANDS = {"get freq", "get tx", "get af", "get dutycycle", "get rxdelay",
                         "get multi.acks", "get path.hash.mode", "get radio.rxgain",
                         "get tz.offset", "get wifi.status", "get wifi.ip"}
DECIMAL = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
MESHCORE_SET = re.compile(
    r"set (?:name .+|(?:pin|tx|multi\.acks|path\.hash\.mode) [-+]?\d+|"
    r"(?:af|dutycycle|rxdelay|tz\.offset) " + DECIMAL +
    r"|radio\.rxgain (?:on|off)|radio " + DECIMAL + "," + DECIMAL + r",[-+]?\d+,[-+]?\d+)",
    re.ASCII)
FRIENDLY_READ = re.compile(
    r"(?:get (?:volume|vibration|melody|sound_quiet|muted|board_led|unread_led|gps|"
    r"battery_protection|agc_reset|fem\.lna|fem\.pa|sound\.bridge|adc(?:\.multiplier|\.default)?|"
    r"battery|battery_mv|shutdown_mv|advert)|(?:get )?caps [a-z][a-z_.]*|"
    r"help(?: (?:sound|fem|adc|radio|connection|system|advert|led|gps)(?: [1-9]\d*)?)?|"
    r"melody \d+|melodies|adc (?:manual|service(?: stop)?))", re.ASCII)
FRIENDLY_WRITE = re.compile(
    r"(?:set (?:(?:volume|melody|advert) \d+|(?:vibration|sound_quiet|muted|board_led|unread_led|"
    r"gps|battery_protection|agc_reset|fem\.lna|fem\.pa|sound\.bridge) (?:on|off|0|1)|"
    r"adc(?:\.multiplier)? (?:\d+(?:\.\d*)?|\.\d+))|test notification|"
    r"adc (?:preview \d+|apply \d+|reset|service start))", re.ASCII)
EXTENDED_KEYS = ("notify_mode|important_notify_mode|led_pin|tone_pin|vibe_pin|melody_dm|"
                 "melody_mention|melody_system|tone_8bit|high_drive|resonance_hz|offline_dm_led|"
                 "ble_dm_led|msg_popup|ui_font|ui_theme|ui_top_color|ui_bottom_color|"
                 "backlight_timeout|gps_source|gps_interval|advert_location|profile")
EXTENDED_COMMAND = re.compile(r"(?:get (?:" + EXTENDED_KEYS + r")|set (?:" + EXTENDED_KEYS +
                              r") (?:-?\d+|on|off)|schema [a-z][a-z0-9_.]*|help (?:display|pins|profile|replies)(?: [1-9]\d*)?)", re.ASCII)


def is_friendly(command):
    return bool(FRIENDLY_READ.fullmatch(command) or FRIENDLY_WRITE.fullmatch(command) or EXTENDED_COMMAND.fullmatch(command))


ERROR_TEXT = {
    "input": "Invalid local command.",
    "unsupported": "smartui_cli:1 not discovered; use archived Helper 1.4 for 0.11.",
    "meshcore_unsupported": "meshcore=1 not discovered in ui hello; use supported ui commands.",
    "console_unsupported": "console=1 not discovered in ui hello; short commands require SmartUI 0.15.",
    "busy": "Another command is pending.",
    "closed": "Transport is closed.",
    "timeout": "No reply; result unknown. Reconnect and read state, do not retry writes.",
    "protocol": "Invalid reply; reconnect before continuing.",
    "uncertain": "Previous result unknown; reconnect and read state.",
    "readonly": "Firmware permits reading only.",
    "exhausted": "Request tags exhausted; reconnect.",
    "failed": "Command rejected; raw response is not logged.",
}


class CliError(Exception):
    def __init__(self, code, reason=None):
        self.code, self.reason = code, reason
        super().__init__(ERROR_TEXT.get(code, ERROR_TEXT["failed"]))


def encode_command(tag, command):
    if not isinstance(command, str) or len(command) < 2 or re.search(r"[\x00-\x1f\x7f]", command):
        raise CliError("input")
    try:
        encoded = command.encode("utf-8")
    except UnicodeError:
        raise CliError("input") from None
    if len(encoded) > 156:
        raise CliError("input")
    if command.startswith("set name "):
        if not MESHCORE_SET.fullmatch(command):
            raise CliError("input")
    elif not command.isascii() or not (command.startswith("ui ") or command in READ_COMMANDS or
                                        command in MESHCORE_READ_COMMANDS or MESHCORE_SET.fullmatch(command) or
                                        is_friendly(command)):
        raise CliError("input")
    if not re.fullmatch(r"[0-9A-Za-z]{2}", tag):
        raise CliError("input")
    return b"\x42" + tag.encode("ascii") + b"|" + encoded


def decode_reply(packet, tag, ascii_only=True):
    if not 5 <= len(packet) <= 160 or packet[:4] != b"\x1d" + tag.encode() + b"|":
        raise CliError("protocol")
    try:
        text = packet[4:].decode("utf-8")
    except UnicodeError:
        raise CliError("protocol") from None
    if re.search(r"[\x00-\x1f\x7f]", text) or (ascii_only and not text.isascii()):
        raise CliError("protocol")
    if text == "Unknown command":
        raise CliError("failed", "unsupported")
    error = re.fullmatch(r"(?:ERR ui |Error: )([a-z_]+)", text)
    if error:
        reason = error[1]
        raise CliError("readonly" if reason == "readonly" else "failed", reason)
    if re.match(r"(?:Error[:,]|ERROR:)", text):
        raise CliError("failed")
    if ascii_only and not text.startswith("OK ui "):
        raise CliError("protocol")
    return text


def record(text, prefix):
    if not isinstance(text, str) or len(text) > 156 or not re.fullmatch(r"[ -~]*", text):
        raise CliError("protocol")
    if text != prefix and not text.startswith(prefix + " "):
        raise CliError("protocol")
    result = {}
    for token in text[len(prefix):].strip().split():
        match = re.fullmatch(r"([a-z][a-z0-9_]*)=([^ \x00-\x1f\x7f]+)", token)
        if not match or match[1] in result:
            raise CliError("protocol")
        result[match[1]] = match[2]
    return result


def discover(packet):
    if not packet or packet[0] != 21:
        raise CliError("unsupported")
    try:
        parts = packet[1:].decode("ascii").rstrip("\0").split(",")
    except UnicodeError:
        raise CliError("unsupported") from None
    if [p for p in parts if p.startswith("smartui_cli:")] != ["smartui_cli:1"]:
        raise CliError("unsupported")


def matches(request, reply):
    if not reply:
        return False
    if reply[0] == 1:  # Standard companion error, including invalid envelope [1,6].
        return True
    if request[0] == 22:
        return reply[0] == 13
    if request[0] == 40:
        return reply[0] == 21
    return len(reply) >= 4 and reply[:4] == b"\x1d" + request[1:4]


def mutates(command):
    return command.startswith("set ") or bool(FRIENDLY_WRITE.fullmatch(command) or re.match(r"ui (set |name |reply set |tx set |test$|(?:radio|advert) set |adc (preview |set |apply |reset$|service start$)|wifi (?!status$)|mode (?!status$))", command))


class CliClient:
    """exchange(request, accept) must enforce a deadline and return one payload.

    The transport owns exactly one reader. accept ignores standard pushes and
    mismatched request prefixes. A timeout makes this instance unusable until
    close and a genuinely new transport/session; writes are never retried.
    """
    def __init__(self, exchange, close=None):
        self.exchange, self._close = exchange, close
        self.hello = None
        self.uncertain = False
        self.closed = False
        self._tag = 0
        self._lock = threading.Lock()

    def _exchange(self, request):
        try:
            reply = bytes(self.exchange(request, lambda p: matches(request, p)))
        except TimeoutError:
            self.uncertain = True
            raise CliError("timeout") from None
        except CliError:
            self.uncertain = True
            raise
        except Exception:
            self.uncertain = True
            raise CliError("closed") from None
        if not matches(request, reply):
            self.uncertain = True
            raise CliError("protocol")
        if reply[0] == 1:
            raise CliError("failed")
        return reply

    def _command(self, command):
        if self._tag >= 3844:
            raise CliError("exhausted")
        tag = ALPHABET[self._tag // 62] + ALPHABET[self._tag % 62]
        request = encode_command(tag, command)
        self._tag += 1
        return decode_reply(self._exchange(request), tag, command.startswith("ui "))

    def connect(self):
        if not self._lock.acquire(blocking=False):
            raise CliError("busy")
        try:
            if self.closed or self.hello or self.uncertain:
                raise CliError("closed" if self.closed else "uncertain")
            info = self._exchange(bytes([22, 3]))  # DeviceInfo may contain PIN: discard.
            if len(info) < 2 or info[0] != 13:
                raise CliError("protocol")
            discover(self._exchange(bytes([40])))
            hello = record(self._command("ui hello"), "OK ui hello")
            expected = {"version": "1", "max_command": "156", "max_reply": "156",
                        "sync": "0", "events": "0"}
            if any(hello.get(k) != v for k, v in expected.items()) or hello.get("write") not in {"0", "1"}:
                raise CliError("protocol")
            self.hello = hello
            return dict(hello)
        except Exception:
            self.close()
            raise
        finally:
            self._lock.release()

    def execute(self, command):
        if not self._lock.acquire(blocking=False):
            raise CliError("busy")
        try:
            if self.closed or self.hello is None:
                raise CliError("closed")
            if self.uncertain:
                raise CliError("uncertain")
            encode_command("00", command)  # Validate before capability/permission checks; no I/O.
            friendly = is_friendly(command)
            if friendly and self.hello.get("console") != "1":
                raise CliError("console_unsupported")
            if not command.startswith("ui ") and command not in READ_COMMANDS and not friendly and self.hello.get("meshcore") != "1":
                raise CliError("meshcore_unsupported")
            if mutates(command) and self.hello["write"] != "1":
                raise CliError("readonly")
            return self._command(command)
        except CliError as error:
            if error.code in {"protocol", "timeout", "closed", "exhausted"}:
                self.uncertain = True
            raise
        finally:
            self._lock.release()

    def field(self, kind, key):
        if kind not in {"caps", "get"} or not re.fullmatch(r"[a-z][a-z_]*", key):
            raise CliError("input")
        values = record(self.execute(f"ui {kind} {key}"), f"OK ui {kind}")
        if values.get("key") != key or not re.fullmatch(r"-?\d+(?:\.\d+)?", values.get("value", "")):
            self.uncertain = True
            raise CliError("protocol")
        return values["value"]

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.hello = None
        if self._close:
            self._close()
