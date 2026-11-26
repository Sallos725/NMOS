// @vitest-environment happy-dom
// PHASE-70 (ADR 0096): direct editing across Explorer/Person Sheet, subject correction, upgraded fact_add, and entity notes.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { repairAction } from '../src/inspector';
import { openPanel, type PanelDeps } from '../src/ui';

const CID = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const ENT_HANA = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
const ENT_WATCH = '0190f3a4-1b2c-7d3e-8f40-00000000000b';
const ENT_GHOST = '0190f3a4-1b2c-7d3e-8f40-00000000000c';
const NOTE_RID = '0190f3a4-1b2c-7d3e-8f40-777777777777';
const REPAIR_ID = '0190f3a4-1b2c-7d3e-8f40-999999999999';

const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

const EXPLORE_HTML = `<div class="v v-doc v-explore"><div class="v-head"><h1 class="v-h1">Harbor</h1></div>`
  + `<div class="v-exp-toolbar-slot"></div>`
  + `<div class="v-sec" id="s-facts" data-cat="facts"><h2 class="v-h2">Facts<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list"><div class="v-card v-exp-card v-fact-card" data-cat="facts" data-who="Hana">`
  + `<div class="v-card-main">Hana: cautious</div>`
  + `<details class="v-edit"><summary>Edit</summary><div class="v-edit-body">`
  + `<span class="rp" data-repair="fact_retract:101"></span>`
  + `<span class="rp" data-repair="fact_correct:101:value"></span>`
  + `<span class="rp" data-repair="fact_hidden:101"></span>`
  + `</div></details></div></div></div>`
  + `<div class="v-sec" id="s-items" data-cat="items"><h2 class="v-h2">Items<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list"><div class="v-card v-exp-card" data-cat="items" data-who="Silver Watch|Hana">`
  + `<div class="v-card-main"><a href="/inspector/c/${CID}/e/${ENT_WATCH}"><b>Silver Watch</b></a> · Held by Hana</div>`
  + `<div class="v-note-box"><span class="v-note-lbl">Note</span><span class="v-note-text">Engraved sunflower lid, runs 3 min slow</span></div>`
  + `<details class="v-edit"><summary>Edit</summary><div class="v-edit-body">`
  + `<span class="rp" data-repair="fact_correct:105:subject"></span>`
  + `<span class="rp" data-repair="entity_note:${ENT_WATCH}:edit"></span>`
  + `</div></details></div></div></div></div>`;

