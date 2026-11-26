// @vitest-environment happy-dom
// PHASE-69: Memory Explorer, Focused Attention & Repairs, Dashboard Home, Upgraded Person Sheet, and 5-tab Memory shell.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { inspectorApiPath, inspectorConversation, keepAttribute, safeFragment } from '../src/inspector';
import { openPanel, type PanelDeps } from '../src/ui';

const CID = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const ENT_A = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
const ENT_B = '0190f3a4-1b2c-7d3e-8f40-00000000000b';
const ENT_C = '0190f3a4-1b2c-7d3e-8f40-00000000000c';
const REPAIR_ID = '0190f3a4-1b2c-7d3e-8f40-999999999999';

const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

const EXPLORE_HTML = `<div class="v v-doc v-explore"><div class="v-head"><h1 class="v-h1">Harbor</h1></div>`
  + `<div class="v-exp-toolbar-slot"><div class="v-chips"><a href="#s-facts">Facts</a></div></div>`
  + `<div class="v-sec" id="s-facts" data-cat="facts"><h2 class="v-h2">Facts<span class="v-n">2</span></h2>`
  + `<div class="v-exp-list">`
  + `<div class="v-card v-exp-card v-fact-card" data-cat="facts" data-who="Hana|old mill">`
  + `<div class="v-card-main">Hana → old mill</div>`
  + `<details class="v-edit"><summary>Edit</summary><div class="v-edit-body">`
  + `<span class="rp" data-repair="fact_retract:101"></span><span class="rp" data-repair="fact_correct:101:value"></span>`
  + `</div></details></div>`
  + `<div class="v-card v-exp-card v-fact-card" data-cat="facts" data-who="Hana" data-canon="1">`
  + `<div class="v-card-main">Hana: lighthouse keeper</div>`
  + `<details class="v-edit"><summary>Edit</summary><div class="v-edit-body">`
  + `<span class="rp" data-repair="fact_retract:102"></span><span class="rp" data-repair="fact_lock:102"></span>`
  + `</div></details></div>`
  + `</div></div>`
  + `<div class="v-sec" id="s-pairs" data-cat="pairs"><h2 class="v-h2">Relationships<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list">`
  + `<div class="v-card v-exp-card" data-cat="pairs" data-who="Hana|Kaito">`
  + `<div class="v-card-main">Hana ↔ Kaito · childhood friend</div></div>`
  + `</div></div>`
  + `<div class="v-sec" id="s-canon" data-cat="canon"><h2 class="v-h2">Setting<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list">`
  + `<div class="v-card v-exp-card" data-cat="canon">`
  + `<div class="v-card-main">Lorebook entry about the fog bell</div></div>`
  + `</div></div></div>`;

