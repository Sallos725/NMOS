// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { openPanel, type PanelDeps } from '../src/ui';
import type { ParserPreset, ParserRule } from '../src/parser-form';

afterEach(() => { document.body.replaceChildren(); });
const rule = { id: 'hp', kind: 'regex', pattern: 'HP: (?P<value>\\d+)', key: 'HP' };
const text = JSON.stringify({ rules: [rule] });
const input = (id: string) => document.getElementById(`nmos-parser-${id}`) as HTMLInputElement;
const button = (id: string) => document.getElementById(`nmos-parser-${id}`) as HTMLButtonElement;
function enter(id: string, value: string): void {
  input(id).value = value;
  input(id).dispatchEvent(new Event('input', { bubbles: true }));
}
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function harness() {
  const calls: [string, string, unknown][] = [];
  const state = { fail: false, old: false, offline: false };
  const config = {
    llm: { url: '', model: '', api_key_set: false, json_mode: false },
    embeddings: { url: '', model: '', api_key_set: false, query_instruction: '' },
    recall: { threshold: .3, vector_min_sim: .3, top_k: 4, facts_limit: 6 }, extraction: { backfill: 20 },
    parsers: { rules: null, source: 'file', active_rules: 1, errors: [] as string[],
      spec: { rules: [{ ...rule, card: 'B' }] as ParserRule[] }, presets: [] as ParserPreset[] },
  };
  const deps: PanelDeps = {
    api: async <T>(method, path, body) => {
      calls.push([method, path, body]);
      if (method === 'GET' && path === '/v1/config' && state.offline) throw new Error('offline');
      if (method === 'PUT' && state.fail) throw new Error(`${path} -> HTTP 422: refused`);
      if (method === 'GET' && path.startsWith('/v1/conversations')) {
        return [{ host_character_name: 'A' }, { host_character_name: 'B' }] as T;
      }
      if (method === 'PUT' && path === '/v1/parsers/card') {
        const b = body as { card: string; rules: ParserRule[] };
        config.parsers.spec.rules = [...config.parsers.spec.rules.filter((r) => r.card !== b.card),
          ...b.rules.map((r) => ({ ...r, card: b.card }))];
        config.parsers.active_rules = config.parsers.spec.rules.length;
      }
      if (method === 'PUT' && path === '/v1/config' && 'parser_presets' in (body as object)) {
        config.parsers.presets = (body as { parser_presets: ParserPreset[] }).parser_presets;
      }
      if (state.old) {
        const { spec: _spec, presets: _presets, ...parsers } = config.parsers;
        return { ...config, parsers } as T;
      }
      return structuredClone(config) as T;
    },
    status: async () => ({ enabled: true, connected: true } as never),
    getArg: async (key) => key === 'language' ? 'en' : '', setArg: async () => {},
    show: async () => {}, hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: { current: async () => ({ id: null, off: false }), set: async () => ({ id: null, off: false }),
      toggle: async () => ({ id: null, off: false }) }, download: async () => 0,
  };
  return { deps, calls, state, config, writes: () => calls.filter(([method]) => method === 'PUT') };
}

