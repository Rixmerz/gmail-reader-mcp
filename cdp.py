"""A minimal Chrome DevTools Protocol client over a WebSocket, standard library only.

Only what this server needs: a client WebSocket (RFC 6455, text frames, fragmentation,
ping/pong, close) and request/response matching for CDP commands. Events are handed
to a callback on the reader thread, which may answer them with `send` but must not
wait on `call`.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import threading
import urllib.parse

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA


class CDPError(Exception):
    """The browser refused a command or the connection is gone."""


def mask(payload: bytes, key: bytes) -> bytes:
    n = len(payload)
    if not n:
        return payload
    repeated = (key * (n // 4 + 1))[:n]
    return (int.from_bytes(payload, "big") ^ int.from_bytes(repeated, "big")).to_bytes(n, "big")


def encode_frame(opcode: int, payload: bytes) -> bytes:
    """One final, masked client frame."""
    n = len(payload)
    if n < 126:
        head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
    elif n < 1 << 16:
        head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
    key = os.urandom(4)
    return head + key + mask(payload, key)


class WebSocket:
    def __init__(self, url: str, timeout: float = 30):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + (f"?{u.query}" if u.query else "")
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("the browser closed the connection during the handshake")
            head += chunk
        head, self._buf = head.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        if " 101 " not in lines[0] + " ":
            raise CDPError(f"WebSocket handshake refused: {lines[0]}")
        # SHA-1 is what RFC 6455 prescribes for the handshake check; it protects nothing.
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode(), usedforsecurity=False).digest()).decode()  # NOSONAR
        accept = next((ln.split(":", 1)[1].strip() for ln in lines[1:] if ln.lower().startswith("sec-websocket-accept:")), "")
        if accept != expected:
            raise CDPError("WebSocket handshake answered with a wrong accept key")
        self.sock.settimeout(None)  # the reader thread blocks until the browser speaks
        self._send_lock = threading.Lock()

    def _exact(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self._buf)))
            if not chunk:
                raise CDPError("the browser closed the connection")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _frame(self) -> tuple[bool, int, bytes]:
        b1, b2 = self._exact(2)
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._exact(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._exact(8))[0]
        key = self._exact(4) if b2 & 0x80 else b""
        data = self._exact(n)
        return bool(b1 & 0x80), b1 & 0x0F, mask(data, key) if key else data

    def send_raw(self, opcode: int, payload: bytes) -> None:
        with self._send_lock:
            self.sock.sendall(encode_frame(opcode, payload))

    def send(self, text: str) -> None:
        self.send_raw(OP_TEXT, text.encode("utf-8"))

    def recv(self) -> str:
        """The next whole text message; answers pings on the way."""
        parts: list[bytes] = []
        while True:
            fin, op, data = self._frame()
            if op == OP_PING:
                self.send_raw(OP_PONG, data)
            elif op == OP_CLOSE:
                raise CDPError("the browser closed the connection")
            elif op in (OP_TEXT, OP_BIN, OP_CONT):
                parts.append(data)
                if fin:
                    return b"".join(parts).decode("utf-8")

    def close(self) -> None:
        try:
            self.send_raw(OP_CLOSE, b"")
        except OSError:
            pass
        self.sock.close()


class CDP:
    """Commands with `call`, events through `on_event(cdp, method, params)`."""

    def __init__(self, ws_url: str, on_event=None):
        self.ws = WebSocket(ws_url)
        self.on_event = on_event
        self.alive = True
        self._next = 0
        self._pending: dict[int, list] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        try:
            while True:
                msg = json.loads(self.ws.recv())
                if "id" in msg:
                    slot = self._pending.get(msg["id"])
                    if slot:
                        slot[1] = msg
                        slot[0].set()
                elif self.on_event:
                    self.on_event(self, msg.get("method"), msg.get("params") or {})
        except (CDPError, OSError, ValueError):
            pass
        finally:
            self.alive = False
            for slot in list(self._pending.values()):
                slot[0].set()

    def send(self, method: str, params: dict | None = None) -> int:
        """Fire a command without waiting for its answer (safe from the event callback)."""
        with self._lock:
            self._next += 1
            mid = self._next
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        return mid

    def call(self, method: str, params: dict | None = None, timeout: float = 60) -> dict:
        if not self.alive:
            raise CDPError("the browser connection is closed")
        with self._lock:
            self._next += 1
            mid = self._next
            slot = [threading.Event(), None]
            self._pending[mid] = slot
        try:
            self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            if not slot[0].wait(timeout):
                raise CDPError(f"{method} got no answer within {timeout:.0f} s")
        finally:
            self._pending.pop(mid, None)
        msg = slot[1]
        if msg is None:
            raise CDPError("the browser connection closed")
        if "error" in msg:
            raise CDPError(f"{method}: {msg['error'].get('message')}")
        return msg.get("result") or {}

    def close(self) -> None:
        self.alive = False
        self.ws.close()
