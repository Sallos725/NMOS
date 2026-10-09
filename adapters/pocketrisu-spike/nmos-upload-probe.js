//@name nmos_upload_probe
//@display-name NMOS upload probe
//@api 3.0
//@version 0.0.1
// Phase 38 step 2: does a request body reach a server whole through risuai.nativeFetch? Each button builds N MB of
// deterministic bytes in the frame, hashes them, POSTs them (binary, a Blob, or base64 in JSON) on one route, and logs
// the sink's length and hash against its own. Not NMOS; a probe for an isolated PocketRisu.
const SINK = 'http://127.0.0.1:8831/sink';
const log = (s) => { console.log('[NMOS-PROBE] ' + s); const d = document.getElementById('out'); if (d) d.textContent += s + '\n'; };
async function hex(buf) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', buf))].map(b => b.toString(16).padStart(2, '0')).join(''); }
function bytes(mb) {
  const out = new Uint8Array(Math.round(mb * 1048576));
  let x = 0x9e3779b9 >>> 0;
  for (let i = 0; i < out.length; i++) { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; out[i] = x & 0xff; }
  return out;
}
function b64(u8) {
  let s = '';
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  return btoa(s);
}
async function send(mb, route, form) {
  const u8 = bytes(mb);
  const want = await hex(u8);
  const body = form === 'binary' ? u8 : form === 'blob' ? new Blob([u8]) : JSON.stringify({ data: b64(u8) });
  const headers = { 'Content-Type': form === 'base64' ? 'application/json' : 'application/octet-stream' };
  const t0 = performance.now();
  let res, text;
  try {
    res = await risuai.nativeFetch(SINK, { method: 'POST', headers, body, requestTimeoutMs: 180000,
      ...(route === 'server' ? { networkRoute: 'local_network' } : {}) });
    text = await res.text();
  } catch (e) {
    log(`send mb=${mb} route=${route} form=${form} threw ${e && e.message || e} after_ms=${Math.round(performance.now() - t0)}`);
    return;
  }
  const ms = Math.round(performance.now() - t0);
  let got = {};
  try { got = JSON.parse(text); } catch { got = { unparsed: text.slice(0, 120) }; }
  log(`send mb=${mb} route=${route} form=${form} status=${res.status} sent=${u8.length} got=${got.bytes} ` +
      `sha=${want.slice(0, 12)} sink=${String(got.sha256).slice(0, 12)} match=${got.sha256 === want} ` +
      `ct=${got.content_type} len=${got.content_length} ms=${ms}${got.unparsed ? ' body=' + got.unparsed : ''}`);
}
const actions = {};
for (const route of ['server', 'direct']) {
  for (const form of ['binary', 'base64']) for (const mb of [1, 4, 30, 64]) actions[`${route}-${form}-${mb}`] = () => send(mb, route, form);
  actions[`${route}-blob-4`] = () => send(4, route, 'blob');
}
actions.info = async () => log(`secure=${window.isSecureContext} origin=${location.origin} ua=${navigator.userAgent.slice(0, 60)}`);
(async () => {
  document.body.innerHTML = '<div style="background:#fff;color:#000;padding:8px">' +
    Object.keys(actions).map(k => `<button id="b-${k}">${k}</button> `).join('') + '<button id="b-close">close</button><pre id="out"></pre></div>';
  for (const [k, f] of Object.entries(actions)) document.getElementById('b-' + k).onclick = () => f().catch(e => log(`${k} error: ${e && e.message || e}`)).finally(() => log(`done ${k}`));
  document.getElementById('b-close').onclick = () => risuai.hideContainer();
  await risuai.registerSetting('NMOS upload probe', () => risuai.showContainer('fullscreen'), '', 'none', 'nmos-upload-probe');
  log('loaded');
})();
