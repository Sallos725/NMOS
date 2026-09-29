//@name nmos_probe
//@display-name NMOS download probe
//@api 3.0
//@version 0.0.1
const B = 'http://127.0.0.1:8830/bytes';
const log = (s) => { console.log('[NMOS-PROBE] ' + s); const d = document.getElementById('out'); if (d) d.textContent += s + '\n'; };
async function hex(buf) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256', buf))].map(b => b.toString(16).padStart(2, '0')).join(''); }
function save(blob, name) {
  const u = URL.createObjectURL(blob); const a = document.createElement('a');
  a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 60000);
}
async function fetched(mb, route) {
  const t0 = performance.now();
  const res = await risuai.nativeFetch(`${B}?mb=${mb}`, { method: 'GET', headers: {}, requestTimeoutMs: 120000,
    ...(route === 'server' ? { networkRoute: 'local_network' } : {}) });
  const t1 = performance.now();
  const buf = await res.arrayBuffer();
  const t2 = performance.now();
  const h = await hex(buf);
  const want = res.headers && res.headers.get ? res.headers.get('x-sha256') : null;
  log(`fetch mb=${mb} route=${route} status=${res.status} type=${typeof res} ctor=${res.constructor && res.constructor.name} bytes=${buf.byteLength} sha=${h.slice(0, 12)} header=${String(want).slice(0, 12)} match=${h === want} headers_ms=${Math.round(t1 - t0)} body_ms=${Math.round(t2 - t1)}`);
  return new Blob([buf], { type: 'application/zip' });
}
const actions = {
  small: async () => { save(new Blob(['hello nmos'], { type: 'text/plain' }), 'small.txt'); log('small clicked'); },
  delayed: async () => { await new Promise(r => setTimeout(r, 8000)); save(new Blob(['late'], { type: 'text/plain' }), 'delayed.txt'); log('delayed clicked'); },
  server1: async () => save(await fetched(1, 'server'), 'server1.nmos.zip'),
  server30: async () => save(await fetched(30, 'server'), 'server30.nmos.zip'),
  direct1: async () => save(await fetched(1, 'direct'), 'direct1.nmos.zip'),
  direct30: async () => save(await fetched(30, 'direct'), 'direct30.nmos.zip'),
  link: async () => { const a = document.createElement('a'); a.href = `${B}?mb=1`; a.download = 'link.nmos.zip'; document.body.appendChild(a); a.click(); a.remove(); log('link clicked'); },
  info: async () => log(`secure=${window.isSecureContext} origin=${location.origin} subtle=${!!(crypto && crypto.subtle)} ua=${navigator.userAgent.slice(0, 60)}`),
};
(async () => {
  document.body.innerHTML = '<div style="background:#fff;color:#000;padding:8px">' +
    Object.keys(actions).map(k => `<button id="b-${k}">${k}</button> `).join('') + '<button id="b-close">close</button><pre id="out"></pre></div>';
  for (const [k, f] of Object.entries(actions)) document.getElementById('b-' + k).onclick = () => f().catch(e => log(`${k} error: ${e && e.message || e}`));
  document.getElementById('b-close').onclick = () => risuai.hideContainer();
  await risuai.registerSetting('NMOS probe', () => risuai.showContainer('fullscreen'), '', 'none', 'nmos-probe');
  log('loaded');
})();
