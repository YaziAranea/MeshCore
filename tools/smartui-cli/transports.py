"""Explicit USB/TCP stream adapters; no device search or background readers."""
import socket
import time
from smartui_cli import CliError


class FrameDecoder:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            if self.buffer[0] != 62:
                raise CliError("protocol")  # USB companion, not text console.
            if len(self.buffer) < 3:
                break
            length = int.from_bytes(self.buffer[1:3], "little")
            if not 1 <= length <= 176:
                raise CliError("protocol")
            if len(self.buffer) < length + 3:
                break
            frames.append(bytes(self.buffer[3:3 + length]))
            del self.buffer[:3 + length]
        return frames


class StreamTransport:
    def __init__(self, read, write, close, timeout=6.0):
        self.read, self.write, self._close = read, write, close
        self.timeout, self.closed = timeout, False
        self.decoder = FrameDecoder()

    def exchange(self, request, accept):
        if self.closed:
            raise CliError("closed")
        if not 1 <= len(request) <= 160:
            raise CliError("input")
        self.write(b"<" + len(request).to_bytes(2, "little") + request)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            raw = self.read(max(0.001, deadline - time.monotonic()))
            if raw is None:  # Timeout/no bytes; a closed TCP stream raises instead.
                continue
            for frame in self.decoder.feed(raw):
                if accept(frame):
                    return frame
        raise TimeoutError()

    def close(self):
        if not self.closed:
            self.closed = True
            self._close()


def tcp(host, port=5000, timeout=6.0):
    """Trusted LAN only: existing firmware TCP has no authentication or TLS."""
    sock = socket.create_connection((host, port), timeout=timeout)

    def read(remaining):
        sock.settimeout(remaining)
        try:
            data = sock.recv(4096)
        except socket.timeout:
            return None
        if not data:
            raise CliError("closed")
        return data

    return StreamTransport(read, sock.sendall, sock.close, timeout)


def usb(port, timeout=6.0):
    """Requires optional pyserial; open only the explicitly supplied port."""
    import serial
    connection = serial.Serial(port=port, baudrate=115200, timeout=0.1,
                               write_timeout=timeout, rtscts=False, dsrdtr=False)

    def read(remaining):
        connection.timeout = min(0.1, remaining)
        return connection.read(max(1, connection.in_waiting)) or None

    def write(data):
        if connection.write(data) != len(data):
            raise CliError("closed")

    return StreamTransport(read, write, connection.close, timeout)