const BULK_JSON = JSON.stringify({
  g: 'stale', l: 'Stale threads', apply: { kind: 'thread_close', item: '55', outcome: 'abandoned' },
}).replace(/"/g, '&quot;');

const ATTENTION_HTML = `<div class="v v-doc v-attention"><div class="v-head"><h1 class="v-h1">Needs attention</h1></div>`
  + `<div class="v-sec" id="s-attention"><h2 class="v-h2">Needs attention<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list"><div class="v-card v-card-warn">`
  + `<div class="v-card-top"><span class="v-card-check"><span class="rq" data-bulk="${BULK_JSON}"></span></span>`
  + `<div class="v-card-badges"><span class="v-tag k-warn">Stale thread</span></div></div>`
  + `<div class="v-card-main">Hana → Kaito: meet at noon</div>`
  + `<div class="v-card-acts"><span class="rp" data-repair="thread_close:55:kept,broken"></span></div>`
  + `</div></div></div>`
  + `<div class="v-sec" id="s-repairs"><h2 class="v-h2">Direct edits<span class="v-n">0</span></h2><p class="v-text">None</p></div>`
  + `</div>`;

const PERSON_RICH_HTML = `<div class="v v-doc"><div class="v-head"><h1 class="v-h1">Hana</h1></div>`
  + `<p class="who"><span>Switch person</span> <b>Hana</b> · <a href="/views/c/${CID}/person/${ENT_B}">Kaito</a></p>`
  + `<div class="v-sec" id="s-facts"><h2 class="v-h2">Facts about them<span class="v-n">1</span></h2>`
  + `<div class="v-card v-fact-card"><div class="v-card-main">Hana → old mill</div>`
  + `<details class="v-edit"><summary>Edit</summary><div class="v-edit-body">`
  + `<span class="rp" data-repair="fact_retract:101"></span></div></details></div></div></div>`;

function makeDeps(opts: { legacy404?: boolean; workerStatus?: () => unknown } = {}) {
  const calls: [string, string, unknown?][] = [];
  const d: PanelDeps = {
    api: async <T>(method, path, body) => {
      calls.push([method, path, body]);
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) {
        return {
          html: `<div class="v v-hub v-hub-compact"><a class="v-pill-link" href="/views/c/${CID}/person/${ENT_A}">Hana</a></div>`,
          conversation: CID,
          meta: {
            conv: { id: CID, name: 'Hana · Harbor', turns: 14 },
            working: { state: 'ok', queued: 0, failed: 0 },
            attention: 1,
            chats: [{ id: CID, name: 'Hana · Harbor', turns: 14 }],
          },
        } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/memory`)) return { html: '<div class="v v-doc"><div class="v-sec" id="s-now">Now</div></div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/explore`)) {
        if (opts.legacy404) throw new Error(`${path} -> HTTP 404: Not Found`);
        return { html: EXPLORE_HTML } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/attention`)) {
        if (opts.legacy404) throw new Error(`${path} -> HTTP 404: Not Found`);
        return { html: ATTENTION_HTML } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/person/`)) return { html: PERSON_RICH_HTML } as T;
      if (path.startsWith(`/v1/views/c/${CID}/map`)) return { html: '<div class="v v-doc">Map</div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/working`)) return { html: '<div class="v v-doc">Working</div>' } as T;
      if (path.startsWith(`/v1/inspector/c/${CID}`)) {
        return { html: '<h1>Raw inspector</h1><details id="s-attention"><summary><h2>Needs attention</h2></summary><p>Fallback</p></details>' } as T;
      }
      if (path.endsWith('/messages?limit=40')) {
        return [{ host_logical_id: 'm1', turn: 14, position: 14, role: 'char', name: 'Hana', preview: 'At the harbor.' }] as T;
      }
      if (path.endsWith('/repairs/batch') && method === 'POST') {
        const b = body as { preview?: boolean };
        if (b?.preview) return { counts: { thread_close: 1 }, errors: 0, plan: [{}] } as T;
        return { applied: 1 } as T;
      }
      if (path.endsWith('/repairs') && method === 'POST') return { repair: { id: REPAIR_ID }, applied: true } as T;
      if (path.endsWith(`/repairs/${REPAIR_ID}/remove`) && method === 'POST') return { removed: true } as T;
      if (path.endsWith('/entities')) {
        return [
          { id: ENT_A, type: 'character', name: 'Hana', names: ['Hana'], mentions: 10, links: [], aliases: [] },
          { id: ENT_B, type: 'character', name: 'Kaito', names: ['Kaito'], mentions: 5, links: [], aliases: [] },
        ] as T;
      }
      if (path.endsWith('/entity-links/preview')) {
        return {
          action: 'join', changes: true, fingerprint: 'fp-1',
          before: [{ id: ENT_A, name: 'Hana', names: ['Hana'], persona: false },
            { id: ENT_B, name: 'Kaito', names: ['Kaito'], persona: false }],
          after: [{ id: ENT_C, name: 'Hana', names: ['Hana', 'Kaito'], persona: false }],
          lines: [], counts: {},
        } as T;
      }
      if (path.endsWith('/entity-links') && method === 'POST') {
        return { entity: { id: ENT_C, type: 'character', name: 'Hana', names: ['Hana', 'Kaito'], mentions: 15 } } as T;
      }
      if (path.endsWith('/memory-mode')) return { strict: false, narrator: null, characters: ['Hana'] } as T;
      if (path.endsWith('/replies-only')) return { on: false } as T;
      if (path.includes('/status/candidates')) throw new Error('404');
      if (path === '/v1/worker/status') {
        if (opts.workerStatus) return opts.workerStatus() as T;
        throw new Error('404');
      }
      return {} as T;
    },
    status: async () => ({
      enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en',
      connected: true, version: '0.7.0', features: { views: true, map: true, map_graph: false }, last: null,
    }),
    getArg: async (k) => (k === 'language' ? 'en' : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => 'host-chat-1' }),
    download: async () => 0,
  };
  return { d, calls };
}