describe('explicit status configuration', () => {
  it('starts blank beside active bindings; importing a file and selecting a preset do not activate either', async () => {
    const h = harness();
    h.config.parsers.presets = [{ name: 'HP', rules: [rule] }];
    await openPanel(h.deps, 'settings');
    expect([input('draft').value, input('target').value, input('preset').value]).toEqual(['', '', '']);
    expect(document.getElementById('nmos-parser-active')!.textContent).toContain('B');
    const file = new File([text], 'hp.json', { type: 'application/json' });
    Object.defineProperty(input('file'), 'files', { value: [file] });
    input('file').dispatchEvent(new Event('change', { bubbles: true }));
    await vi.waitFor(() => expect(input('draft').value).toBe(text));
    input('preset').value = 'HP';
    input('preset').dispatchEvent(new Event('change', { bubbles: true }));
    expect(JSON.parse(input('draft').value)).toEqual({ rules: [rule] });
    expect(h.writes()).toEqual([]);
    expect(button('apply').disabled).toBe(true);
  });

  it('sends only the explicit target and draft, and retains both on a rejected or unsupported apply', async () => {
    const h = harness();
    await openPanel(h.deps, 'settings');
    enter('draft', text); enter('target', 'A');
    expect(document.getElementById('nmos-parser-preview')!.textContent).toContain('A');
    h.state.fail = true;
    button('apply').click(); await settle();
    expect(input('draft').value).toBe(text);
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B']);
    h.state.fail = false;
    button('apply').click(); await settle();
    expect(h.writes().at(-1)).toEqual(['PUT', '/v1/parsers/card', { card: 'A', rules: [rule] }]);
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B', 'A']);
    enter('draft', '{'); expect(button('apply').disabled).toBe(true);
    enter('draft', ''); expect(button('apply').disabled).toBe(true);
    enter('draft', '{"rules":[]}'); button('apply').click(); await settle();
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B']);
    expect(h.writes().every(([, path]) => path === '/v1/parsers/card')).toBe(true);
  });

  it('keeps general Save and Save-and-close from applying or overwriting a status draft', async () => {
    const h = harness();
    await openPanel(h.deps, 'settings');
    enter('draft', text); enter('target', 'A');
    const threshold = [...document.querySelectorAll<HTMLInputElement>('input')].find((i) => i.value === '0.3')!;
    threshold.value = '0.4'; threshold.dispatchEvent(new Event('input', { bubbles: true }));
    (document.querySelector('.bar button.primary') as HTMLButtonElement).click(); await settle();
    expect(h.writes()).toHaveLength(1);
    expect(h.writes()[0]![2]).not.toHaveProperty('parsers');
    expect(input('draft').value).toBe(text);
    [...document.querySelectorAll('button')].find((b) => b.textContent === 'Close')!.click();
    expect(document.querySelector('.bar')!.textContent).toContain('status');
    expect([...document.querySelectorAll('button')].some((b) => b.textContent === 'Save and close')).toBe(false);
    expect(h.writes()).toHaveLength(1);
  });

  it('saves, reloads and removes presets separately from active rules', async () => {
    const h = harness();
    await openPanel(h.deps, 'settings');
    enter('draft', JSON.stringify({ rules: [{ ...rule, card: 'Old' }] })); enter('name', 'HP');
    button('save-preset').click(); await settle();
    expect(h.writes()).toEqual([['PUT', '/v1/config', { parser_presets: [{ name: 'HP', rules: [rule] }] }]]);
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B']);
    document.body.replaceChildren(); await openPanel(h.deps, 'settings');
    expect(input('preset').value).toBe('');
    input('preset').value = 'HP'; input('preset').dispatchEvent(new Event('change', { bubbles: true }));
    expect(JSON.parse(input('draft').value)).toEqual({ rules: [rule] });
    button('remove-preset').click(); await settle();
    expect(h.writes().at(-1)).toEqual(['PUT', '/v1/config', { parser_presets: [] }]);
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B']);
  });

  it('does not fall back to a global write on an older sidecar', async () => {
    const h = harness(); h.state.old = true;
    await openPanel(h.deps, 'settings');
    enter('target', 'A'); enter('draft', text);
    expect(button('apply').disabled).toBe(true);
    expect(document.getElementById('nmos-parser-active')!.textContent).toContain('Update');
    expect(h.writes()).toEqual([]);
  });

  it('keeps the preset library and draft when saving the library fails', async () => {
    const h = harness();
    h.config.parsers.presets = [{ name: 'Existing', rules: [rule] }];
    await openPanel(h.deps, 'settings');
    enter('draft', text); enter('name', 'New'); enter('target', 'A');
    h.state.fail = true;
    button('save-preset').click(); await settle();
    expect(h.config.parsers.presets.map((p) => p.name)).toEqual(['Existing']);
    expect(input('draft').value).toBe(text);
    expect(input('name').value).toBe('New');
    expect(input('target').value).toBe('A');
    expect(h.config.parsers.spec.rules.map((r) => r.card)).toEqual(['B']);
    expect(h.writes().every(([, path, body]) => path === '/v1/config'
      && !Object.hasOwn(body as object, 'parsers'))).toBe(true);
  });

  it('refreshes status configuration after the first connection is saved without reopening the panel', async () => {
    const h = harness(); h.state.offline = true;
    await openPanel(h.deps, 'settings');
    enter('draft', text); enter('target', 'A');
    expect(button('apply').disabled).toBe(true);
    h.state.offline = false;
    const address = document.querySelector<HTMLInputElement>('input[spellcheck="false"]')!;
    address.value = 'http://localhost:8842'; address.dispatchEvent(new Event('input', { bubbles: true }));
    (document.querySelector('.bar button.primary') as HTMLButtonElement).click();
    await vi.waitFor(() => expect(button('apply').disabled).toBe(false));
    expect(input('draft').value).toBe(text);
    expect(input('target').value).toBe('A');
    expect(h.writes()).toEqual([]);
    expect(document.getElementById('nmos-parser-active')!.textContent).toContain('B');
  });

  it('does not keep the previous sidecar enabled when refreshing a changed connection fails', async () => {
    const h = harness();
    await openPanel(h.deps, 'settings');
    enter('draft', text); enter('target', 'A');
    expect(button('apply').disabled).toBe(false);
    h.state.offline = true;
    const address = document.querySelector<HTMLInputElement>('input[spellcheck="false"]')!;
    address.value = 'http://localhost:8843'; address.dispatchEvent(new Event('input', { bubbles: true }));
    (document.querySelector('.bar button.primary') as HTMLButtonElement).click(); await settle();
    expect(button('apply').disabled).toBe(true);
    expect(input('draft').value).toBe(text);
    expect(input('target').value).toBe('A');
    expect(h.writes()).toEqual([]);
  });

});
