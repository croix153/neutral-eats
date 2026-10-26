#!/usr/bin/env python3
"""Cold-load check: does the live preview center on the user on open?

Geolocation is overridden to downtown Orlando (28.5425,-81.3790) —
deliberately ~15 mi from the Lake Mary home fallback (28.713,-81.326)
so a centered load is unmistakable: the userloc marker must exist and
the sheet must list downtown-Orlando venues at small distances.
Run ON the croix.ai host against the test Chrome (CDP 9224).
"""
import json, time, urllib.request

src = open("/root/repro_detail.py").read()
ns = {}
exec(src.split("def main()")[0], ns)
WS, CDP = ns["WS"], ns["CDP"]

# Grant geolocation to the origin at browser level first.
with urllib.request.urlopen("http://127.0.0.1:9224/json/version", timeout=10) as r:
    version = json.load(r)
bws = WS(version["webSocketDebuggerUrl"])
import itertools
_bid = itertools.count(1000)
def bsend(method, params=None):
    i = next(_bid)
    bws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(bws.recv_msg())
        if msg.get("id") == i:
            return msg
bsend("Browser.grantPermissions", {
    "origin": "https://neutraleats.com",
    "permissions": ["geolocation"],
})

with urllib.request.urlopen("http://127.0.0.1:9224/json/list", timeout=10) as r:
    targets = json.load(r)
page = next(t for t in targets if t["type"] == "page")
cdp = CDP(WS(page["webSocketDebuggerUrl"]))
cdp.send("Page.enable")
cdp.send("Runtime.enable")
cdp.send("Emulation.setGeolocationOverride",
         {"latitude": 28.5425, "longitude": -81.3790, "accuracy": 30})
cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
time.sleep(10)

_r = cdp.send("Runtime.evaluate", {
    "expression": "navigator.permissions.query({name:'geolocation'}).then(s=>s.state)",
    "awaitPromise": True, "returnByValue": True})
print("perm state:", _r["result"].get("value"))
print("userloc markers:", cdp.ev("document.querySelectorAll('.userloc').length"))
sheet = cdp.ev("(document.querySelector('#sheet')||{innerText:''}).innerText.slice(0,600)")
print("sheet text:", json.dumps(sheet))
