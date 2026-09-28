// @vitest-environment happy-dom
// DOM code (audit follow-up, 2026-09-27 review): the inspector sanitizer's tree walk and the settings panel.
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StatusInfo } from '../src/core';
import { safeFragment } from '../src/inspector';
import { openPanel, type PanelDeps } from '../src/ui';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const ran = globalThis as { __ran?: boolean };

function html(fragment: DocumentFragment): string {
  const div = document.createElement('div');
  div.append(fragment);
  return div.innerHTML;
}

describe('safeFragment', () => {
  it('keeps the inspector markup and drops every element and attribute that could run or load', () => {
    ran.__ran = false;
    const out = html(safeFragment(
      `<div class="card" onclick="__ran=true" style="color:red"><h2 id="s-facts" title="t">Facts</h2>`
      + '<script>__ran=true</script><img src="x" onerror="__ran=true"><iframe src="https://example.com"></iframe>'
      + `<a href="javascript:__ran=true">bad</a><a href="/inspector/c/${id}?token=x">ok</a><a href="#s-facts">jump</a>`
      + '<details open><summary>more</summary><table><tbody><tr><td>cell<b>bold</b></td></tr></tbody></table></details>'
      + '<svg><a href="#s-facts">svg</a></svg><!-- note --><form><input name="x"></form><p id="nmos-panel">text<br></p></div>'));
    expect(out).toBe('<div class="card"><h2 id="s-facts" title="t">Facts</h2>'
      + `<a>bad</a><a href="/inspector/c/${id}?token=x">ok</a><a href="#s-facts">jump</a>`
      + '<details open=""><summary>more</summary><table><tbody><tr><td>cell<b>bold</b></td></tr></tbody></table></details>'
      + '<p>text<br></p></div>');
    expect(ran.__ran).toBe(false);
  });

  it('keeps text as text', () => {
    const out = safeFragment('<p>&lt;script&gt;__ran=true&lt;/script&gt; &amp; more</p>');
    expect(out.textContent).toBe('<script>__ran=true</script> & more');
    expect(out.querySelector('script')).toBeNull();
  });
});

describe('panel', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  const config = {
    llm: { url: 'https://llm.example/v1', model: 'm', api_key_set: true, json_mode: true },
    embeddings: { url: '', model: '', api_key_set: false, query_instruction: '' },
    recall: { threshold: 0.3, vector_min_sim: 0.3, top_k: 4, facts_limit: 6 },
    extraction: { backfill: 20 },
    parsers: { rules: null, source: 'none', active_rules: 0, errors: [] as string[] },
  };

  function deps(status: Partial<StatusInfo> = {}) {
    const calls: [string, string, unknown][] = [];
    const args: Record<string, string> = { sidecar_url: 'http://127.0.0.1:8790', language: 'en' };
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown) => {
        calls.push([method, path, body]);
        return (method === 'PUT' ? { ...config, queued_jobs: 0 } : config) as T;
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.1.0b21', features: { extraction: true }, last: null, ...status }),
      getArg: async (key) => args[key] ?? '',
      setArg: async (key, value) => { args[key] = String(value); },
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    };
    return { d, calls, args };
  }

  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('shows the sidecar status', async () => {
    const { d } = deps();
    await openPanel(d, 'status');
    await settle();
    const text = document.getElementById('nmos-panel')!.textContent ?? '';
    expect(text).toContain('0.1.0b21');
    expect(text).toContain('http://127.0.0.1:8790');
  });

  it('loads the settings and saves one sidecar update for the section that changed', async () => {
    const { d, calls, args } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const endpoint = [...panel.querySelectorAll('input')].find((i) => i.value === 'https://llm.example/v1')!;
    expect(endpoint).toBeDefined();
    endpoint.value = 'https://llm.example/v2';
    endpoint.dispatchEvent(new Event('input', { bubbles: true }));
    const reserved = [...panel.querySelectorAll('input')].find((i) => i.value === '2000')!;
    reserved.value = '99999';
    reserved.dispatchEvent(new Event('input', { bubbles: true }));
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    expect(calls.filter(([method]) => method === 'PUT')).toEqual([['PUT', '/v1/config',
      { llm_url: 'https://llm.example/v2', llm_model: 'm' }]]);  // no key typed: none sent
    expect(args.reserved_memory_tokens).toBe('20000');
  });

  it('turns summaries off from the settings (ADR 0042, 0043)', async () => {
    const { d, calls } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const label = [...panel.querySelectorAll('.check')].find((c) => c.textContent === 'Scene summaries')!;
    const box = label.querySelector('input') as HTMLInputElement;
    expect(box.checked).toBe(true);  // the settings response has no `summaries`: on, the sidecar's default
    box.checked = false;
    box.dispatchEvent(new Event('change', { bubbles: true }));
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    const put = calls.find(([method]) => method === 'PUT')!;
    expect((put[2] as Record<string, unknown>).summaries).toBe(false);
  });
});

