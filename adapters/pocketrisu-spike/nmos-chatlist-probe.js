//@name age4_probe
//@display-name AGE-4 probe
//@api 3.0
//@version 0.0.1
//@arg go string measurement trigger (tag[:reps])
(async () => {
  const log = (o) => console.log('[AGE4] ' + JSON.stringify(o));
  const now = () => performance.now();
  async function once() {
    const r = {};
    let t = now();
    const db = await risuai.getDatabase(['characters']);
    r.getDatabase_characters_ms = +(now() - t).toFixed(1);
    if (!db) return { denied: true };
    const chars = db.characters || [];
    let msgs = 0, chars_n = 0;
    r.chats = chars.map((c) => ({ cha: c.chaId, chats: (c.chats || []).map((ch) => {
      const n = (ch.message || []).length; msgs += n;
      for (const m of ch.message || []) chars_n += (m.data || '').length;
      return { id: ch.id, n, ph: !!ch._placeholder };
    }) }));
    r.messages = msgs; r.message_chars = chars_n;
    t = now();
    const o = await risuai.getDatabase(['characterOrder']);
    r.getDatabase_order_ms = +(now() - t).toFixed(1);
    r.order = o && o.characterOrder;
    t = now();
    let k = 0;
    for (let i = 0; ; i++) { const c = await risuai.getCharacterFromIndex(i); if (!c) break; k++; }
    r.charLoop_ms = +(now() - t).toFixed(1); r.charLoop_n = k;
    return r;
  }
  let last = '';
  setInterval(async () => {
    const v = String((await risuai.getArgument('go')) ?? '');
    if (!v || v === last) return;
    last = v;
    const [tag, reps] = v.split(':');
    for (let i = 0; i < Number(reps || 1); i++) {
      try { const r = await once(); if (i > 0) { delete r.chats; delete r.order; } log({ tag, rep: i, ...r }); }
      catch (e) { log({ tag, rep: i, error: String(e) }); }
    }
    log({ tag, done: true });
  }, 700);
  log({ loaded: true });
})();
