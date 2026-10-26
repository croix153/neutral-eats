#!/usr/bin/env python3
"""Diagnose geolocation behavior in the rig: what does watchPosition do,
and when does the .userloc marker appear/disappear after Near-me?"""
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

print("perm state:", cdp.ev("navigator.permissions.query({name:'geolocation'}).then(s=>s.state)"))
# Raw watch listener of our own, logging into window.__geoLog
cdp.ev("""(() => {
  window.__geoLog = [];
  navigator.geolocation.watchPosition(
    p => window.__geoLog.push('ok ' + p.coords.latitude.toFixed(5)),
    e => window.__geoLog.push('err code=' + e.code + ' ' + e.message),
    { enableHighAccuracy: true, maximumAge: 30000 });
  return 'watch registered';
})()""")
time.sleep(2)
print("raw watch log after 2s:", cdp.ev("JSON.stringify(window.__geoLog)"))

cdp.ev("document.querySelector('#locateBtn').click()")
for i in range(16):
    time.sleep(0.5)
    n = cdp.ev("document.querySelectorAll('.userloc').length")
    print(f"t+{(i+1)*0.5:.1f}s after Near-me: .userloc = {n}")
print("raw watch log final:", cdp.ev("JSON.stringify(window.__geoLog)"))
print("perm state final:", cdp.ev("navigator.permissions.query({name:'geolocation'}).then(s=>s.state)"))
