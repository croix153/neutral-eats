#!/usr/bin/env python3
"""Timeline probe: click Near-me, poll .userloc + first-row distance + toast."""
import json, time, urllib.request

src = open("/tmp/repro_detail.py").read()
ns = {}
exec(src.split("def main()")[0], ns)
WS, CDP = ns["WS"], ns["CDP"]

with urllib.request.urlopen("http://127.0.0.1:9224/json/list", timeout=10) as r:
    targets = json.load(r)
page = next(t for t in targets if t["type"] == "page")
cdp = CDP(WS(page["webSocketDebuggerUrl"]))
cdp.send("Page.enable")
cdp.send("Emulation.setDeviceMetricsOverride",
         {"width": 440, "height": 956, "deviceScaleFactor": 3, "mobile": True})
cdp.send("Network.setUserAgentOverride",
         {"userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"})
cdp.send("Emulation.setGeolocationOverride",
         {"latitude": 28.7145, "longitude": -81.3275, "accuracy": 30})
cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
time.sleep(7)
print("rows at load:", cdp.ev("document.querySelectorAll('.venue').length"),
      "| first dist:", cdp.ev("(document.querySelector('.venue .dist')||{}).textContent"))
cdp.ev("document.querySelector('#locateBtn').click()")
for i in range(24):
    time.sleep(0.5)
    out = cdp.ev("""(() => ({
      dot: document.querySelectorAll('.userloc').length,
      dist: (document.querySelector('.venue .dist')||{}).textContent || '',
      toast: (document.querySelector('#toast')||{}).textContent || ''
    }))()""")
    print(f"t+{(i+1)*0.5:4.1f}s dot={out['dot']} dist={out['dist']!r} toast={out['toast']!r}")
    if out['dot']:
        break
