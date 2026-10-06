"""Optional synchronous USB/TCP adapters for SmartUI 0.10.

TCP uses only the stdlib. USB imports pyserial only when explicitly opened.
No adapter retries, reconnects, scans networks, or changes device settings.
"""

from __future__ import annotations

import socket
import time
from collections import deque
from typing import Callable

from smartui_api import MAGIC, ProtocolError

COMPANION_MAX_FRAME = 176  # Existing protocol, including non-API pushes.


def frame_to_device(packet: bytes) -> bytes:
    if not 1 <= len(packet) <= COMPANION_MAX_FRAME:
        raise ValueError("companion packet length must be in 1..176")
    return b"<" + len(packet).to_bytes(2, "little") + packet


class FrameDecoder:
    """Incremental device-to-host '>' + uint16-LE + payload decoder.

    Arbitrary fragmentation and multiple coalesced frames are supported. Fail
    closed on text, invalid markers and oversized lengths: do not reinterpret
    a mixed text/binary console as authenticated protocol traffic.
    """

    def __init__(self):
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._buffer.extend(chunk)
        frames = []
        while self._buffer:
            if self._buffer[0] != ord(">"):
                raise ProtocolError("unexpected stream data; raw console text cannot be mixed with frames")
            if len(self._buffer) < 3:
                break
            length = int.from_bytes(self._buffer[1:3], "little")
            if not 1 <= length <= COMPANION_MAX_FRAME:
                raise ProtocolError("invalid companion stream frame length")
            if len(self._buffer) < 3 + length:
                break
            frames.append(bytes(self._buffer[3:3 + length]))
            del self._buffer[:3 + length]
        return frames


def response_matches(request: bytes, packet: bytes) -> bool:
    if request.startswith(MAGIC):
        # Include pagination offset to ignore delayed duplicate pages after a
        # timeout. Detailed version/length/status checks remain in the core.
        offset = request[8:10] if request[7] == 2 else b"\0\0"
        empty_error = (len(packet) == 13 and packet[8] != 0
                       and packet[9:13] == b"\0\0\0\0")
        return (len(packet) >= 13 and packet[:4] == MAGIC
                and packet[5:8] == request[5:8]
                and (packet[9:11] == offset or empty_error))
    if request == bytes([40]):
        return bool(packet) and packet[0] in (1, 21)  # ERR or custom vars.
    if request and request[0] == 22:
        return bool(packet) and packet[0] in (1, 13)  # ERR or device info.
    raise ValueError("adapter supports DEVICE_QUERY, discovery and SmartUI packets only")


class StreamExchange:
    """Serializes one request/reply while dispatching other companion frames.

    read(max_bytes, remaining_seconds) must return bytes within that deadline.
    Empty reads are permitted for serial poll timeouts; TCP EOF must raise.
    send_all must be bounded and send the entire supplied buffer or raise.
    With no callback, up to 64 unrelated packets are retained in unsolicited.
    Integrators sharing a session with an app should use that app's dispatcher
    instead of opening a second transport or competing for its read stream.
    """

    def __init__(self, send_all: Callable[[bytes], None],
                 read: Callable[[int, float], bytes], *, timeout: float = 10.0,
                 on_packet: Callable[[bytes], None] | None = None):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.send_all = send_all
        self.read = read
        self.timeout = timeout
        self.on_packet = on_packet
        self.unsolicited: deque[bytes] = deque(maxlen=64)
        self._frames: deque[bytes] = deque()
        self.decoder = FrameDecoder()
        self._active = False

    def _dispatch(self, packet: bytes):
        if self.on_packet is not None:
            self.on_packet(packet)
        else:
            if len(self.unsolicited) == self.unsolicited.maxlen:
                raise ProtocolError("unsolicited queue full; install a companion push dispatcher")
            self.unsolicited.append(packet)

    def exchange(self, packet: bytes) -> bytes:
        if self._active:
            raise RuntimeError("concurrent or reentrant exchange is not supported")
        encoded = frame_to_device(packet)
        self._active = True
        try:
            # Frames already buffered before this request are not its reply.
            while self._frames:
                self._dispatch(self._frames.popleft())
            self.send_all(encoded)
            deadline = time.monotonic() + self.timeout
            while True:
                while self._frames:
                    incoming = self._frames.popleft()
                    if response_matches(packet, incoming):
                        return incoming
                    self._dispatch(incoming)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("companion response deadline expired; request outcome may be unknown")
                self._frames.extend(self.decoder.feed(self.read(4096, remaining)))
        finally:
            self._active = False

    def begin_companion_session(self) -> None:
        """Read-only standard handshake on a *new* session; never print its reply.

        DEVICE_INFO contains an existing BLE PIN field, so return no raw data.
        Do not call this on another application's session without coordination.
        """
        reply = self.exchange(bytes([22, 3]))
        if len(reply) < 2 or reply[0] != 13:
            raise ProtocolError("standard companion DEVICE_QUERY failed")


class TcpTransport(StreamExchange):
    def __init__(self, host: str, port: int, *, timeout: float = 35.0,
                 on_packet: Callable[[bytes], None] | None = None):
        # No authentication or TLS is added to the existing TCP listener here.
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.socket = socket.create_connection((host, port), timeout=timeout)
        super().__init__(self._send, self._read, timeout=timeout, on_packet=on_packet)

    def _send(self, data: bytes):
        self.socket.settimeout(self.timeout)
        self.socket.sendall(data)

    def _read(self, size: int, remaining: float) -> bytes:
        self.socket.settimeout(remaining)
        data = self.socket.recv(size)
        if not data:
            raise ConnectionError("TCP session closed; replay cache no longer guaranteed")
        return data

    def close(self):
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class UsbTransport(StreamExchange):
    def __init__(self, port: str, *, baudrate: int = 115200, timeout: float = 10.0,
                 on_packet: Callable[[bytes], None] | None = None):
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("USB adapter requires optional pyserial; core and TCP do not") from exc
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=0.1, write_timeout=timeout)
        super().__init__(self._send, self._read, timeout=timeout, on_packet=on_packet)

    def _send(self, data: bytes):
        if self.serial.write(data) != len(data):
            raise OSError("partial USB write; request outcome may be unknown")

    def _read(self, size: int, remaining: float) -> bytes:
        self.serial.timeout = min(remaining, 0.1)
        return self.serial.read(min(size, max(1, self.serial.in_waiting)))

    def close(self):
        self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
