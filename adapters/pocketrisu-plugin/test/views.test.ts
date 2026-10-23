// @vitest-environment happy-dom
// PHASE-52: the panel's new screens — the hub first, the sidecar's stylesheet, the plugin's own actions.
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { createChatSwitch } from '../src/chatoff';
import { inspectorApiPath, inspectorConversation, inspectorEntity, keepAttribute, safeFragment } from '../src/inspector';
import { PALETTE } from '../src/palette';
import { openPanel, type PanelDeps } from '../src/ui';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
// happy-dom's import.meta.url is not a file URL: the tests run from the plugin's folder (npm test)
const tokens = JSON.parse(readFileSync(resolve(process.cwd(), '../../fixtures/unit/design-tokens-v1.json'), 'utf8'));

describe('design tokens (PHASE-52 D8)', () => {
  it('the palette is the fixture\'s', () => {
    expect({ ...PALETTE }).toEqual(tokens.color);
  });
});

describe('the sanitizer and the plugin\'s actions', () => {
  it('keeps data-act only for the three actions the plugin does', () => {
    for (const ok of ['notes', 'settings', 'backup', 'retry']) expect(keepAttribute('data-act', ok)).toBe(true);
    for (const bad of ['', 'delete', 'javascript:x', 'settings ']) expect(keepAttribute('data-act', bad)).toBe(false);
    const part = safeFragment('<a class="v-block" data-act="settings" onclick="x()">S</a><a data-act="rebuild">R</a>');
    const links = Array.from(part.querySelectorAll('a'));
    expect(links[0]!.getAttribute('data-act')).toBe('settings');
    expect(links[0]!.getAttribute('onclick')).toBeNull();
    expect(links[1]!.hasAttribute('data-act')).toBe(false);
  });
});

describe('view paths (PHASE-52)', () => {
  const e = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
  it('map the new screens to the sidecar, and only them', () => {
    expect(inspectorApiPath(`/views/c/${id}/memory`)).toBe(`/v1/views/c/${id}/memory`);
    expect(inspectorApiPath(`/views/c/${id}/memory#s-open`)).toBe(`/v1/views/c/${id}/memory`);
    expect(inspectorApiPath(`/views/c/${id}/person/${e}`)).toBe(`/v1/views/c/${id}/person/${e}`);
    expect(inspectorApiPath(`/views/c/${id}/working`)).toBe(`/v1/views/c/${id}/working`);
    expect(inspectorApiPath('/views/chats')).toBe('/v1/views/chats');
    for (const bad of [`/views/c/${id}/delete`, '/views/c/x/memory', '//evil/views/chats', `/views/c/${id}/person/x`]) {
      expect(inspectorApiPath(bad)).toBeNull();
    }
    expect(inspectorConversation(`/v1/views/c/${id}/memory`)).toBe(id);
    expect(inspectorEntity(`/v1/views/c/${id}/person/${e}`)).toEqual({ conversation: id, entity: e });
  });
});

const memory = `<div class="v v-doc"><div class="v-sec" id="s-open"><h2 class="v-h2">Open threads</h2>`
  + `<div class="v-line">Hana: find the bell<div class="v-meta">goal</div>`
  + `<span class="rp" data-repair="thread_close:5:achieved,abandoned"></span></div></div></div>`;

const person = `<div class="v v-doc"><div class="v-sec" id="s-time"><div class="tl v-tl"><div class="tl-row">`
  + `<span class="v-mark major" data-l="75" data-k="t9" data-v="Hana meets Kaito" data-s="t9"></span></div></div></div></div>`;

const hub = `<div class="v v-hub"><div class="v-blocks">`
  + `<a class="v-block v-wide ok" href="/inspector/c/${id}"><span class="v-bt">Working</span></a>`
  + `<a class="v-block v-big" href="/inspector/c/${id}"><span class="v-bt">Memory</span></a>`
  + `<a class="v-block" href="/views/c/${id}/memory"><span class="v-bt">Memory doc</span></a>`
  + `<a class="v-block" href="/views/c/${id}/working"><span class="v-bt">Working page</span></a>`
  + `<a class="v-block" href="/views/c/${id}/person/0190f3a4-1b2c-7d3e-8f40-00000000000a"><span class="v-bt">Hana</span></a>`
  + `<a class="v-block" data-act="settings"><span class="v-bt">Settings</span></a>`
  + `<a class="v-block" data-act="notes"><span class="v-bt">Author's note</span></a></div></div>`;

