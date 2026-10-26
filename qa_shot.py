#!/usr/bin/env python3
"""Reproduce the preview's detail-view layout at iPhone size via CDP.
Stdlib-only minimal WebSocket client (Chrome on this host, port 9224)."""
import base64, json, os, socket, struct, sys, time, urllib.request
from urllib.parse import urlparse

BASE = "http://127.0.0.1:9224"

class WS:
    def __init__(self, url):
        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        path = u.path + ("?" + u.query if u.query else "")
        req = (f"GET {path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("handshake closed")
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b"101" not in head.split(b"\r\n")[0]:
            raise RuntimeError("handshake failed: " + head.decode(errors="replace")[:200])
        self.buf = rest

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("socket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode()
        mask = os.urandom(4)
        ln = len(data)
        if ln < 126:
            hdr = bytes([0x81, 0x80 | ln])
        elif ln < 65536:
            hdr = bytes([0x81, 0xFE]) + struct.pack(">H", ln)
        else:
            hdr = bytes([0x81, 0xFF]) + struct.pack(">Q", ln)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    def recv_msg(self):
        payload = b""
        while True:
            b1, b2 = self._read(2)
            fin = b1 & 0x80; op = b1 & 0x0F
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            if b2 & 0x80:
                self._read(4)
            data = self._read(ln) if ln else b""
            if op == 9:      # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if op in (0, 1, 2):
                payload += data
                if fin:
                    return payload.decode()

class CDP:
    def __init__(self, ws):
        self.ws = ws; self.mid = 0
    def send(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            m = json.loads(self.ws.recv_msg())
            if m.get("id") == self.mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m["result"]
    def ev(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        if "exceptionDetails" in r:
            raise RuntimeError("eval: " + json.dumps(r["exceptionDetails"])[:400])
        return r["result"].get("value")
    def shot(self, path):
        s = self.send("Page.captureScreenshot", {"format": "png"})
        open(path, "wb").write(base64.b64decode(s["data"]))
        print("shot ->", path)

def main():
    req = urllib.request.Request(BASE + "/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        target = json.load(r)
    cdp = CDP(WS(target["webSocketDebuggerUrl"]))
    cdp.send("Page.enable")
    cdp.send("Emulation.setDeviceMetricsOverride",
             {"width": 1440, "height": 900, "deviceScaleFactor": 2, "mobile": False})
    cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
    time.sleep(7)
    print("rows:", cdp.ev("document.querySelectorAll('.venue').length"))
    print("wordmark font:", cdp.ev("getComputedStyle(document.querySelector('.brand h1')).fontFamily"))
    cdp.ev("var l=document.querySelector('#list'); if(l) l.scrollTop=320; 'ok'")
    time.sleep(0.6)
    cdp.shot("/tmp/ne-desktop.png")
    cdp.send("Page.navigate", {"url": "file:///tmp/favicon-candidates/preview.html"})
    time.sleep(1.5)
    cdp.shot("/tmp/ne-favicons.png")

main()
