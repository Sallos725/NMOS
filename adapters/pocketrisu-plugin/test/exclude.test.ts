// @vitest-environment happy-dom
// PHASE-47: "not a character" — out of the cast by default, memory too only when the box is ticked, each action
// carrying the fingerprint of the scope it was previewed for.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { repairAction } from '../src/inspector';
import { openPanel, type PanelDeps } from '../src/ui';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const e = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
const hub = `<div class="v v-hub"><div class="v-blocks"><a class="v-block" href="/views/c/${id}/person/${e}">Gloomfang</a></div></div>`;
const person = `<div class="v v-doc"><div class="v-line">Not a character?<span class="rp" data-repair="entity_exclude:${e}:Gloomfang"></span></div></div>`;

function deps() {
  const posts: [string, unknown][] = [];
  const d: PanelDeps = {
    api: async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown) => {
      if (method === 'POST') posts.push([path, body]);
      if (path === '/v1/views/style') return { css: '.nmos .v{font-size:16px}' } as T;
      if (path.startsWith('/v1/views/hub')) return { html: hub, conversation: id } as T;
      if (path.includes('/person/')) return { html: person } as T;
      if (path.endsWith('/repairs/preview')) {
        const scope = (body as { scope: string }).scope;
        return { action: 'exclude', changes: true, before: [], after: [], lines: [], counts: {}, scope,
          scopes: { cast: { pairs: 1, facts: 0 }, memory: { pairs: 1, facts: 2 } }, fingerprint: `fp-${scope}` } as T;
      }
      if (path.endsWith('/repairs')) return { repair: { id: 'r1' }, applied: e } as T;
      if (path.endsWith('/entities')) return [] as T;
      return {} as T;
    },
    status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
      version: '0.5.0', features: { views: true }, last: null }),
    getArg: async (key) => (key === 'language' ? 'en' : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => 'host-chat-1' }),
    download: async () => 0,
  };
  return { d, posts };
}

const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

async function open(d: PanelDeps) {
  await openPanel(d, 'status');
  await settle();
  panel().querySelector<HTMLAnchorElement>('a[href*="/person/"]')!.click();
  await settle();
  const button = Array.from(panel().querySelectorAll('button')).find((b) => b.textContent === 'Gloomfang: not a character')!;
  button.click();
  await settle();
  return button;
}

describe('not a character (PHASE-47)', () => {
  afterEach(() => { document.body.replaceChildren(); document.head.replaceChildren(); });

  it('is a repair mark the sanitizer keeps', () => {
    expect(repairAction(`entity_exclude:${e}:Gloomfang`)).toEqual({ kind: 'entity_exclude', item: e, extra: 'Gloomfang' });
    expect(repairAction('entity_exclude:not an id')).toBeNull();
  });

  it('marks it out of the cast by default with the cast preview\'s fingerprint', async () => {
    const { d, posts } = deps();
    await open(d);
    const box = panel().querySelector('.preview')!;
    expect(box.textContent).toContain('relationships (1). Every fact stays.');
    expect(box.textContent).toContain('hides 2 facts');
    expect(box.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked).toBe(false);
    Array.from(box.querySelectorAll('button')).find((b) => b.textContent === 'Mark not a character')!.click();
    await settle();
    expect(posts.at(-1)).toEqual([`/v1/conversations/${id}/repairs`,
      { kind: 'entity_exclude', item: e, scope: 'cast', expect: 'fp-cast' }]);
  });

  it('leaves it out of memory only when the box is ticked, previewing that scope first', async () => {
    const { d, posts } = deps();
    await open(d);
    const box = panel().querySelector('.preview')!;
    box.querySelector<HTMLInputElement>('input[type=checkbox]')!.checked = true;
    Array.from(box.querySelectorAll('button')).find((b) => b.textContent === 'Mark not a character')!.click();
    await settle();
    expect(posts.map(([p, b]) => [p, (b as { scope?: string }).scope])).toEqual([
      [`/v1/conversations/${id}/repairs/preview`, 'cast'], [`/v1/conversations/${id}/repairs/preview`, 'memory'],
      [`/v1/conversations/${id}/repairs`, 'memory']]);
    expect((posts.at(-1)![1] as { expect: string }).expect).toBe('fp-memory');
  });
});
