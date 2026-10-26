#!/usr/bin/env python3
"""Diagnose what's actually painted under the detail view (stdlib CDP client)."""
import base64, json, time
import importlib.util
spec = importlib.util.spec_from_file_location("repro", "/tmp/repro_detail.py")

# Reuse the WS/CDP classes without running main(): exec only the top part.
src = open("/tmp/repro_detail.py").read()
head = src.split("def main()")[0]
ns = {}
exec(head, ns)
WS, CDP = ns["WS"], ns["CDP"]
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:9224/json/list", timeout=10) as r:
    targets = json.load(r)
page = next(t for t in targets if t["type"] == "page")
cdp = CDP(WS(page["webSocketDebuggerUrl"]))
cdp.send("Page.enable")
cdp.send("Emulation.setDeviceMetricsOverride",
         {"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": True})
cdp.send("Network.setUserAgentOverride",
         {"userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"})
cdp.send("Page.navigate", {"url": "https://neutraleats.com/preview.html"})
time.sleep(6)
cdp.ev("document.querySelector('.venue').click()")
time.sleep(1.2)
info = cdp.ev("""(() => {
  const sheets = document.querySelectorAll('#sheet').length;
  const el = document.elementFromPoint(200, 700);
  const chain = [];
  let n = el;
  while (n && chain.length < 6) {
    const cs = getComputedStyle(n);
    chain.push({ tag: n.tagName, id: n.id, cls: n.className && String(n.className).slice(0,30),
                 bg: cs.backgroundColor, opacity: cs.opacity });
    n = n.parentElement;
  }
  const sheet = document.querySelector('#sheet');
  const parent = sheet.parentElement;
  return { sheets, atPoint: chain,
           detailParent: document.querySelector('#detail').parentElement.id,
           sheetParent: parent.id || parent.tagName,
           panelVar: getComputedStyle(document.documentElement).getPropertyValue('--panel'),
           sheetOpacity: getComputedStyle(sheet).opacity };
})()""")
print(json.dumps(info, indent=1))
cdp.ev("document.querySelector('#sheet').style.background = 'rgb(255,0,0)'")
time.sleep(0.4)
cdp.shot("/tmp/ne_red.png")
cdp.ev("document.querySelector('#sheet').style.display = 'none'")
time.sleep(0.4)
cdp.shot("/tmp/ne_nosheet.png")
