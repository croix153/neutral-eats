// Reproduce the preview's detail-view layout at iPhone size via CDP (Chrome on croix.ai, port 9224).
const BASE = 'http://127.0.0.1:9224';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function main() {
  const ts = await (await fetch(BASE + '/json/list')).json();
  const page = ts.find(t => t.type === 'page');
  if (!page) throw new Error('no page target');
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const mid = ++id;
    const onMsg = ev => {
      const m = JSON.parse(ev.data);
      if (m.id === mid) {
        ws.removeEventListener('message', onMsg);
        if (m.error) reject(new Error(method + ': ' + JSON.stringify(m.error)));
        else resolve(m.result);
      }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id: mid, method, params }));
  });
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    if (r.exceptionDetails) throw new Error('eval: ' + JSON.stringify(r.exceptionDetails).slice(0, 400));
    return r.result.value;
  };
  const shot = async path => {
    const s = await send('Page.captureScreenshot', { format: 'png' });
    require('fs').writeFileSync(path, Buffer.from(s.data, 'base64'));
    console.log('shot ->', path);
  };

  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 3, mobile: true });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true });
  await send('Network.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' });
  await send('Page.navigate', { url: 'https://neutraleats.com/preview.html' });
  await sleep(5000);
  console.log('rows:', await ev(`document.querySelectorAll('.venue').length`));
  await shot('/tmp/ne_list.png');

  await ev(`document.querySelector('.venue').click()`);
  await sleep(1500);
  await shot('/tmp/ne_detail.png');
  const diag = await ev(`(() => {
    const r = s => { const el = document.querySelector(s); if (!el) return null;
      const b = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      return { top: Math.round(b.top), bottom: Math.round(b.bottom), height: Math.round(b.height),
               transform: cs.transform, bg: cs.backgroundColor, display: cs.display, z: cs.zIndex }; };
    return { innerH: window.innerHeight, sheet: r('#sheet'), detail: r('#detail'),
             listView: r('#listView'), back: r('#detailBack'), header: r('header'), chips: r('#chips') };
  })()`);
  console.log(JSON.stringify(diag, null, 1));
  ws.close();
}
main().catch(e => { console.error('FAIL', e.message); process.exit(1); });
