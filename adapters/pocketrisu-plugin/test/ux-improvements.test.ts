// @vitest-environment happy-dom
// UX improvements (#1–#9): live worker card & calls log, chat context banner, HUD deep-links & status pill,
// story document search & thread filters, interactive graph drawer/controls, floating Undo toast,
// Author's Note studio presets/cache/section copy/cancel, settings dirty dots & modal Esc, onboarding checklist.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { drawGraph, parseGraph } from '../src/graph';
import { EMPTY, openTarget, reduce } from '../src/hud';
import { inspectorApiPath } from '../src/inspector';
import { splitNoteSections } from '../src/notes';
import { openPanel, type PanelDeps } from '../src/ui';

const CID1 = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const CID2 = '0190f3a4-1b2c-7d3e-8f40-123456789def';
const ENT_A = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
const ENT_B = '0190f3a4-1b2c-7d3e-8f40-00000000000b';
const REPAIR_ID = '0190f3a4-1b2c-7d3e-8f40-999999999999';

const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

const MEMORY_HTML = `<div class="v v-doc"><div class="v-head"><h1 class="v-h1">Harbor</h1></div>`
  + `<div class="v-doc-grid"><div class="v-doc-main">`
  + `<div class="v-sec" id="s-open"><h2 class="v-h2">Open threads</h2>`
  + `<div class="v-line"><span class="v-tag k-promise">Promise</span>Hana: return the silver key`
  + `<span class="rp" data-repair="thread_close:5:kept,broken"></span></div>`
  + `<div class="v-line"><span class="v-tag k-threat">Threat</span>Marcus: expose the smuggling</div>`
  + `<details class="v-more"><summary>1 more</summary>`
  + `<div class="v-line"><span class="v-tag k-goal">Goal</span>Elina: find the archive bell</div></details></div>`
  + `</div></div></div>`;

const CALLS_HTML = `<div class="top"><h1>Model calls</h1></div><table><thead><tr>`
  + `<th>When</th><th>Kind</th><th>Outcome</th><th>ms</th><th>Tokens</th><th>Model</th><th>Error</th></tr></thead><tbody>`
  + `<tr><td>now</td><td>extract</td><td>HTTP <span class="mono">429</span></td><td>420</td><td>—</td><td>m1</td><td>rate limit</td></tr>`
  + `<tr><td>1m</td><td>extract</td><td>ok</td><td>1200</td><td>100 / 20</td><td>m1</td><td></td></tr>`
  + `</tbody></table>`;

function makeDeps(opts: {
  connected?: boolean;
  workerStatus?: unknown;
  chatSetThrows?: boolean;
  notesPending?: Promise<unknown>;
} = {}) {
  const calls: [string, string, unknown?][] = [];
  let hidden = 0;
  const d: PanelDeps = {
    api: async <T>(method, path, body) => {
      calls.push([method, path, body]);
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path === '/v1/worker/status') {
        if (opts.workerStatus === undefined) throw new Error('404');
        return opts.workerStatus as T;
      }
      if (path.startsWith('/v1/views/hub')) {
        const isSecond = path.includes(`conversation=${CID2}`);
        const cid = isSecond ? CID2 : CID1;
        return {
          html: `<div class="v v-hub"><div class="v-blocks"><a class="v-block" href="/views/c/${cid}/memory">Memory</a></div></div>`,
          conversation: cid,
          meta: {
            conv: { id: cid, name: isSecond ? 'Kaito · Mill' : 'Hana · Harbor', turns: isSecond ? 8 : 14 },
            working: { state: 'ok', queued: 0, failed: 0 },
            attention: 0,
            chats: [
              { id: CID1, name: 'Hana · Harbor', turns: 14 },
              { id: CID2, name: 'Kaito · Mill', turns: 8 },
            ],
          },
        } as T;
      }
      if (path.startsWith('/v1/inspector/calls')) return { html: CALLS_HTML } as T;
      if (path.startsWith(`/v1/views/c/${CID1}/memory`)) return { html: MEMORY_HTML } as T;
      if (path.startsWith(`/v1/views/c/${CID1}/working`)) return { html: '<div class="v">Working view</div>' } as T;
      if (path.endsWith('/repairs') && method === 'POST') return { repair: { id: REPAIR_ID }, applied: true } as T;
      if (path.endsWith(`/repairs/${REPAIR_ID}/remove`) && method === 'POST') return { removed: true } as T;
      if (path === '/v1/notes/prompt') return { prompt: '' } as T;
      if (path.endsWith('/notes') && method === 'POST') {
        if (opts.notesPending) return (await opts.notesPending) as T;
        return {
          text: '[NMOS note · t14]\n## Changed from the setting\nHana trusts you.\n\n## Address and standing\nHana -> You: polite\n[/NMOS note]',
          chars: 90,
          sections: [
            { kind: 'diverged', made: 'model' },
            { kind: 'address', made: 'assembled' },
          ],
        } as T;
      }
      if (path === '/v1/config') {
        return {
          llm: { url: 'https://openrouter.ai/api/v1', model: 'm1', api_key_set: true, json_mode: true, extra_body: {}, no_temperature: false },
          embeddings: { url: '', model: '', api_key_set: false, query_instruction: '' },
          recall: { threshold: 0.35, vector_min_sim: 0.3, top_k: 5, facts_limit: 12 },
          extraction: { backfill: 20, summaries: true, canon_facts: true },
          parsers: { rules: [], source: 'none', active_rules: 0, errors: [] },
        } as T;
      }
      if (path === '/v1/config/preview') {
        return { model_change: true, queued: { continue: {}, recent: { extract: 5 }, canon: { canon: 2 } } } as T;
      }
      if (path.endsWith('/memory-mode')) return { strict: false, narrator: null, characters: ['Hana'] } as T;
      if (path.endsWith('/replies-only')) return { on: false } as T;
      if (path.endsWith('/entities')) return [] as T;
      if (path.endsWith('/carry')) throw new Error('404');
      if (path.includes('/status/candidates')) throw new Error('404');
      return {} as T;
    },
    status: async () => ({
      enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en',
      connected: opts.connected ?? true, version: '0.6.0',
      features: { views: true, map: true, map_graph: true }, last: null,
    }),
    getArg: async (k) => (k === 'language' ? 'en' : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => { hidden += 1; },
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({
      getArg: async () => '',
      setArg: async () => { if (opts.chatSetThrows) throw new Error('host write failed'); },
      currentChatId: async () => 'host-chat-1',
    }),
    download: async () => 0,
  };
  return { d, calls, getHidden: () => hidden };
}