function makeDeps() {
  const calls: [string, string, unknown?][] = [];
  const d: PanelDeps = {
    api: async <T>(method, path, body) => {
      calls.push([method, path, body]);
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) {
        return {
          html: `<div class="v v-hub v-hub-compact"><a class="v-pill-link" href="/views/c/${CID}/person/${ENT_HANA}">Hana</a></div>`,
          conversation: CID,
          meta: {
            conv: { id: CID, name: 'Hana · Harbor', turns: 14 },
            working: { state: 'ok', queued: 0, failed: 0 },
            attention: 0,
            chats: [{ id: CID, name: 'Hana · Harbor', turns: 14 }],
          },
        } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/memory`)) return { html: '<div class="v v-doc"><div class="v-sec" id="s-now">Now</div></div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/explore`)) return { html: EXPLORE_HTML } as T;
      if (path.startsWith(`/v1/views/c/${CID}/person/`)) return { html: '<div class="v v-doc"><h1 class="v-h1">Hana</h1></div>' } as T;
      if (path.startsWith(`/v1/inspector/c/${CID}/e/`)) return { html: '<h1>Entity page</h1>' } as T;
      if (path.endsWith('/messages?limit=40')) {
        return [{ host_logical_id: 'm1', turn: 14, position: 14, role: 'char', name: 'Hana', preview: 'At the harbor.' }] as T;
      }
      if (path.endsWith('/repairs') && method === 'POST') return { repair: { id: REPAIR_ID }, applied: true } as T;
      if (path.endsWith(`/repairs/${NOTE_RID}/remove`) && method === 'POST') return { removed: true } as T;
      if (path.endsWith('/entities')) {
        return [
          { id: ENT_HANA, type: 'character', name: 'Hana', names: ['Hana'], mentions: 10, links: [], aliases: [] },
          {
            id: ENT_WATCH, type: 'item', name: 'Silver Watch', names: ['Silver Watch'], mentions: 4,
            links: [], aliases: [], note: { id: NOTE_RID, text: 'Engraved sunflower lid, runs 3 min slow' },
          },
          {
            id: ENT_GHOST, type: 'character', name: 'SystemBot', names: ['SystemBot'], mentions: 2,
            excluded: 'memory', links: [], aliases: [],
          },
        ] as T;
      }
      if (path.endsWith('/memory-mode')) return { strict: false, narrator: null, characters: ['Hana'] } as T;
      if (path.endsWith('/replies-only')) return { on: false } as T;
      if (path.includes('/status/candidates')) throw new Error('404');
      if (path === '/v1/worker/status') throw new Error('404');
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

describe('PHASE-70 sanitizer & repairAction allowlist', () => {
  it('accepts entity_note add/edit and rejects malformed values', () => {
    expect(repairAction(`entity_note:${ENT_WATCH}:add`)).toEqual({ kind: 'entity_note', item: ENT_WATCH, extra: 'add' });
    expect(repairAction(`entity_note:${ENT_WATCH}:edit`)).toEqual({ kind: 'entity_note', item: ENT_WATCH, extra: 'edit' });
    expect(repairAction(`fact_correct:105:subject`)).toEqual({ kind: 'fact_correct', item: '105', extra: 'subject' });
    expect(repairAction('entity_note:bad id:add')).toBeNull();
    expect(repairAction(`entity_note:${ENT_WATCH}:%00`)).toBeNull();
  });
});

describe('PHASE-70 Explorer edits, entity_note inline & page card, and upgraded fact_add', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  it('wires inline entity_note edit (prefilled), subject correction, and deduplicates fact_hidden', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    // No duplicate fact_hidden button on Explorer #s-facts card
    const factBtns = Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-facts .v-edit-body button'))
      .map((b) => b.textContent);
    expect(factBtns.filter((t) => t === 'Hidden')).toHaveLength(1);

    // Inline subject correction sends new_subject
    const subjBtn = Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-items button'))
      .find((b) => b.textContent === 'Correct subject')!;
    expect(subjBtn).toBeTruthy();
    subjBtn.click();
    const subjInput = panel().querySelector<HTMLInputElement>('#s-items .rpform input[type="text"]')!;
    subjInput.value = 'Kaito';
    Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-items .rpform button'))
      .find((b) => b.textContent === 'Save')!.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>)?.kind === 'fact_correct'
      && (b as Record<string, unknown>)?.item === '105'
      && (b as Record<string, unknown>)?.new_subject === 'Kaito')).toBe(true);

    // Inline entity_note form prefills from .v-note-text and submits entity_note repair
    const noteBtn = Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-items button'))
      .find((b) => b.textContent === 'Edit note')!;
    expect(noteBtn).toBeTruthy();
    noteBtn.click();
    const area = panel().querySelector<HTMLTextAreaElement>('#s-items .rp-note-form textarea')!;
    expect(area.value).toBe('Engraved sunflower lid, runs 3 min slow');
    area.value = 'Cracked glass, engraved sunflower lid';
    area.dispatchEvent(new Event('input'));
    Array.from(panel().querySelectorAll<HTMLButtonElement>('#s-items .rp-note-form button'))
      .find((b) => b.textContent === 'Save')!.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>)?.kind === 'entity_note'
      && (b as Record<string, unknown>)?.item === ENT_WATCH
      && (b as Record<string, unknown>)?.new_value === 'Cracked glass, engraved sunflower lid')).toBe(true);
  });

  it('upgrades fact_add form with dynamic subject_type and item predicates (world_fact / destroyed)', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    panel().querySelector<HTMLButtonElement>('.exp-add')!.click();
    await settle();

    const predSel = panel().querySelector<HTMLSelectElement>('select[aria-label="Predicate"]')!;
    const subjTypeSel = panel().querySelector<HTMLSelectElement>('select[aria-label="Subject type"]')!;
    const subjInput = panel().querySelector<HTMLInputElement>('input[aria-label="Subject"]')!;
    const objInput = panel().querySelector<HTMLInputElement>('input[aria-label="Object (optional)"]')!;
    const valInput = panel().querySelector<HTMLInputElement>('input[aria-label="Value (optional)"]')!;

    predSel.value = 'world_fact';
    predSel.dispatchEvent(new Event('change'));
    expect(subjTypeSel.style.display).not.toBe('none');
    expect(Array.from(subjTypeSel.options).map((o) => o.value)).toEqual(['item', 'place', 'group', 'concept']);
    expect(objInput.style.display).toBe('none');
    expect(valInput.style.display).not.toBe('none');

    subjTypeSel.value = 'item';
    subjInput.value = 'Silver Watch';
    valInput.value = 'Stopped at 3:15';
    Array.from(panel().querySelectorAll<HTMLButtonElement>('.card button.primary'))
      .find((b) => b.textContent === 'Save')!.click();
    await settle();

    expect(calls.some(([m, p, b]) => {
      if (m !== 'POST' || !p.endsWith('/repairs')) return false;
      const body = b as { kind?: string; fact?: Record<string, unknown> };
      return body.kind === 'fact_add'
        && body.fact?.predicate === 'world_fact'
        && body.fact?.subject === 'Silver Watch'
        && body.fact?.subject_type === 'item'
        && body.fact?.value === 'Stopped at 3:15'
        && body.fact?.object === undefined;
    })).toBe(true);
  });

  it('shows noteCard on item entity page (save & delete) while keeping pinCard hidden, and hides noteCard on leave', async () => {
    const { d, calls } = makeDeps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    // Click item link -> opens /v1/inspector/c/{CID}/e/{ENT_WATCH}
    panel().querySelector<HTMLAnchorElement>(`#s-items a[href="/inspector/c/${CID}/e/${ENT_WATCH}"]`)!.click();
    await settle();

    const noteCard = panel().querySelector<HTMLElement>('.note-card')!;
    expect(noteCard.style.display).not.toBe('none');
    expect(noteCard.textContent).toContain('Note for Silver Watch');
    const area = noteCard.querySelector<HTMLTextAreaElement>('textarea')!;
    expect(area.value).toBe('Engraved sunflower lid, runs 3 min slow');

    // Save updated note from noteCard
    area.value = 'Brass gears visible through the back';
    noteCard.querySelector<HTMLButtonElement>('button.primary')!.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>)?.kind === 'entity_note'
      && (b as Record<string, unknown>)?.item === ENT_WATCH
      && (b as Record<string, unknown>)?.new_value === 'Brass gears visible through the back')).toBe(true);

    // Delete note from noteCard
    noteCard.querySelector<HTMLButtonElement>('button.danger')!.click();
    await settle();
    expect(calls.some(([m, p]) => m === 'POST' && p.endsWith(`/repairs/${NOTE_RID}/remove`))).toBe(true);

    // Navigate back to Explore -> noteCard hides cleanly
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();
    expect(noteCard.style.display).toBe('none');
  });
});
