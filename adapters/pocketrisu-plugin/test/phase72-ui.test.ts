// @vitest-environment happy-dom
// PHASE-72: floating Back-to-Top button, Raw Inspector section tabs + Show-all toggle, and sticky Explorer toolbar.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { openPanel, type PanelDeps } from '../src/ui';

const CID = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

const RAW_HTML = `<h1>Harbor</h1>`
  + `<p class="toc"><a href="#s-attention">Needs attention <span class="n">0</span></a> · `
  + `<a href="#s-people">Characters</a> · `
  + `<a href="#s-state">State</a> · `
  + `<a href="#s-facts">Facts <span class="n">2</span></a></p>`
  + `<details id="s-attention"><summary><h2>Needs attention</h2></summary><p>None</p></details>`
  + `<details id="s-people"><summary><h2>Characters</h2></summary><div class="tl-lazy" data-part="timeline"></div></details>`
  + `<details id="s-state" open><summary><h2>State</h2></summary><p>HP 100</p></details>`
  + `<details id="s-facts" open><summary><h2>Facts</h2></summary><p>Hana lives at the lighthouse</p></details>`;

const EXPLORE_HTML = `<div class="v v-doc v-explore">`
  + `<div class="v-exp-toolbar-slot"></div>`
  + `<div class="v-sec" id="s-facts" data-cat="facts"><h2 class="v-h2">Facts<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list"><div class="v-card v-exp-card" data-cat="facts"><div class="v-card-main">Fact A</div></div></div></div>`
  + `<div class="v-sec" id="s-pairs" data-cat="pairs"><h2 class="v-h2">Relationships<span class="v-n">1</span></h2>`
  + `<div class="v-exp-list"><div class="v-card v-exp-card" data-cat="pairs"><div class="v-card-main">Hana &amp; Kaito</div></div></div></div>`
  + `</div>`;