describe('PHASE-69 sanitizer & route allowlist', () => {
  it('routes /explore and /attention and keeps only safe filter attributes', () => {
    expect(inspectorApiPath(`/views/c/${CID}/explore`)).toBe(`/v1/views/c/${CID}/explore`);
    expect(inspectorApiPath(`/views/c/${CID}/explore#s-facts`)).toBe(`/v1/views/c/${CID}/explore`);
    expect(inspectorApiPath(`/views/c/${CID}/attention`)).toBe(`/v1/views/c/${CID}/attention`);
    expect(inspectorApiPath(`/views/c/${CID}/explore/evil`)).toBeNull();
    expect(inspectorConversation(`/v1/views/c/${CID}/explore`)).toBe(CID);
    expect(inspectorConversation(`/v1/views/c/${CID}/attention`)).toBe(CID);

    expect(keepAttribute('data-cat', 'facts')).toBe(true);
    expect(keepAttribute('data-cat', 'FACTS')).toBe(false);
    expect(keepAttribute('data-cat', 'a-b')).toBe(false);
    expect(keepAttribute('data-who', 'Hana|Kaito')).toBe(true);
    expect(keepAttribute('data-who', 'a'.repeat(241))).toBe(false);
    expect(keepAttribute('data-who', 'Hana\nKaito')).toBe(false);
    expect(keepAttribute('data-canon', '1')).toBe(true);
    expect(keepAttribute('data-canon', '0')).toBe(false);

    const frag = safeFragment(
      '<div class="v-card" data-cat="facts" data-who="Hana|Kaito" data-canon="1" onclick="alert(1)" style="color:red">'
      + '<script>alert(2)</script><a href="javascript:alert(3)">x</a></div>',
    );
    const div = frag.querySelector('div')!;
    expect(div.getAttribute('data-cat')).toBe('facts');
    expect(div.getAttribute('data-who')).toBe('Hana|Kaito');
    expect(div.getAttribute('data-canon')).toBe('1');
    expect(div.hasAttribute('onclick')).toBe(false);
    expect(div.hasAttribute('style')).toBe(false);
    expect(frag.querySelector('script')).toBeNull();
    expect(frag.querySelector('a')!.hasAttribute('href')).toBe(false);
  });
});