describe('owner repairs in the panel (ADR 0044)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  const t1 = '0190f3a4-0000-7000-8000-000000000001';
  const t2 = '0190f3a4-0000-7000-8000-000000000002';
  const who = '5c6d7e8f-9a0b-5c2d-8e3f-0123456789ab';
  const mark = (value: string) => `<span class="rp" data-repair="${value}"></span>`;
  const chat = `<details id="s-threads" open><summary>Threads</summary><table>`
    + `<tr><td>a goal</td><td>open ${mark(`thread_close:${t1}:achieved,abandoned`)}</td></tr>`
    + `<tr><td>a promise</td><td>open ${mark(`thread_close:${t2}:kept,broken`)}</td></tr>`
    + `<tr><td>a plan</td><td>closed ${mark('thread_reopen:-4')}</td></tr></table></details>`
    + `<p>a secret ${mark('secret_found_out:12:하나')}</p><p>a fact ${mark('fact_correct:42:object')}</p>`
    + `<p>a repair ${mark(`undo:${t1}`)}</p><p>forged ${mark('name_split:1:x')}<span class="rp" data-repair="x"></span></p>`;

  function deps(entities: unknown[] = []) {
    const calls: [string, string, unknown][] = [];
    let fail = false;
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT', address: string, body?: unknown) => {
        const path = address.replace(/\?lang=en$/, '');
        calls.push([method, path, body]);
        if (method === 'POST' && fail) throw new Error('422 already closed');
        if (path === '/v1/inspector') return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
        if (path.startsWith(`/v1/inspector/c/${id}/e/`)) return { html: '<p>a character</p>' } as T;
        if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: chat } as T;
        if (path.endsWith('/entities')) return entities as T;
        if (path.endsWith('/memory-mode')) throw new Error('404');
        return {} as T;
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.1.0b21', features: {}, last: null }),
      getArg: async (key) => (key === 'language' ? 'en' : ''),
      setArg: async () => {},
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    };
    return { d, calls, failPosts: () => { fail = true; } };
  }

  const settle = async () => { for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0)); };
  const panel = () => document.getElementById('nmos-panel')!;
  const button = (text: string) => [...panel().querySelectorAll('button')].find((b) => b.textContent === text)!;
  const posts = (calls: [string, string, unknown][]) => calls.filter(([method]) => method === 'POST');

  async function openChat(d: PanelDeps, path = `/inspector/c/${id}`): Promise<void> {
    await openPanel(d, 'inspector');
    await settle();
    const link = panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!;
    if (path !== link.getAttribute('href')) link.setAttribute('href', path);
    link.click();
    await settle();
  }

  it('puts a button on each line the page marks and posts that repair', async () => {
    const { d, calls } = deps();
    await openChat(d);
    const spots = [...panel().querySelectorAll('span.rp[data-repair]')];
    expect(spots.map((s) => s.getAttribute('data-repair'))).toEqual(
      [`thread_close:${t1}:achieved,abandoned`, `thread_close:${t2}:kept,broken`, 'thread_reopen:-4', 'secret_found_out:12:하나', 'fact_correct:42:object',
        `undo:${t1}`]); // a mark the panel does not know is dropped with the attribute
    expect(spots.every((s) => s.querySelector('button'))).toBe(true);
    expect(panel().querySelectorAll('span.rp:not([data-repair]) button')).toHaveLength(0);
    expect(button('Reopen')).toBeDefined();
    button('하나: found out').click();
    await settle();
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs`,
      { kind: 'secret_found_out', item: '12', character: '하나' }]]);
    expect(panel().textContent).toContain('Fixed.');
    button('Undo').click();
    await settle();
    expect(posts(calls)[1]).toEqual(['POST', `/v1/conversations/${id}/repairs/${t1}/remove`, {}]);
  });

  it('asks for the new object of a correction, and posts nothing when the owner cancels', async () => {
    const { d, calls } = deps();
    await openChat(d);
    const answers = ['', '  유이  '];
    vi.spyOn(window, 'prompt').mockImplementation(() => answers.shift() ?? null);
    button('Correct').click();
    await settle();
    expect(posts(calls)).toEqual([]);
    button('Correct').click();
    await settle();
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs`,
      { kind: 'fact_correct', item: '42', new_object: '유이' }]]);
  });

  it('closes the picked threads together, and says why when the sidecar refuses', async () => {
    const { d, calls, failPosts } = deps();
    await openChat(d);
    const boxes = [...panel().querySelectorAll<HTMLInputElement>('span.rp input[type="checkbox"]')];
    expect(boxes).toHaveLength(2); // only open threads can be picked
    expect(button('Close 0 selected threads')?.closest<HTMLElement>('.btns')?.style.display).toBe('none');
    for (const box of boxes) {
      box.checked = true;
      box.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const outcome = panel().querySelector<HTMLSelectElement>(`span.rp[data-repair^="thread_close:${t2}"] select`)!;
    expect([...outcome.options].map((o) => o.textContent)).toEqual(['kept', 'broken']);
    outcome.value = 'broken'; // chosen after the box was ticked: the bulk close still uses it
    button('Close 2 selected threads').click();
    await settle();
    expect(posts(calls).map(([, , body]) => body)).toEqual([{ kind: 'thread_close', item: t1, outcome: 'achieved' },
      { kind: 'thread_close', item: t2, outcome: 'broken' }]);
    expect(panel().textContent).toContain('Closed 2 threads.');
    failPosts();
    const close = panel().querySelector<HTMLButtonElement>(`span.rp[data-repair^="thread_close:${t1}"] button`)!;
    close.click();
    await settle();
    expect(panel().textContent).toContain('422 already closed');
    expect(close.disabled).toBe(false);
  });

  it('splits two names the story joined on the entity page (K8)', async () => {
    const hana = { id: who, type: 'character', name: '하나', names: ['하나', '유이'], mentions: 9, links: [],
      aliases: [{ name: '하나', other: '유이', turn: 3 }] };
    const { d, calls } = deps([hana, { id: t2, type: 'character', name: '카이토', names: ['카이토'], mentions: 4, links: [] }]);
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    expect(panel().textContent).toContain('하나 ~ 유이');
    button('Split').click();
    await settle();
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs`,
      { kind: 'name_split', item: '하나', other: '유이', entity_type: 'character' }]]);
    expect(panel().textContent).toContain('Split "하나" and "유이".');
  });
});
