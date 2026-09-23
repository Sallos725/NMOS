import { describe, expect, it, vi } from 'vitest';
import { DONE_MS } from '../src/hud';
import { createHud, MAX_POLL_ERRORS, POLL_MS, type HudDeps, type HudDocument, type HudElement } from '../src/hud-host';

interface FakeElement extends HudElement { tag: string; text: string; styles: Record<string, string>; children: FakeElement[];
  removed: boolean; classes: string[] }

function fakePage(existing = false) {
  const log: string[] = [];
  const listeners = new Map<string, (e: { clientX: number; clientY: number }) => void>();
  const make = (tag: string): FakeElement => {
    const node: FakeElement = {
      tag, text: '', styles: {}, children: [], removed: false, classes: [],
      async remove() { node.removed = true; log.push(`remove ${tag}${node.classes.map((c) => '.' + c).join('')}`); },
      async appendChild(child) { node.children.push(child as FakeElement); },
      async addClass(name) { node.classes.push(name); },
      async setStyleAttribute() {},
      async setStyle(property, value) { node.styles[property] = value; },
      async setTextContent(value) { node.text = value; log.push(`text ${value}`); },
      async getBoundingClientRect() { return { left: 900, top: 8, right: 1100, bottom: 40 }; },
      async addEventListener(_type, fn) { const id = `l${listeners.size + 1}`; listeners.set(id, fn); return id; },
      async removeEventListener(_type, id) { listeners.delete(id); },
    };
    return node;
  };
  const body = make('body');
  const stale = existing ? make('div') : null;
  if (stale) stale.classes.push('nmos-hud');
  const doc: HudDocument = {
    async querySelector(selector) {
      if (selector === 'body') return body;
      if (selector === '.nmos-hud') return stale && !stale.removed ? stale : body.children.find((c) => !c.removed) ?? null;
      return null;
    },
    async createElement(tag) { return make(tag); },
  };
  const pill = () => body.children.find((c) => !c.removed) ?? null;
  const click = (x: number, y: number) => { for (const fn of listeners.values()) fn({ clientX: x, clientY: y }); };
  return { doc, body, pill, log, listeners, click, stale };
}

function setup(opts: { enabled?: boolean; coverage?: (id: string) => Promise<unknown>; doc?: HudDocument | null;
  position?: () => string } = {}) {
  const page = fakePage();
  let now = 0;
  let enabled = opts.enabled ?? true;
  const timers: { at: number; fn: () => void; id: number }[] = [];
  let seq = 0;
  const openPanel = vi.fn();
  const coverage = vi.fn(opts.coverage ?? (async () => ({})));
  const rootDocument = vi.fn(async () => (opts.doc === undefined ? page.doc : opts.doc));
  const deps: HudDeps = {
    enabled: async () => enabled,
    lang: async () => 'ko',
    rootDocument,
    position: async () => (opts.position ? opts.position() : '0:0'),
    coverage,
    openPanel,
    now: () => now,
    debug: () => {},
    setTimer: (fn, ms) => { const id = ++seq; timers.push({ at: now + ms, fn, id }); return id; },
    clearTimer: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
  };
  const hud = createHud(deps);
  /** Advance the clock by `ms`, running due timers in order and letting the HUD settle after each. */
  async function advance(ms: number) {
    const end = now + ms;
    await hud.settled();
    for (;;) {
      timers.sort((a, b) => a.at - b.at);
      const next = timers[0];
      if (!next || next.at > end) break;
      timers.shift();
      now = Math.max(now, next.at);
      next.fn();
      await hud.settled();
    }
    now = end;
  }
  return { hud, page, deps, advance, openPanel, coverage, rootDocument, timers, setEnabled: (v: boolean) => { enabled = v; } };
}

const cov = (pendingExtract: number, done = 0, total = 4) => ({
  extraction: { generation: { key: 'x' }, eligible: total, compiled: done, pending: pendingExtract, failed: 0 },
  embeddings: { generation: null },
});