function makeDeps(opts: { rawHtml?: string; exploreHtml?: string; onCall?: (path: string) => void } = {}) {
  const d: PanelDeps = {
    api: async <T>(_method, path) => {
      opts.onCall?.(path);
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) {
        return {
          html: '<div class="v v-hub">Hub</div>',
          conversation: CID,
          meta: {
            conv: { id: CID, name: 'Harbor', turns: 42 },
            working: { state: 'ok', queued: 0, failed: 0 },
            attention: 0,
            chats: [{ id: CID, name: 'Harbor', turns: 42 }],
          },
        } as T;
      }
      if (path.startsWith(`/v1/views/c/${CID}/memory`)) return { html: '<div class="v v-doc">Memory</div>' } as T;
      if (path.startsWith(`/v1/views/c/${CID}/explore`)) return { html: opts.exploreHtml ?? EXPLORE_HTML } as T;
      if (path.startsWith(`/v1/views/c/${CID}/working`)) return { html: '<div class="v v-doc">Working</div>' } as T;
      if (path.startsWith(`/v1/inspector/c/${CID}`) && path.includes('part=timeline')) {
        return { html: '<div class="tl"><p>Timeline loaded</p></div>' } as T;
      }
      if (path.startsWith(`/v1/inspector/c/${CID}`)) return { html: opts.rawHtml ?? RAW_HTML } as T;
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

async function openRawInspector(): Promise<void> {
  panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
  await settle();
  panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="diag"]')!.click();
  await settle();
  const rawBtn = Array.from(panel().querySelectorAll<HTMLButtonElement>('.diag-toggle button'))
    .find((b) => b.textContent?.includes('Raw inspector'))!;
  rawBtn.click();
  await settle();
}

afterEach(() => {
  document.body.replaceChildren();
  document.head.replaceChildren();
});

describe('PHASE-72 floating Back-to-Top button', () => {
  it('stays hidden at top, appears past scroll threshold, and scrolls back to top on click', async () => {
    await openPanel(makeDeps(), 'status');
    await settle();

    const root = panel();
    const topBtn = root.querySelector<HTMLButtonElement>('.nmos-top-btn')!;
    expect(topBtn).not.toBeNull();
    expect(topBtn.getAttribute('aria-label')).toBe('Back to top');
    expect(topBtn.classList.contains('show')).toBe(false);
    expect(topBtn.querySelector('svg.ic')?.getAttribute('aria-hidden')).toBe('true');

    // Scroll down past threshold -> visible
    root.scrollTop = 420;
    root.dispatchEvent(new Event('scroll'));
    expect(topBtn.classList.contains('show')).toBe(true);

    // Click scrolls smoothly to 0
    const scrollSpy = vi.fn((opts?: ScrollToOptions | number) => {
      root.scrollTop = typeof opts === 'number' ? opts : (opts?.top ?? 0);
      root.dispatchEvent(new Event('scroll'));
    });
    root.scrollTo = scrollSpy as unknown as typeof root.scrollTo;
    topBtn.click();
    expect(scrollSpy).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
    expect(root.scrollTop).toBe(0);
    expect(topBtn.classList.contains('show')).toBe(false);

    // Mobile CSS positions button above bottom nav bar
    const css = Array.from(document.querySelectorAll('style')).map((s) => s.textContent ?? '').join('\n');
    expect(css).toContain('.nmos .nmos-top-btn{position:fixed;');
    expect(css).toContain('bottom:calc(70px + env(safe-area-inset-bottom))');
  });
});

describe('PHASE-72 Raw Inspector section tabs', () => {
  it('displays one section at a time by default, switches tabs, preserves active tab on refresh, and toggles Show all', async () => {
    const calls: string[] = [];
    await openPanel(makeDeps({ onCall: (p) => calls.push(p) }), 'status');
    await settle();
    await openRawInspector();

    const toc = panel().querySelector<HTMLElement>('p.toc.insp-tabs')!;
    expect(toc).not.toBeNull();
    expect(toc.getAttribute('role')).toBe('tablist');

    const sec = (id: string) => panel().querySelector<HTMLDetailsElement>(`#${id}`)!;
    const tab = (id: string) => toc.querySelector<HTMLAnchorElement>(`a[href="#${id}"]`)!;
    const toggle = toc.querySelector<HTMLButtonElement>('button.toc-all')!;

    // Default active tab is the first initially-open section (#s-state, since #s-attention/#s-people start closed)
    expect(sec('s-state').style.display).toBe('');
    expect(sec('s-state').open).toBe(true);
    expect(sec('s-facts').style.display).toBe('none');
    expect(sec('s-attention').style.display).toBe('none');
    expect(tab('s-state').classList.contains('on')).toBe(true);
    expect(tab('s-state').getAttribute('aria-selected')).toBe('true');
    expect(toggle.textContent).toBe('Show all');

    // Clicking #s-facts tab shows only #s-facts
    tab('s-facts').click();
    expect(sec('s-facts').style.display).toBe('');
    expect(sec('s-facts').open).toBe(true);
    expect(sec('s-state').style.display).toBe('none');
    expect(tab('s-facts').classList.contains('on')).toBe(true);
    expect(tab('s-state').classList.contains('on')).toBe(false);

    // Refreshing preserves the active #s-facts tab
    panel().querySelector<HTMLButtonElement>('.inspbar button:nth-of-type(2)')!.click();
    await settle();
    expect(sec('s-facts').style.display).toBe('');
    expect(sec('s-state').style.display).toBe('none');
    expect(panel().querySelector<HTMLAnchorElement>('p.toc.insp-tabs a[href="#s-facts"]')?.classList.contains('on')).toBe(true);

    // Clicking lazy #s-people tab shows it and fetches timeline immediately
    panel().querySelector<HTMLAnchorElement>('p.toc.insp-tabs a[href="#s-people"]')!.click();
    await settle();
    expect(sec('s-people').style.display).toBe('');
    expect(calls.some((p) => p.includes('part=timeline'))).toBe(true);
    expect(sec('s-people').textContent).toContain('Timeline loaded');

    // Toggling Show all reveals every section; toggling back restores single-tab mode on active tab
    const toggleAfter = panel().querySelector<HTMLButtonElement>('p.toc.insp-tabs button.toc-all')!;
    toggleAfter.click();
    expect(toggleAfter.textContent).toBe('Tab view');
    expect(toggleAfter.classList.contains('on')).toBe(true);
    expect(sec('s-state').style.display).toBe('');
    expect(sec('s-facts').style.display).toBe('');
    expect(sec('s-people').style.display).toBe('');

    toggleAfter.click();
    expect(toggleAfter.textContent).toBe('Show all');
    expect(sec('s-people').style.display).toBe('');
    expect(sec('s-facts').style.display).toBe('none');
  });
});

describe('PHASE-72 sticky Memory Explorer toolbar', () => {
  it('sticks toolbar on desktop, stays static on mobile, and scrolls up when switching category while scrolled down', async () => {
    await openPanel(makeDeps(), 'status');
    await settle();

    panel().querySelector<HTMLButtonElement>('.nmos-nav button[data-nav="memory"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.mem-subtabs button[data-memsub="explore"]')!.click();
    await settle();

    const css = Array.from(document.querySelectorAll('style')).map((s) => s.textContent ?? '').join('\n');
    expect(css).toContain('@media (min-width: 721px){');
    expect(css).toContain('.nmos.shell-on .exp-toolbar{position:sticky;top:54px;');
    expect(css).toContain('.nmos.shell-on .exp-toolbar,.nmos.shell-on .insp .toc.insp-tabs{position:static;box-shadow:none}');

    const root = panel();
    root.scrollTop = 360;
    const scrollSpy = vi.fn();
    root.scrollTo = scrollSpy as unknown as typeof root.scrollTo;

    panel().querySelector<HTMLButtonElement>('.exp-toolbar [data-exp-cat="pairs"]')!.click();
    expect(scrollSpy).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
  });
});
