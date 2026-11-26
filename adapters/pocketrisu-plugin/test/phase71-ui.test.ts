// @vitest-environment happy-dom
// PHASE-71: semantic repair button affordance, passive metadata chips, and Raw Inspector table action-bar grouping.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { openPanel, repairIcon, repairTone, type PanelDeps } from '../src/ui';

const CID = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

function makeDeps(pages: { explore?: string; inspector?: string } = {}) {
  const d: PanelDeps = {
    api: async <T>(_method, path) => {
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) {
        return {
          html: '<div class="v v-hub">Hub</div>',
          conversation: CID,
          meta: {
            conv: { id: CID, name: 'Harbor', turns: 14 },
            working: { state: 'ok', queued: 0, failed: 0 },
            attention: 0,
            chats: [{ id: CID, name: 'Harbor', turns: 14 }],
          },
        } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/memory`)) return { html: '<div class="v v-doc">Memory</div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/explore`)) return { html: pages.explore ?? '<div class="v v-explore"></div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/working`)) return { html: '<div class="v v-doc">Working</div>' } as T;
      if (path.startsWith(`/v1/inspector/c/${CID}`)) return { html: pages.inspector ?? '<h1>Raw</h1>' } as T;
      if (path.endsWith('/entities')) return [] as T;
      if (path.endsWith('/memory-mode')) return { strict: false, narrator: null, characters: [] } as T;
      if (path.endsWith('/replies-only')) return { on: false } as T;
      if (path.includes('/status/candidates') || path === '/v1/worker/status') throw new Error('404');
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
  return d;
}

afterEach(() => {
  document.body.replaceChildren();
  document.head.replaceChildren();
});

describe('PHASE-71 semantic repair helpers', () => {
  it('classifies destructive, undo, and modify/action repair kinds with icons', () => {
    for (const k of ['fact_retract', 'told_retract', 'entity_exclude', 'state_dismiss', 'attention_dismiss']) {
      expect(repairTone(k)).toBe('danger');
      expect(repairIcon(k)).toBe('close');
    }
    for (const k of ['undo', 'undo_batch']) {
      expect(repairTone(k)).toBe('undo');
      expect(repairIcon(k)).toBe('undo');
    }
    expect(repairTone('fact_correct')).toBe('act');
    expect(repairIcon('fact_correct')).toBe('edit');
    expect(repairIcon('entity_note')).toBe('edit');
    expect(repairIcon('fact_lock')).toBe('lock');
    expect(repairIcon('fact_hidden')).toBe('eyeOff');
    expect(repairIcon('fact_restore')).toBe('undo');
    expect(repairIcon('thread_reopen')).toBe('undo');
    expect(repairIcon('thread_close')).toBe('check');
  });
});

describe('PHASE-71 Explorer buttons and Raw Inspector action grouping', () => {
  it('renders semantic button classes + decorative SVG icons without altering textContent in Explorer', async () => {
    const exploreHtml = `<div class="v v-doc v-explore">`
      + `<div class="v-exp-toolbar-slot"></div>`
      + `<div class="v-sec" id="s-facts" data-cat="facts"><h2 class="v-h2">Facts<span class="v-n">1</span></h2>`
      + `<div class="v-exp-list"><div class="v-card v-exp-card" data-cat="facts">`
      + `<div class="v-card-top"><div class="v-card-badges"><span class="v-tag">event</span><span class="v-tag">minor</span></div></div>`
      + `<div class="v-card-main">Hana dropped the key</div>`
      + `<details class="v-edit" open><summary>Edit</summary><div class="v-edit-body">`
      + `<span class="rp" data-repair="fact_retract:101"></span>`
      + `<span class="rp" data-repair="fact_correct:101:value"></span>`
      + `<span class="rp" data-repair="fact_lock:101"></span>`
      + `<span class="rp" data-repair="undo:0190f3a4-1b2c-7d3e-8f40-999999999999"></span>`
      + `</div></details></div></div></div></div>`;

    await openPanel(makeDeps({ explore: exploreHtml }), 'status');
    await settle();

    // Open Memory → Explore
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    const btns = Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-facts .v-edit-body button'));
    const byText = (txt: string) => btns.find((b) => b.textContent === txt);

    const retract = byText('Retract')!;
    const hidden = byText('Hidden')!;
    const correct = byText('Correct value')!;
    const lock = byText('Lock')!;
    const undo = byText('Undo')!;

    expect(retract.classList.contains('rp-danger')).toBe(true);
    expect(hidden.classList.contains('rp-act')).toBe(true);
    expect(correct.classList.contains('rp-act')).toBe(true);
    expect(lock.classList.contains('rp-act')).toBe(true);
    expect(undo.classList.contains('rp-undo')).toBe(true);

    for (const b of [retract, hidden, correct, lock, undo]) {
      expect(b.classList.contains('mini')).toBe(true);
      expect(b.classList.contains('rp-btn')).toBe(true);
      const svg = b.querySelector('svg.ic');
      expect(svg).not.toBeNull();
      expect(svg?.getAttribute('aria-hidden')).toBe('true');
    }

    // Inline correction form Save button uses primary class
    correct.click();
    const formBtns = Array.from(panel().querySelectorAll<HTMLButtonElement>('.rpform button'));
    expect(formBtns.find((b) => b.textContent === 'Save')?.classList.contains('primary')).toBe(true);

    // Inline hidden form Save button uses primary class
    hidden.click();
    const hidSave = Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-facts .v-edit-body .rpform button'))
      .find((b) => b.textContent === 'Save');
    expect(hidSave?.classList.contains('primary')).toBe(true);

    // CSS distinguishes passive chips from interactive repair buttons
    const css = Array.from(document.querySelectorAll('style')).map((s) => s.textContent ?? '').join('\n');
    expect(css).toContain('.nmos .insp .chip{');
    expect(css).toContain('cursor:default');
    expect(css).toContain('.nmos button.rp-btn.rp-danger{');
    expect(css).toContain('.nmos button.rp-btn.rp-act{');
    expect(css).toContain('.nmos button.rp-btn.rp-undo{');
    expect(css).toContain('.nmos .insp .rp-bar.has-sep{');
  });

  it('groups Raw Inspector table-cell repair buttons into .rp-bar separated from text/chips', async () => {
    const bulkJson = JSON.stringify({
      g: 'canon', l: 'Canon', apply: { kind: 'fact_lock', item: '81' },
    }).replace(/"/g, '&quot;');
    const rawHtml = `<details id="s-facts" open><table><tbody>`
      + `<tr>`
      + `<td>Hana <span class="chip">event</span>`
      + `<span class="rp" data-repair="fact_retract:77"></span>`
      + `<span class="rp" data-repair="fact_correct:77:value"></span></td>`
      + `<td id="only-acts"><span class="rp" data-repair="fact_lock:81"></span><span class="rq" data-bulk="${bulkJson}"></span></td>`
      + `<td id="bad-rp"><span class="chip">public</span><span class="rp" data-repair="unknown_kind:1"></span></td>`
      + `</tr></tbody></table></details>`;

    await openPanel(makeDeps({ inspector: rawHtml }), 'status');
    await settle();

    // Open Memory → Diagnostics → Raw inspector
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="diag"]')!.click();
    await settle();
    const rawBtn = Array.from(panel().querySelectorAll<HTMLButtonElement>('.diag-toggle button'))
      .find((b) => b.textContent?.includes('Raw inspector'))!;
    rawBtn.click();
    await settle();

    const tds = Array.from(panel().querySelectorAll('#s-facts td'));
    // 1. Mixed text + chip + repairs -> separated .rp-bar.has-sep containing retract + auto-injected hidden + correct
    const mixedTd = tds[0]!;
    const chip = mixedTd.querySelector(':scope > span.chip');
    expect(chip?.textContent).toBe('event');
    const sepBar = mixedTd.querySelector(':scope > div.rp-bar.has-sep');
    expect(sepBar).not.toBeNull();
    const barBtns = Array.from(sepBar!.querySelectorAll<HTMLButtonElement>('button')).map((b) => b.textContent);
    expect(barBtns).toEqual(['Retract', 'Hidden', 'Correct value']);

    // 2. Action-only td -> .rp-bar WITHOUT .has-sep, bulk checkbox stays outside .rp-bar
    const onlyActsTd = tds[1]!;
    const plainBar = onlyActsTd.querySelector(':scope > div.rp-bar');
    expect(plainBar).not.toBeNull();
    expect(plainBar!.classList.contains('has-sep')).toBe(false);
    expect(plainBar!.querySelector('button')?.textContent).toBe('Lock');
    expect(onlyActsTd.querySelector(':scope > span.rq input[type="checkbox"]')).not.toBeNull();

    // 3. Dropped/empty span.rp is not wrapped into an empty .rp-bar
    const badRpTd = tds[2]!;
    expect(badRpTd.querySelector('.rp-bar')).toBeNull();
  });
});