describe('createHud', () => {
  it('draws nothing and never touches the page while off', async () => {
    const { hud, rootDocument, page, advance } = setup({ enabled: false });
    hud.event({ type: 'request-start' });
    await advance(0);
    expect(rootDocument).not.toHaveBeenCalled();
    expect(page.body.children).toHaveLength(0);
  });

  it('draws one pill, replaces a leftover one, and skips unchanged views', async () => {
    const page = fakePage(true);
    const { hud, advance } = setup({ doc: page.doc });
    hud.event({ type: 'request-start' });
    hud.event({ type: 'request-start' });
    await advance(0);
    expect(page.stale?.removed).toBe(true);
    expect(page.body.children).toHaveLength(1);
    expect(page.log.filter((l) => l.startsWith('text'))).toEqual(['text 🧠 기억 불러오는 중…']);
    expect(page.pill()?.children[1]?.styles.display).toBe('none'); // no bar for a running request
  });

  it('opens the panel only for clicks on the pill', async () => {
    const { hud, page, advance, openPanel } = setup();
    hud.event({ type: 'request-start' });
    await advance(0);
    page.click(10, 10);
    page.click(950, 20);
    await advance(0);
    await new Promise((r) => setTimeout(r, 0));
    expect(openPanel).toHaveBeenCalledTimes(1);
  });

  it('polls coverage after a request until the work is done, then hides', async () => {
    const answers = [cov(2, 2), cov(1, 3), cov(0, 4)];
    const { hud, page, advance, coverage, timers } = setup({ coverage: async () => answers.shift() ?? cov(0, 4) });
    hud.event({ type: 'request-end', outcome: 'injected', chars: 10, conversationId: 'conv-1' });
    await advance(0);
    expect(coverage).toHaveBeenCalledWith('conv-1');
    expect(page.pill()?.children[0]?.text).toBe('✓ 기억 주입 (10자)');
    await advance(4000);  // outcome expired; second poll done at 3000
    expect(page.pill()?.children[0]?.text).toBe('추출 3/4');
    await advance(POLL_MS); // third poll: nothing pending
    expect(page.pill()?.children[0]?.text).toBe('✓ 처리 완료');
    expect(coverage).toHaveBeenCalledTimes(3);
    await advance(DONE_MS);
    expect(page.pill()).toBeNull();
    expect(timers).toHaveLength(0);
  });

  it('stops polling on 404 at once and after repeated errors', async () => {
    const gone = setup({ coverage: async () => { throw new Error('/v1/conversations/x/coverage -> HTTP 404'); } });
    gone.hud.background('x');
    await gone.advance(POLL_MS * 3);
    expect(gone.coverage).toHaveBeenCalledTimes(1);

    const flaky = setup({ coverage: async () => { throw new Error('deadline during coverage'); } });
    flaky.hud.background('x');
    await flaky.advance(POLL_MS * 10);
    expect(flaky.coverage).toHaveBeenCalledTimes(MAX_POLL_ERRORS);
  });

  it('clears progress and stops polling when the user moves to another chat', async () => {
    let where = '0:0';
    const { hud, page, advance, coverage } = setup({ coverage: async () => cov(3, 1), position: () => where });
    hud.background('conv-1');
    await advance(0);
    expect(page.pill()?.children[0]?.text).toBe('추출 1/4');
    where = '0:1';
    await advance(POLL_MS);
    expect(page.pill()).toBeNull();
    await advance(POLL_MS * 3);
    expect(coverage).toHaveBeenCalledTimes(1);
  });

  it('background without an id uses the last conversation seen', async () => {
    const { hud, advance, coverage } = setup({ coverage: async () => cov(0, 4) });
    hud.background();
    await advance(0);
    expect(coverage).not.toHaveBeenCalled();
    hud.event({ type: 'request-end', outcome: 'nothing-relevant', chars: 0, conversationId: 'conv-9' });
    await advance(0);
    hud.background();
    await advance(0);
    expect(coverage.mock.calls.map((c) => c[0])).toEqual(['conv-9', 'conv-9']);
  });

  it('turns itself off for the session when the page is not reachable', async () => {
    const { hud, advance, rootDocument } = setup({ doc: null });
    hud.event({ type: 'request-start' });
    await advance(0);
    expect(hud.problem()).toMatch(/mainDom/);
    hud.event({ type: 'request-start' });
    await advance(0);
    expect(rootDocument).toHaveBeenCalledTimes(1);
    hud.refresh();
    await advance(0);
    expect(hud.problem()).toBeNull();
  });

  it('erases the pill and its listener when switched off', async () => {
    const { hud, page, advance, setEnabled } = setup({ coverage: async () => cov(3, 1) });
    hud.background('conv-1');
    await advance(0);
    expect(page.pill()).not.toBeNull();
    setEnabled(false);
    hud.refresh();
    await advance(POLL_MS * 2);
    expect(page.pill()).toBeNull();
    expect(page.listeners.size).toBe(0);
  });
});