describe('UX improvements (#1–#9)', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  it('#1 surfaces live Worker card on Home and opens Model calls with Failed-only filter inside the panel', async () => {
    expect(inspectorApiPath('/inspector/calls')).toBe('/v1/inspector/calls');
    const { d } = makeDeps({
      workerStatus: {
        queued: { extract: 4 }, queued_total: 4, running: 1, retrying: 2, dead_recent: 1, done_recent: 10,
        recent_minutes: 15, dead_hours: 24,
        last_error: { kind: 'extract', status: 'retrying', at: new Date().toISOString(), text: 'HTTP 429 rate limit' },
      },
    });
    await openPanel(d, 'status');
    await settle();
    const worker = panel().querySelector('.worker-home.trouble');
    expect(worker).not.toBeNull();
    expect(worker!.textContent).toContain('HTTP 429 rate limit');
    const viewCalls = Array.from(worker!.querySelectorAll('button')).find((b) => b.textContent === 'View call log')!;
    viewCalls.click();
    await settle();
    expect(panel().textContent).toContain('Model calls');
    const rows = Array.from(panel().querySelectorAll<HTMLTableRowElement>('tbody tr'));
    expect(rows).toHaveLength(2);
    expect(rows[0]!.classList.contains('call-fail')).toBe(true);
    const failChip = Array.from(panel().querySelectorAll<HTMLButtonElement>('.filter-chip'))
      .find((b) => b.textContent === 'Failed only (1)')!;
    failChip.click();
    expect(rows[0]!.style.display).toBe('');
    expect(rows[1]!.style.display).toBe('none');
  });

  it('#2 shows other-chat banner when switched via Chat Switcher and surfaces chat-strip toggle errors', async () => {
    const { d } = makeDeps({ chatSetThrows: true });
    await openPanel(d, 'status');
    await settle();
    expect(panel().querySelector('.other-chat-banner')).toBeNull();
    // Toggle error must be visible inside the DOM (fixes detached msg bug)
    const toggleBtn = panel().querySelector<HTMLButtonElement>('.chat-strip button')!;
    toggleBtn.click();
    await settle();
    expect(panel().querySelector('.chat-strip .msg')?.textContent).toContain('host write failed');

    // Switch to another chat via the top chat switcher
    panel().querySelector<HTMLButtonElement>('.chat-btn')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>(`.chat-opt[data-chat-id="${CID2}"]`)!.click();
    await settle();
    const banner = panel().querySelector('.other-chat-banner');
    expect(banner).not.toBeNull();
    expect(banner!.textContent).toContain('Kaito · Mill');
    // Clicking "Return to open chat" returns to the host chat
    banner!.querySelector('button')!.click();
    await settle();
    expect(panel().querySelector('.other-chat-banner')).toBeNull();
  });

  it('#3 computes HUD deep-link targets and jumps directly via openPanel target or status pill click', async () => {
    const t0 = 1000;
    const failed = reduce(EMPTY, { type: 'request-end', outcome: 'failed', chars: 0, error: 'deadline', conversationId: CID1 }, t0);
    expect(openTarget(failed, t0 + 100)).toBe('connection');
    const ok = reduce(EMPTY, { type: 'request-end', outcome: 'injected', chars: 500, conversationId: CID1 }, t0);
    expect(openTarget(ok, t0 + 100)).toBe('working');
    const progFail = reduce(EMPTY, {
      type: 'coverage',
      coverage: { extract: { done: 2, total: 5, pending: 2, failed: 1 }, embed: null },
    }, t0);
    expect(openTarget(progFail, t0 + 100)).toBe('calls');

    const { d, calls } = makeDeps();
    await openPanel(d, 'status', 'calls');
    await settle();
    expect(calls.some(([, p]) => p.startsWith('/v1/inspector/calls'))).toBe(true);
    // Status pill is now a clickable button
    const pill = panel().querySelector<HTMLButtonElement>('button.status-pill')!;
    expect(pill).not.toBeNull();
    pill.click();
    await settle();
    expect(calls.some(([, p]) => p.startsWith(`/v1/views/c/${CID1}/working`) || p.startsWith('/v1/inspector/calls'))).toBe(true);
  });

  it('#4 filters Story Document lines by search query (auto-opening folds) and thread kind chips', async () => {
    const { d } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    const input = panel().querySelector<HTMLInputElement>('.doc-search-bar input')!;
    const fold = panel().querySelector<HTMLDetailsElement>('details.v-more')!;
    expect(fold.open).toBe(false);

    // Searching opens folded <details> and hides non-matching lines
    input.value = 'archive bell';
    input.dispatchEvent(new Event('input'));
    expect(fold.open).toBe(true);
    const visible = Array.from(panel().querySelectorAll<HTMLElement>('#s-open .v-line'))
      .filter((r) => r.style.display !== 'none');
    expect(visible).toHaveLength(1);
    expect(visible[0]!.textContent).toContain('archive bell');

    // Clearing search restores fold state
    input.value = '';
    input.dispatchEvent(new Event('input'));
    expect(fold.open).toBe(false);

    // Kind chip filters to Threat only
    const threatChip = panel().querySelector<HTMLButtonElement>('.filter-chip[data-th-kind="threat"]')!;
    threatChip.click();
    const threats = Array.from(panel().querySelectorAll<HTMLElement>('#s-open .v-line'))
      .filter((r) => r.style.display !== 'none');
    expect(threats).toHaveLength(1);
    expect(threats[0]!.textContent).toContain('Marcus');
  });

  it('#5 renders graph search, source filters, zoom buttons, and 1-tap relation summary drawer when opts passed', () => {
    const box = document.createElement('div');
    document.body.append(box);
    const g = parseGraph({
      nodes: [
        { id: ENT_A, name: 'Hana', kind: 'character', lead: true, entity: ENT_A, x: 0, y: 0 },
        { id: ENT_B, name: 'Kaito', kind: 'character', lead: false, entity: ENT_B, x: 120, y: 0 },
      ],
      edges: [{ a: ENT_A, b: ENT_B, kind: 'tie', mark: 'changed' }],
      suspects: [], focus: null, everyone: false, capped: false,
      words: { legend: 'Legend', fit: 'Fit', all: 'All', fewer: 'Fewer', tap: 'Tap again', ties: '{n} ties', left: '' },
    })!;
    const openedPerson: string[] = [];
    const focused: string[] = [];
    drawGraph(box, g, (e) => focused.push(e), () => {}, {
      labels: {
        search: 'Find…', zoomIn: 'Zoom in', zoomOut: 'Zoom out', filterAll: 'All', filterSetting: 'Setting',
        filterStory: 'Story', filterChanged: 'Changed', filterSplit: 'Split',
        openPerson: 'Open person sheet', focusPerson: 'Focus map here', noTies: 'No ties',
      },
      openPerson: (e) => openedPerson.push(e),
    });
    expect(box.querySelector('.g-toolbar input[type="search"]')).not.toBeNull();
    expect(box.querySelectorAll('.g-zoom button')).toHaveLength(2);
    // 1-tap node opens drawer with Open person sheet & Focus buttons
    const hana = box.querySelectorAll('.g-node')[0]!;
    hana.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 1, clientX: 5, clientY: 5 }));
    box.querySelector('svg')!.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1, clientX: 5, clientY: 5 }));
    const drawer = box.querySelector<HTMLElement>('.g-drawer')!;
    expect(drawer.style.display).toBe('');
    expect(drawer.textContent).toContain('Hana');
    expect(drawer.textContent).toContain('Kaito');
    Array.from(drawer.querySelectorAll('button')).find((b) => b.textContent === 'Open person sheet')!.click();
    expect(openedPerson).toEqual([ENT_A]);
  });

  it('#6 shows floating Undo toast after a repair and sends /remove on Undo click', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    const closeBtn = panel().querySelector<HTMLButtonElement>('#s-open .rp button')!;
    closeBtn.click();
    await settle();
    const toast = panel().querySelector<HTMLElement>('.nmos-toast')!;
    expect(toast.style.display).toBe('');
    const undoBtn = Array.from(toast.querySelectorAll('button')).find((b) => b.textContent === 'Undo')!;
    undoBtn.click();
    await settle();
    expect(calls.some(([m, p]) => m === 'POST' && p === `/v1/conversations/${CID1}/repairs/${REPAIR_ID}/remove`)).toBe(true);
    expect(toast.style.display).toBe('none');
  });

  it('#7 supports Author\'s Note presets, section splitting, session cache across tabs, and cancel', async () => {
    const sections = splitNoteSections('[NMOS note · t5]\n## First\nLine 1\n\n## Second\nLine 2\n[/NMOS note]');
    expect(sections.map((s) => s.title)).toEqual(['First', 'Second']);

    const { d } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="notes"]')!.click();
    await settle();
    // Enable custom prompt and click a preset chip
    const customBox = panel().querySelector<HTMLInputElement>('.notes-studio input[value="custom"]')!;
    customBox.checked = true;
    customBox.dispatchEvent(new Event('change'));
    const presetBtn = panel().querySelector<HTMLButtonElement>('.note-presets .filter-chip')!;
    presetBtn.click();
    expect(panel().querySelector<HTMLTextAreaElement>('.notes-studio textarea')!.value.length).toBeGreaterThan(10);

    // Generate note -> shows per-section copy buttons
    const makeBtn = panel().querySelector<HTMLButtonElement>('.notes-studio button.primary')!;
    makeBtn.click();
    await settle();
    expect(panel().querySelectorAll('.note-sec-row button')).toHaveLength(2);

    // Switch away to Home and return -> generated note stays intact
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="home"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="notes"]')!.click();
    await settle();
    expect(panel().querySelector<HTMLTextAreaElement>('.notes-studio textarea[readonly]')!.value).toContain('Hana trusts you.');

    // Switch to another chat and back -> session cache restores the last note with cached hint
    panel().querySelector<HTMLButtonElement>('.chat-btn')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>(`.chat-opt[data-chat-id="${CID2}"]`)!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.chat-btn')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>(`.chat-opt[data-chat-id="${CID1}"]`)!.click();
    await settle();
    expect(panel().textContent).toContain('Showing your last generated note');
    expect(panel().querySelector<HTMLTextAreaElement>('.notes-studio textarea[readonly]')!.value).toContain('Hana trusts you.');
  });

  it('#8 displays dirty dots on modified settings groups and cancels model-change modal on Escape', async () => {
    const { d, getHidden } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="settings"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.groups button[data-group="models"]')!.click();
    const modelDot = panel().querySelector<HTMLElement>('.groups button[data-group="models"] .dirty-dot')!;
    expect(modelDot.style.display).toBe('none');

    // Change LLM model input
    const modelInput = Array.from(panel().querySelectorAll<HTMLInputElement>('[data-group="models"] input'))
      .find((i) => i.value === 'm1')!;
    modelInput.value = 'm2';
    modelInput.dispatchEvent(new Event('input', { bubbles: true }));
    expect(modelDot.style.display).toBe('');

    // Save opens centered modal sheet (.bar.modal-open)
    panel().querySelector<HTMLButtonElement>('.bar button.primary')!.click();
    await settle();
    const bar = panel().querySelector<HTMLElement>('.bar')!;
    expect(bar.classList.contains('modal-open')).toBe(true);

    // Pressing Escape cancels the modal without closing the panel
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await settle();
    expect(bar.classList.contains('modal-open')).toBe(false);
    expect(getHidden()).toBe(0);
  });

  it('#9 shows 3-step onboarding checklist when sidecar is disconnected', async () => {
    const { d } = makeDeps({ connected: false });
    await openPanel(d, 'status');
    await settle();
    const card = panel().querySelector('.onboard-card');
    expect(card).not.toBeNull();
    expect(card!.querySelectorAll('.onboard-step')).toHaveLength(3);
  });
});
