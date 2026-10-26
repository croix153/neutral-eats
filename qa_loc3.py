#!/usr/bin/env python3
"""Verify the location indicator through the page's REAL code: stub only the
platform geolocation/permissions APIs before page scripts run (the rig
Chrome's native override never delivers a fix), let the page's own
permission-gated autostart create the dot, then push a moved fix through
the page's watchPosition registration."""
import json, time, urllib.request

src = open("/tmp/repro_detail.py").read()
ns = {}
exec(src.split("def main()")[0], ns)
WS, CDP = ns["WS"], ns["CDP"]

STUB = r"""
(() => {
  var fix = { coords: { latitude: 28.7145, longitude: -81.3275, accuracy: 80,
                        altitude: null, altitudeAccuracy: null, heading: null, speed: null },
              timestamp: Date.now() };
  var watchers = {};
  var nextId = 1;
  var fakeGeo = {
    getCurrentPosition: function(ok, err, opts){ setTimeout(function(){ ok(fix); }, 60); },
    watchPosition: function(ok, err, opts){
      var id = nextId++; watchers[id] = ok;
      setTimeout(function(){ ok(fix); }, 60);
      return id;
    },
    clearWatch: function(id){ delete watchers[id]; }
  };
  Object.defineProperty(navigator, 'geolocation', { value: fakeGeo, configurable: true });
  window.__geoPush = function(lat, lng, acc){
    fix = { coords: { latitude: lat, longitude: lng, accuracy: acc,
                      altitude: null, altitudeAccuracy: null, heading: null, speed: null },
            timestamp: Date.now() };
    Object.keys(watchers).forEach(function(id){ watchers[id](fix); });
  };
  if (navigator.permissions && navigator.permissions.query) {
    var origQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(d){
      if (d && d.name === 'geolocation') return Promise.resolve({ state: 'granted' });
      return origQuery(d);
    };
  }
})();
"""

with urllib.request.urlopen("http://127.0.0.1:9224/json/list", timeout=10) as r:
    targets = json.load(r)
page = next(t for t in targets if t["type"] == "page")
cdp = CDP(WS(page["webSocketDebuggerUrl"]))
cdp.send("Page.enable")
cdp.send("Emulation.setDeviceMetricsOverride",
         {"width": 440, "height": 956, "deviceScaleFactor": 3, "mobile": True})
cdp.send("Network.setUserAgentOverride",
         {"userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"})
cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": STUB})
cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
time.sleep(7)
probe = cdp.ev("""(() => ({
  userloc: document.querySelectorAll('.userloc').length,
  dot: document.querySelectorAll('.userloc-dot').length,
  halo: document.querySelectorAll('.userloc-halo').length,
  overlayPaths: document.querySelectorAll('.leaflet-overlay-pane path').length
}))()""")
print("autostart probe:", json.dumps(probe))
# Collapse the sheet so the map (and dot) is fully visible, then shoot.
cdp.ev("document.querySelector('#sheetHandle').click()")
time.sleep(1.2)
cdp.shot("/tmp/qa_d2_loc.png")
# Push a moved fix (~350m east) through the page's own watch registration.
cdp.ev("window.__geoPush(28.7148, -81.3235, 45)")
time.sleep(1.2)
cdp.shot("/tmp/qa_d3_loc_moved.png")
print("done")
