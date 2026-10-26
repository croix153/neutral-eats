#!/usr/bin/env python3
"""Round-4 QA for the Neutral Eats preview (stdlib CDP, Chrome on this host :9224).
Emulates an iPhone (440x956, DSF 3), fakes a Lake Mary geolocation fix, and captures:
  qa_a_list.png   - list at peek after load (vector map + dots)
  qa_b_zoom19.png - street level via the zoom control (pixelation + venue labels)
  qa_c_detail.png - detail open at full (sheet/header clearance)
  qa_d_loc.png    - after Near-me (user location indicator)
"""
import base64, json, time, urllib.request

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
cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True})
cdp.send("Network.setUserAgentOverride",
         {"userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"})
# Fake fix near the default Lake Mary view, BEFORE navigate, so the
# permission-gated autostart path (if it fires) lands on screen.
cdp.send("Emulation.setGeolocationOverride",
         {"latitude": 28.7145, "longitude": -81.3275, "accuracy": 30})
cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
time.sleep(8)

probe = cdp.ev("""(() => ({
  rows: document.querySelectorAll('.venue').length,
  glCanvas: document.querySelectorAll('canvas.maplibregl-canvas').length,
  glLayerEl: !!document.querySelector('.leaflet-gl-layer'),
  rasterTiles: document.querySelectorAll('img.leaflet-tile').length,
  userloc: document.querySelectorAll('.userloc').length,
  zoom: (function(){ var z = document.querySelector('.leaflet-control-zoom-in'); return z ? 'ctrl-ok' : 'no-ctrl'; })()
}))()""")
print("after load:", json.dumps(probe))
cdp.shot("/tmp/qa_a_list.png")

# Zoom to 19 through Leaflet's own control (5 clicks from 14).
for i in range(5):
    cdp.ev("document.querySelector('.leaflet-control-zoom-in').click()")
    time.sleep(0.9)
time.sleep(3)
probe2 = cdp.ev("""(() => ({
  labels: document.querySelectorAll('.venue-label').length,
  rows: document.querySelectorAll('.venue').length,
  glCanvas: document.querySelectorAll('canvas.maplibregl-canvas').length
}))()""")
print("at z19:", json.dumps(probe2))
cdp.shot("/tmp/qa_b_zoom19.png")

# Back out to a normal zoom, then open the first venue's detail.
for i in range(5):
    cdp.ev("document.querySelector('.leaflet-control-zoom-out').click()")
    time.sleep(0.7)
time.sleep(2.5)
cdp.ev("document.querySelector('.venue').click()")
time.sleep(1.5)
diag = cdp.ev("""(() => {
  const r = s => { const el = document.querySelector(s); if (!el) return null;
    const b = el.getBoundingClientRect();
    return { top: Math.round(b.top), bottom: Math.round(b.bottom), height: Math.round(b.height) }; };
  const sh = document.querySelector('#sheet');
  return { innerH: window.innerHeight, sheet: r('#sheet'), header: r('header'),
           back: r('#detailBack'), close: r('#detailClose'),
           sheetInlineH: sh.style.height, sheetInlineTransform: sh.style.transform };
})()""")
print("detail diag:", json.dumps(diag))
cdp.shot("/tmp/qa_c_detail.png")

# Location: if the autostart didn't light the dot, use the Near-me flow.
had_dot = cdp.ev("document.querySelectorAll('.userloc').length")
cdp.ev("document.querySelector('#detailClose').click()")
time.sleep(0.8)
cdp.ev("document.querySelector('#locateBtn').click()")
time.sleep(3)
probe3 = cdp.ev("""(() => ({
  userloc: document.querySelectorAll('.userloc').length,
  userdot: document.querySelectorAll('.userloc-dot').length,
  accuracyPaths: document.querySelectorAll('.leaflet-overlay-pane path').length
}))()""")
print("location: dot-before-nearme =", had_dot, "| after near-me:", json.dumps(probe3))
cdp.shot("/tmp/qa_d_loc.png")
print("QA done")
