// @vitest-environment happy-dom
// PHASE-43 S3: a chat's status window on its Inspector page: found, tracked on confirmation, pinned, untracked.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { openPanel, type PanelDeps } from '../src/ui';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const keys = ['date', 'hp', 'place', 'items'];
const values = { date: '1214년 9월 4일', hp: '150 / 200', place: '광장', items: '물약 ×2' };

function deps(card: string | null = 'Shape test') {
  const calls: [string, string, unknown][] = [];
  const state = { tracked: false, ruleId: null as string | null, pins: [] as string[] };
  const d: PanelDeps = {
    api: async <T>(method: 'GET' | 'POST' | 'PUT', address: string, body?: unknown) => {
      const path = address.replace(/\?.*$/, '');
      calls.push([method, path, body]);
      if (path === '/v1/inspector') return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
      if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: '<p>a chat</p>' } as T;
      if (path.endsWith('/memory-mode')) throw new Error('404');
      if (path.endsWith('/status/candidates')) {
        return { card, pins: state.pins, candidates: [{ keys, count: 4, values, tracked: state.tracked,
          rule_id: state.ruleId }] } as T;
      }
      if (path === '/v1/parsers/card/track') { state.tracked = true; state.ruleId = 'card-x:1:status'; return {} as T; }
      if (path === '/v1/parsers/card/untrack') { state.tracked = false; state.ruleId = null; return {} as T; }
      if (path === '/v1/parsers/card/pins') { state.pins = (body as { keys: string[] }).keys; return {} as T; }
      return {} as T;
    },
    status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
      version: '0.4.0', features: {}, last: null }),
    getArg: async (key) => (key === 'language' ? 'en' : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => null }),
    download: async () => 0,
  };
  return { d, calls, state };
}

const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setTimeout(resolve, 0)); };
const panel = () => document.getElementById('nmos-panel')!;
const card = () => document.getElementById('nmos-status-windows')!;
const button = (text: string) => [...card().querySelectorAll('button')].find((b) => b.textContent === text)!;

async function openChat(d: PanelDeps): Promise<void> {
  await openPanel(d, 'inspector');
  await settle();
  panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!.click();
  await settle();
}

describe('status window card', () => {
  afterEach(() => { document.body.replaceChildren(); document.head.replaceChildren(); });

  it('offers a found window, tracks it on confirmation, pins keys and untracks it', async () => {
    const { d, calls } = deps();
    await openChat(d);
    expect(card().style.display).toBe('');
    expect(card().textContent).toContain('A 4-key status window · in 4 replies');
    expect(card().textContent).toContain('date: 1214년 9월 4일 · hp: 150 / 200');
    expect(calls.some(([m, p]) => m !== 'GET' && p.startsWith('/v1/parsers'))).toBe(false);  // looking configures nothing

    button('Track').click();
    await settle();
    expect(calls.find(([, p]) => p === '/v1/parsers/card/track')![2]).toEqual({ card: 'Shape test', keys });
    expect(card().textContent).toContain('Tracked · 4 keys');

    const items = [...card().querySelectorAll<HTMLInputElement>('input[type=checkbox]')].find((i) => i.value === 'items')!;
    items.checked = true;
    button('Save pins').click();
    await settle();
    expect(calls.find(([, p]) => p === '/v1/parsers/card/pins')![2]).toEqual({ card: 'Shape test', keys: ['items'] });

    button('Stop tracking').click();
    await settle();
    expect(calls.find(([, p]) => p === '/v1/parsers/card/untrack')![2]).toEqual({ card: 'Shape test', rule_id: 'card-x:1:status' });
    expect(card().textContent).toContain('A 4-key status window');
  });

  it('cannot bind without a character name, and an older sidecar shows nothing', async () => {
    const { d } = deps(null);
    await openChat(d);
    expect(card().textContent).toContain("character name is not known yet");
    expect(card().querySelectorAll('button')).toHaveLength(0);
    document.body.replaceChildren();
    const old = deps();
    const api = old.d.api;
    old.d.api = async (method, path, body, t) => {
      if (path.includes('/status/candidates')) throw new Error('404');
      return api(method, path, body, t);
    };
    await openChat(old.d);
    expect(card().style.display).toBe('none');
  });

  it('folds every card\'s rules and the hand-written rules in Settings', async () => {
    const { d } = deps();
    await openPanel(d, 'settings');
    await settle();
    const summaries = [...panel().querySelectorAll('details > summary')].map((s) => s.textContent);
    expect(summaries).toContain("Every card's status rules");
    expect(summaries).toContain('Advanced: write rules by hand (JSON)');
    expect(document.getElementById('nmos-parser-apply')!.closest('details')).not.toBeNull();
  });
});