describe('PHASE-69 Memory 5-tab workspace, Explorer, Attention, Person Sheet & Home compact hub', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  it('requests compact=1 on Home hub and renders 5 flattened Memory sub-tabs defaulting to story', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    expect(calls.some(([, p]) => p.startsWith('/v1/views/hub') && p.includes('compact=1'))).toBe(true);

    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    const tabs = Array.from(panel().querySelectorAll<HTMLButtonElement>('.mem-subtabs button')).map((b) => b.dataset.memsub);
    expect(tabs).toEqual(['story', 'explore', 'attention', 'map', 'diag']);
    expect(panel().querySelector('.mem-subtabs button[data-memsub="story"]')?.classList.contains('on')).toBe(true);
    expect(calls.some(([, p]) => p.startsWith(`/v1/views/c/${CID}/memory`) && p.includes('rich=1'))).toBe(true);
  });

  it('falls back gracefully to raw inspector when an older sidecar returns 404 on /explore or /attention', async () => {
    const { d, calls } = makeDeps({ legacy404: true });
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();

    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();
    expect(calls.some(([, p]) => p.startsWith(`/v1/views/c/${CID}/explore`))).toBe(true);
    expect(panel().textContent).toContain('Raw inspector');

    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="attention"]')!.click();
    await settle();
    const attn = panel().querySelector<HTMLDetailsElement>('#s-attention')!;
    expect(attn.open).toBe(true);
  });

  it('filters Explorer cards by category, search, character, canon toggle, and wires inline repair + Add fact', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    const visibleCards = () => Array.from(panel().querySelectorAll<HTMLElement>('.v-exp-card'))
      .filter((c) => c.style.display !== 'none');

    // Default: canon fact (data-canon="1") hidden while story fact exists -> 3 visible cards (story fact, pair, canon doc)
    expect(visibleCards()).toHaveLength(3);
    expect(visibleCards().some((c) => c.textContent?.includes('lighthouse keeper'))).toBe(false);

    // Toggle "Include setting facts" reveals the canon fact card
    const canonToggle = panel().querySelector<HTMLButtonElement>('.exp-canon-toggle')!;
    canonToggle.click();
    expect(visibleCards()).toHaveLength(4);
    expect(visibleCards().some((c) => c.textContent?.includes('lighthouse keeper'))).toBe(true);

    // Category pill: Relationships only
    panel().querySelector<HTMLButtonElement>('.exp-toolbar [data-exp-cat="pairs"]')!.click();
    expect(visibleCards()).toHaveLength(1);
    expect(visibleCards()[0]!.textContent).toContain('childhood friend');

    // Back to All + Character dropdown filter: Kaito
    panel().querySelector<HTMLButtonElement>('.exp-toolbar [data-exp-cat="all"]')!.click();
    const whoSel = panel().querySelector<HTMLSelectElement>('select.exp-who')!;
    whoSel.value = 'Kaito';
    whoSel.dispatchEvent(new Event('change'));
    expect(visibleCards()).toHaveLength(1);
    expect(visibleCards()[0]!.textContent).toContain('Kaito');

    // Reset character + search text
    whoSel.value = '';
    whoSel.dispatchEvent(new Event('change'));
    const search = panel().querySelector<HTMLInputElement>('.exp-toolbar input[type="search"]')!;
    search.value = 'fog bell';
    search.dispatchEvent(new Event('input'));
    expect(visibleCards()).toHaveLength(1);
    expect(visibleCards()[0]!.textContent).toContain('fog bell');

    // Non-matching search displays empty notice
    search.value = 'no-such-term';
    search.dispatchEvent(new Event('input'));
    expect(panel().querySelector<HTMLElement>('.exp-empty')!.style.display).toBe('');

    // Clear search and test inline repair + fact_hidden (only on story fact, not canon fact) + Undo toast
    search.value = '';
    search.dispatchEvent(new Event('input'));
    const factCards = panel().querySelectorAll<HTMLElement>('.v-fact-card');
    expect(factCards[0]!.textContent).toContain('Hidden'); // fact_hidden attached on story fact
    expect(factCards[1]!.textContent).not.toContain('Hidden'); // NOT attached on canon-only fact

    const retractBtn = factCards[0]!.querySelector<HTMLButtonElement>('.v-edit .rp button')!;
    retractBtn.click();
    await settle();
    expect(calls.some(([m, p]) => m === 'POST' && p === `/v1/conversations/${CID}/repairs`)).toBe(true);
    expect(panel().querySelector<HTMLElement>('.nmos-toast')!.style.display).toBe('');

    // "+ Add fact" opens factAddCard visibly
    panel().querySelector<HTMLButtonElement>('.exp-add')!.click();
    await settle();
    expect(calls.some(([, p]) => p === `/v1/conversations/${CID}/messages?limit=40`)).toBe(true);
    expect(panel().textContent).toContain('At the harbor.');
  });

  it('wires Phase 57 bulk selection and batch apply inside dedicated /attention view', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="attention"]')!.click();
    await settle();

    const bulkBar = panel().querySelector<HTMLElement>('.bulk-card')!;
    expect(bulkBar.style.display).toBe('');
    const box = panel().querySelector<HTMLInputElement>('.v-card-check input[type="checkbox"]')!;
    box.checked = true;
    box.dispatchEvent(new Event('change'));

    const applyBtn = Array.from(bulkBar.querySelectorAll('button')).find((b) => b.textContent?.includes('Apply'))!;
    applyBtn.click(); // preview
    await settle();
    applyBtn.click(); // confirm
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p === `/v1/conversations/${CID}/repairs/batch`
      && !(b as { preview?: boolean })?.preview)).toBe(true);
  });

  it('requests rich=1 on Person Sheet and stays in /views/c/.../person after entity join', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/views/c/${CID}/person/${ENT_A}"]`)!.click();
    await settle();

    expect(calls.some(([, p]) => p.startsWith(`/v1/views/c/${CID}/person/${ENT_A}`) && p.includes('rich=1'))).toBe(true);
    // Character switcher <p class="who"> hydrated to <select>
    expect(panel().querySelector('p.who select')).not.toBeNull();
    // Pin + Link cards mounted
    expect(panel().textContent).toContain('Always keep in memory');
    const joinBtn = Array.from(panel().querySelectorAll('button')).find((b) => b.textContent === 'Join')!;
    joinBtn.click();
    await settle();
    const confirmBtn = Array.from(panel().querySelectorAll('button')).find((b) => b.textContent?.toLowerCase().includes('join') && b !== joinBtn)!;
    confirmBtn.click();
    await settle();
    // Redirected to /v1/views/c/{cid}/person/{ENT_C}, NOT raw /v1/inspector/c/{cid}/e/{ENT_C}
    expect(calls.some(([, p]) => p.startsWith(`/v1/views/c/${CID}/person/${ENT_C}`))).toBe(true);
    expect(calls.some(([, p]) => p.startsWith(`/v1/inspector/c/${CID}/e/${ENT_C}`))).toBe(false);
  });

  it('dismisses a stale Model work trouble warning on Home and re-surfaces on a newer error', async () => {
    localStorage.clear();
    let currentWorker: Record<string, unknown> = {
      queued: { extract: 0, reveal: 0, summarize: 0, canon: 0, embed: 0 },
      queued_total: 0, running: 0, retrying: 0, dead_recent: 1, done_recent: 1, recent_minutes: 30, dead_hours: 24,
      last_error: { kind: 'canon', status: 'dead', at: '2026-11-25T14:53:18+00:00', text: 'HTTP 429' },
      calls: { minutes: 60, total: 1, ok: 1, failed: 0, by_fault: {}, median_ms: 500 },
    };
    const { d } = makeDeps({ workerStatus: () => currentWorker });
    await openPanel(d, 'status');
    await settle();
    expect(panel().querySelector('.worker-home.trouble')).not.toBeNull();
    expect(panel().querySelector('.status-pill.err')).not.toBeNull();

    // Dismissing hides the trouble card and clears the red error state from the top Status Pill
    panel().querySelector<HTMLButtonElement>('[data-worker-dismiss]')!.click();
    await settle();
    expect(panel().querySelector('.worker-home')).toBeNull();
    expect(panel().querySelector('.status-pill.err')).toBeNull();

    // Navigating away and back to Home keeps the same error dismissed
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="home"]')!.click();
    await settle();
    expect(panel().querySelector('.worker-home')).toBeNull();

    // When a newer error occurs, the trouble warning re-appears automatically
    currentWorker = {
      ...currentWorker,
      last_error: { kind: 'extract', status: 'dead', at: '2026-11-26T02:00:00+00:00', text: 'HTTP 500' },
    };
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="home"]')!.click();
    await settle();
    expect(panel().querySelector('.worker-home.trouble')).not.toBeNull();
    expect(panel().querySelector('.worker-home.trouble')!.textContent).toContain('HTTP 500');
  });
});