function deps(opts: { views?: boolean; css?: string } = {}) {
  const calls: [string, string][] = [];
  const d: PanelDeps = {
    api: async <T>(method: 'GET' | 'POST' | 'PUT', path: string) => {
      calls.push([method, path]);
      if (path === '/v1/views/style') return { css: opts.css ?? '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) return { html: hub, conversation: id } as T;
      if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: '<h1>Chat page</h1>' } as T;
      if (path.startsWith(`/v1/views/c/${id}/memory`)) return { html: memory } as T;
      if (path.includes('/person/')) return { html: person } as T;
      if (path.startsWith(`/v1/views/c/${id}/working`)) {
        return { html: '<div class="v"><span class="has-failed"></span><a data-act="retry">Retry failed</a></div>' } as T;
      }
      if (path.endsWith('/retry-failed')) return { retried: { extract: 2 } } as T;
      if (path.startsWith('/v1/inspector')) return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
      if (path.endsWith('/memory-mode')) throw new Error('404');
      if (path.includes('/status/candidates')) throw new Error('404');
      return {} as T;
    },
    status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
      version: '0.5.0', features: opts.views === false ? {} : { views: true }, last: null }),
    getArg: async (key) => (key === 'language' ? 'en' : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => 'host-chat-1' }),
    download: async () => 0,
  };
  return { d, calls };
}

const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

describe('the hub (PHASE-52 D1)', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  it('opens on the hub, with the sidecar\'s stylesheet injected once', async () => {
    const { d, calls } = deps();
    await openPanel(d, 'status');
    await settle();
    expect(panel().textContent).toContain('Memory');
    const hubCall = calls.find(([, p]) => p.startsWith('/v1/views/hub'));
    expect(hubCall?.[1]).toContain('chat=host-chat-1');
    expect(document.querySelectorAll('#nmos-views-style')).toHaveLength(1);
    expect(document.getElementById('nmos-views-style')!.textContent).toBe('.nmos .v{font-size:16px}');
  });

  it('follows a block into a page and comes back', async () => {
    const { d } = deps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>('a.v-big')!.click();
    await settle();
    expect(panel().textContent).toContain('Chat page');
    const back = Array.from(panel().querySelectorAll('button')).find((b) => b.textContent === '← Back')!;
    back.click();
    await settle();
    expect(panel().textContent).toContain('Memory');
  });

  it('does the plugin\'s own action for a data-act block', async () => {
    const { d } = deps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>('a[data-act="notes"]')!.click();
    await settle();
    expect(Array.from(panel().querySelectorAll('input[type=checkbox][value]')).map((b) => b.getAttribute('value')))
      .toEqual(['chronicle', 'changed', 'address']);
    panel().querySelector<HTMLAnchorElement>('a[data-act="settings"]')!.click();
    await settle();
    expect(panel().querySelector<HTMLElement>('.bar')!.style.display).toBe('');
  });

  it('refuses a stylesheet that could load anything', async () => {
    const { d } = deps({ css: '.nmos .v{background:url(https://x)}' });
    await openPanel(d, 'status');
    await settle();
    expect(document.getElementById('nmos-views-style')).toBeNull();
  });

  it('keeps today\'s screens with a sidecar that has no views', async () => {
    const { d, calls } = deps({ views: false });
    await openPanel(d, 'inspector');
    await settle();
    expect(calls.some(([, p]) => p.startsWith('/v1/views'))).toBe(false);
    expect(panel().querySelector(`a[href="/inspector/c/${id}"]`)).not.toBeNull();
  });

  it('opens the memory document without today\'s action row, and a tapped line shows its repair', async () => {
    const { d } = deps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/views/c/${id}/memory"]`)!.click();
    await settle();
    const row = panel().querySelector<HTMLElement>('.v-line')!;
    expect(row).not.toBeNull();
    const historyButton = Array.from(panel().querySelectorAll('button')).find((b) => b.textContent === 'Extract all history');
    expect(historyButton?.closest<HTMLElement>('div[style*="display: none"]') ?? null).not.toBeNull();
    expect(row.querySelector('.rp button')).not.toBeNull(); // the controls are there, shown by CSS when open
    expect(row.classList.contains('open')).toBe(false);
    row.click();
    expect(row.classList.contains('open')).toBe(true);
    row.click();
    expect(row.classList.contains('open')).toBe(false);
  });

  it('places a person\'s circles and opens a mark\'s card', async () => {
    const { d } = deps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>('a[href*="/person/"]')!.click();
    await settle();
    const mark = panel().querySelector<HTMLElement>('.v-mark')!;
    expect(mark.style.left).toBe('75%');
    mark.click();
    expect(panel().querySelector('.tl-card')!.textContent).toContain('Hana meets Kaito');
  });

  it('retries a chat\'s failed work from the working screen', async () => {
    const { d, calls } = deps();
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/views/c/${id}/working"]`)!.click();
    await settle();
    panel().querySelector<HTMLAnchorElement>('a[data-act="retry"]')!.click();
    await settle();
    expect(calls).toContainEqual(['POST', `/v1/conversations/${id}/retry-failed`]);
  });
});
