// @vitest-environment happy-dom
// DOM code (audit follow-up, 2026-09-27 review): the inspector sanitizer's tree walk and the settings panel.
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StatusInfo } from '../src/core';
import { createChatSwitch } from '../src/chatoff';
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
    const open: { chat: string | null } = { chat: 'chat-1' };
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
      chat: createChatSwitch({ getArg: async (key) => args[key] ?? '', setArg: async (key, value) => { args[key] = value; },
        currentChatId: async () => open.chat }),
      download: async (path, name) => {
        calls.push(['DOWNLOAD', path, name]);
        if (args.refuse_export) throw new Error('/v1/archive -> HTTP 409: a row holds a credential');
        return 3 * 1_048_576;
      },
    };
    return { d, calls, args, open };
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

  it('shows this chat first and switches NMOS off and back on for it (ADR 0048)', async () => {
    const { d, args } = deps();
    args.disabled_chats = 'chat-0';
    await openPanel(d, 'status');
    await settle();
    const panel = document.getElementById('nmos-panel')!;
    const first = () => panel.querySelector('.card')!;
    const flip = () => first().querySelector('button') as HTMLButtonElement;
    expect(first().textContent).toContain('This chat');
    expect(first().textContent).toContain('NMOS on');
    expect(flip().textContent).toBe('Turn off for this chat');
    flip().click();
    await vi.waitFor(() => expect(first().textContent).toContain('NMOS off'));
    expect(args.disabled_chats).toBe('chat-0 chat-1');
    expect(flip().textContent).toBe('Turn back on for this chat');
    flip().click();
    await vi.waitFor(() => expect(first().textContent).toContain('NMOS on'));
    expect(args.disabled_chats).toBe('chat-0');
  });

  it("says in this chat's card what its memory cost in NMOS's model calls (PHASE-17 Q4)", async () => {
    const { d, calls } = deps();
    const total = { calls: 12, reported: 12, input: 48210, output: 3105, cached: 0 };
    d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string) => {
      calls.push([method, path, undefined]);
      if (path === '/v1/conversations?host=pocketrisu&host_chat_ref=chat-1') return [{ id: 'conv-9', host_chat_ref: 'chat-1' }] as T;
      if (path.startsWith('/v1/conversations/conv-9/coverage')) return { usage: { total } } as T;
      return config as T;
    };
    await openPanel(d, 'status');
    await vi.waitFor(() => expect(document.querySelector('#nmos-panel .card')!.textContent)
      .toContain('NMOS model use: 12 calls · 48,210 input · 3,105 output tokens'));
    expect(calls.map((c) => c[1])).toContain('/v1/conversations/conv-9/coverage?usage=true');
  });

  it("counts in this chat's card the facts a re-extraction dropped, and says nothing for none (PHASE-22 Q6)", async () => {
    for (const dropped of [3, 0]) {
      document.body.replaceChildren();
      const { d } = deps();
      const total = { calls: 12, reported: 12, input: 48210, output: 3105, cached: 0 };
      d.api = async <T>(_method: 'GET' | 'POST' | 'PUT', path: string) => {
        if (path === '/v1/conversations?host=pocketrisu&host_chat_ref=chat-1') return [{ id: 'conv-9', host_chat_ref: 'chat-1' }] as T;
        if (path.startsWith('/v1/conversations/conv-9/coverage')) return { usage: { total }, dropped } as T;
        return config as T;
      };
      await openPanel(d, 'status');
      const card = () => document.querySelector('#nmos-panel .card')!.textContent ?? '';
      await vi.waitFor(() => expect(card()).toContain('NMOS model use: 12 calls'));
      if (dropped) expect(card()).toContain('3 facts dropped by a re-extraction');
      else expect(card()).not.toContain('dropped by a re-extraction');
    }
  });

  it('leaves the usage line out when the sidecar does not know the chat', async () => {
    const { d } = deps();
    d.api = async <T>(_method: 'GET' | 'POST' | 'PUT', path: string) =>
      (path.startsWith('/v1/conversations?') ? [] : config) as T;
    await openPanel(d, 'status');
    await settle();
    await vi.waitFor(() => expect(document.querySelector('#nmos-panel .card')!.textContent).toContain('NMOS on'));
    expect(document.querySelector('#nmos-panel .card')!.textContent).not.toContain('NMOS model use');
  });

  it('draws this chat first and adds the usage line when it comes (Copilot review)', async () => {
    const { d } = deps();
    let answer: (v: unknown) => void = () => {};
    d.api = <T>(_method: 'GET' | 'POST' | 'PUT', path: string) => (path.startsWith('/v1/conversations?')
      ? new Promise<T>((resolve) => { answer = resolve as (v: unknown) => void; }) : Promise.resolve(config as T));
    await openPanel(d, 'status');
    const card = () => document.querySelector('#nmos-panel .card')!;
    await vi.waitFor(() => expect(card().textContent).toContain('NMOS on'));  // not held back by the slow sidecar
    expect(card().textContent).not.toContain('NMOS model use');
    answer([]);
  });

  it('says when NMOS is off for every chat', async () => {
    const { d } = deps({ enabled: false });
    await openPanel(d, 'status');
    await settle();
    const first = document.getElementById('nmos-panel')!.querySelector('.card')!;
    expect(first.textContent).toContain('NMOS is off for every chat');
  });

  it('says when the last request recalled without vectors (PHASE-15 Q5, K34)', async () => {
    const last = { at: Date.now(), ms: 900, packetChars: 10, packet: 'x', outcome: 'injected' as const, deadlineMs: 3000 };
    for (const [vectors, shown] of [['fallback', true], ['on', false], [null, false]] as const) {
      const { d } = deps({ last: { ...last, vectors } });
      await openPanel(d, 'status');
      await settle();
      const text = document.getElementById('nmos-panel')!.textContent!;
      expect(text.includes('Memory was recalled without semantic search')).toBe(shown);
      if (shown) expect(text).toContain('NMOS_EMBED_TIMEOUT_MS');
      document.getElementById('nmos-panel')?.remove();
    }
  });

  it('says when no chat is open', async () => {
    const { d, open } = deps();
    open.chat = null;
    await openPanel(d, 'status');
    await settle();
    const first = document.getElementById('nmos-panel')!.querySelector('.card')!;
    expect(first.textContent).toContain('No chat is open');
    expect(first.querySelector('button')).toBeNull();
  });

  it('loads the settings and saves one sidecar update for the section that changed', async () => {
    const { d, calls, args } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const endpoint = [...panel.querySelectorAll('input')].find((i) => i.value === 'https://llm.example/v1')!;
    expect(endpoint).toBeDefined();
    endpoint.value = 'https://llm.example/v2';
    endpoint.dispatchEvent(new Event('input', { bubbles: true }));
    const reserved = [...panel.querySelectorAll('input')].find((i) => i.value === '4000')!;
    reserved.value = '99999';
    reserved.dispatchEvent(new Event('input', { bubbles: true }));
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    expect(calls.filter(([method]) => method === 'PUT')).toEqual([['PUT', '/v1/config',
      { llm_url: 'https://llm.example/v2', llm_model: 'm' }]]);  // no key typed: none sent
    expect(args.reserved_memory_tokens).toBe('8000');  // the panel saves up to 8,000 (ADR 0049)
    expect(reserved.value).toBe('8000');  // and shows what it stored (Phase 15 real-host smoke)
  });

  it("fills an embedding preset's endpoint, model and its own similarity bar (AGE-40)", async () => {
    const { d, calls } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const pick = [...panel.querySelectorAll('select')].find((s) => [...s.options].some((o) => o.text === 'Voyage AI'))!;
    const bar = panel.querySelector<HTMLInputElement>('input[type="number"][step="0.01"]')!;
    const choose = (text: string) => {
      pick.value = String([...pick.options].findIndex((o) => o.text === text));
      pick.dispatchEvent(new Event('change', { bubbles: true }));
    };
    expect(bar.value).toBe('0.3');  // as saved
    choose('Ollama (this PC)');
    expect(bar.value).toBe('0.42');
    choose('OpenAI');  // a preset nobody measured leaves the bar as it is
    expect(bar.value).toBe('0.42');
    choose('Voyage AI');
    expect(bar.value).toBe('0.3');
    expect(pick.closest('.card')!.querySelector('.msg')!.textContent).toContain('3 requests a minute');
    choose('Ollama (this PC)');
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    expect(calls.filter(([method]) => method === 'PUT').at(-1)![2]).toMatchObject({
      embed_url: 'http://host.docker.internal:11434/v1', embed_model: 'qwen3-embedding:0.6b', vector_min_sim: 0.42 });
  });

  it('exports everything from the settings, with embeddings when asked, and says what it saved (ADR 0050)', async () => {
    const { d, calls, args } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const exportAll = [...panel.querySelectorAll('button')].find((b) => b.textContent === 'Export everything')!;
    exportAll.click();
    await settle();
    const downloads = () => calls.filter(([kind]) => kind === 'DOWNLOAD');
    expect(downloads()[0]?.[1]).toBe('/v1/archive');
    expect(downloads()[0]?.[2]).toMatch(/^nmos-all-\d{8}-\d{6}\.nmos\.zip$/);
    expect(panel.textContent).toContain('Saved 3.0 MB.');
    const label = [...panel.querySelectorAll('.check')].find((c) => c.textContent?.startsWith('Include embeddings'))!;
    (label.querySelector('input') as HTMLInputElement).checked = true;
    args.refuse_export = '1';
    exportAll.click();
    await settle();
    expect(downloads()[1]?.[1]).toBe('/v1/archive?embeddings=true');
    expect(panel.textContent).toContain('a row holds a credential');
    expect(exportAll.disabled).toBe(false);
    expect(calls.filter(([method]) => method === 'PUT')).toEqual([]);  // not a setting: nothing saved
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

  it('turns canon facts off from the settings (ADR 0047)', async () => {
    const { d, calls } = deps();
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const label = [...panel.querySelectorAll('.check')].find((c) => c.textContent === 'Facts from canon')!;
    const box = label.querySelector('input') as HTMLInputElement;
    expect(box.checked).toBe(true);  // absent from the settings response: on, the sidecar's default
    box.checked = false;
    box.dispatchEvent(new Event('change', { bubbles: true }));
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    const put = calls.find(([method]) => method === 'PUT')!;
    expect((put[2] as Record<string, unknown>).canon_facts).toBe(false);
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
  const hana = encodeURIComponent('하나');
  const goal = `<tr><td>a goal</td><td>open ${mark(`thread_close:${t1}:achieved,abandoned`)}</td></tr>`;
  const promise = `<tr><td>a promise</td><td>open ${mark(`thread_close:${t2}:kept,broken`)}</td></tr>`;
  const page = (threads: string) => `<details id="s-attention" open><summary>Needs attention</summary><table>`
    + `<tr><td>open for more than 30 turns</td><td>${mark(`thread_close:${t2}:kept,broken`)}</td></tr></table></details>`
    + `<details id="s-threads" open><summary>Threads</summary><table>${threads}`
    + `<tr><td>a plan</td><td>closed ${mark('thread_reopen:-4')}</td></tr></table></details>`
    + `<p>a secret ${mark(`secret_found_out:12:${hana}`)}</p>`
    + `<p>a fact ${mark('fact_correct:42:object')}${mark('fact_correct:42:value')}</p>`
    + `<p>a repair ${mark(`undo:${t1}`)}</p><p>forged ${mark('name_split:1:x')}${mark('secret_keep:1:하나')}</p>`;

  function deps(entities: unknown[] = []) {
    const calls: [string, string, unknown][] = [];
    const state = { html: page(goal + promise), refuse: new Set<string>(), stale: 0, turns: 0, failReextract: 0,
      hold: null as Promise<void> | null };
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT', address: string, body?: unknown) => {
        const path = address.replace(/\?lang=en$/, '');
        calls.push([method, path, body]);
        const item = (body as { item?: string } | undefined)?.item;
        if (method === 'POST' && (state.refuse.has('*') || (item && state.refuse.has(item)))) {
          throw new Error('422 already closed');
        }
        if (path === '/v1/inspector') return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
        if (path.startsWith(`/v1/inspector/c/${id}/e/`)) return { html: '<p>a character</p>' } as T;
        if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: state.html } as T;
        if (path.endsWith('/entities')) return entities as T;
        if (path.endsWith('/memory-mode')) throw new Error('404');
        if (path.endsWith('/preview')) {  // PHASE-20: one fingerprint per preview asked
          const n = calls.filter(([, p]) => p.endsWith('/preview')).length;
          if (state.hold) await state.hold;  // an answer that arrives late
          const one = [{ id: 'a', name: '하나', names: ['하나', '유이'], persona: false }];
          const two = [{ id: 'a', name: '하나', names: ['하나'], persona: false }, { id: 'b', name: '유이', names: ['유이'],
            persona: false }];
          const undo = path.endsWith('/remove/preview');
          return { action: undo ? 'unlink' : 'join', changes: true, before: undo ? one : two, after: undo ? two : one,
            lines: [{ kind: 'fact_replaced', fact: { text: '하나 at chapel' }, by: { text: '유이 at harbor', turn: 2 } }],
            counts: {}, fingerprint: `fp${n}`,
            ...(state.turns ? { reextract: { turns: state.turns, list: [4, 5].slice(0, state.turns) } } : {}) } as T;
        }
        if (state.stale > 0 && (body as { expect?: string } | undefined)?.expect) {
          state.stale -= 1;
          throw new Error(`${path} -> HTTP 409: [object Object]`);
        }
        if (path.endsWith('/reextract')) {
          if (state.failReextract > 0) { state.failReextract -= 1; throw new Error(`${path} -> HTTP 409: fact extraction is off`); }
          return { turns: (body as { turns?: number[] }).turns ?? [4, 5] } as T;
        }
        return {} as T;
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.1.0b21', features: {}, last: null }),
      getArg: async (key) => (key === 'language' ? 'en' : ''),
      setArg: async () => {},
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
      chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => null }),
      download: async (path, name) => { calls.push(['DOWNLOAD', path, name]); return 524_288; },
    };
    return { d, calls, state };
  }

  const settle = async () => { for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setTimeout(resolve, 0)); };
  const panel = () => document.getElementById('nmos-panel')!;
  const button = (text: string) => [...panel().querySelectorAll('button')].find((b) => b.textContent === text)!;
  const posts = (calls: [string, string, unknown][]) => calls.filter(([method]) => method === 'POST');
  const closeOf = (item: string) => [...panel().querySelectorAll(`span.rp[data-repair^="thread_close:${item}:"]`)];

  async function openChat(d: PanelDeps, path = `/inspector/c/${id}`): Promise<void> {
    await openPanel(d, 'inspector');
    await settle();
    const link = panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!;
    if (path !== link.getAttribute('href')) link.setAttribute('href', path);
    link.click();
    await settle();
  }

  it('exports the chat on its page (ADR 0050)', async () => {
    const { d, calls } = deps();
    await openChat(d);
    button('Export this chat').click();
    await settle();
    const [, path, name] = calls.find(([kind]) => kind === 'DOWNLOAD')!;
    expect(path).toBe(`/v1/archive?conversation=${id}`);
    expect(name).toMatch(/^nmos-chat-\d{8}-\d{6}\.nmos\.zip$/);
    expect(panel().textContent).toContain('Saved 0.5 MB.');
  });

  it('puts a button on each line the page marks and posts that repair', async () => {
    const { d, calls } = deps();
    await openChat(d);
    const spots = [...panel().querySelectorAll('span.rp[data-repair]')];
    expect(spots.map((s) => s.getAttribute('data-repair'))).toEqual([`thread_close:${t2}:kept,broken`,
      `thread_close:${t1}:achieved,abandoned`, `thread_close:${t2}:kept,broken`, 'thread_reopen:-4',
      `secret_found_out:12:${hana}`, 'fact_correct:42:object', 'fact_correct:42:value', `undo:${t1}`]);
    expect(spots.every((s) => s.querySelector('button'))).toBe(true);
    // a mark the panel does not know, or a name not encoded, is dropped with the attribute
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

  it('corrects a fact in a form with the new value and the turn it takes effect (PHASE-13 Q5)', async () => {
    const { d, calls } = deps();
    await openChat(d);
    button('Correct value').click();
    const form = panel().querySelector('span.rpform')!;
    const [text, turn] = [...form.querySelectorAll('input')];
    button('Save').click(); // nothing typed: nothing posted
    turn!.value = '-1';
    text!.value = '  친구  ';
    button('Save').click();
    await settle();
    expect(posts(calls)).toEqual([]);
    expect(panel().textContent).toContain('A turn is a whole number');
    turn!.value = '7';
    button('Save').click();
    await settle();
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs`,
      { kind: 'fact_correct', item: '42', new_value: '친구', turn: 7 }]]);
    button('Correct object').click();
    button('Cancel').click();
    expect(button('Correct object')).toBeDefined(); // the button is back, nothing posted
    expect(posts(calls)).toHaveLength(1);
  });

  it('keeps the controls of a thread shown twice in step, and closes the picked threads with their outcomes', async () => {
    const { d, calls, state } = deps();
    await openChat(d);
    const [attention, listed] = closeOf(t2);
    const outcome = (spot: Element | undefined) => spot!.querySelector('select')!;
    const box = (spot: Element | undefined) => spot!.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect([...outcome(listed).options].map((o) => o.textContent)).toEqual(['kept', 'broken']);
    outcome(attention).value = 'broken';
    outcome(attention).dispatchEvent(new Event('change', { bubbles: true }));
    expect(outcome(listed).value).toBe('broken');
    box(listed).checked = true;
    box(listed).dispatchEvent(new Event('change', { bubbles: true }));
    expect(box(attention).checked).toBe(true);
    box(closeOf(t1)[0]).checked = true;
    box(closeOf(t1)[0]).dispatchEvent(new Event('change', { bubbles: true }));
    state.refuse.add(t1); // one refusal does not stop the others
    button('Close 2 selected threads').click();
    await settle();
    expect(posts(calls).map(([, , body]) => body)).toEqual([{ kind: 'thread_close', item: t2, outcome: 'broken' },
      { kind: 'thread_close', item: t1, outcome: 'achieved' }]);
    expect(panel().textContent).toContain('Closed 1 threads. 1 could not be closed: ');
    expect(panel().textContent).toContain('422 already closed');
    expect(button('Close 1 selected threads')).toBeDefined(); // the refused one stays picked
    state.html = page(promise); // closed elsewhere: gone from the page
    button('Refresh').click();
    await settle();
    expect(button('Close 0 selected threads')?.closest<HTMLElement>('.btns')?.style.display).toBe('none');
  });

  it('keeps the outcome picked for a thread through a refresh, and reports a refused close', async () => {
    const { d, calls, state } = deps();
    await openChat(d);
    const select = closeOf(t2)[1]!.querySelector('select')!;
    select.value = 'broken';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    button('Refresh').click();
    await settle();
    expect(closeOf(t2).map((s) => s.querySelector('select')!.value)).toEqual(['broken', 'broken']);
    state.refuse.add('*');
    const close = closeOf(t1)[0]!.querySelector('button')!;
    close.click();
    await settle();
    expect(posts(calls).map(([, , body]) => body)).toEqual([{ kind: 'thread_close', item: t1, outcome: 'achieved' }]);
    expect(panel().textContent).toContain('422 already closed');
    expect(close.disabled).toBe(false);
  });

  it('splits two names the story joined on the entity page (K8)', async () => {
    const hanaRow = { id: who, type: 'character', name: '하나', names: ['하나', '유이'], mentions: 9, links: [],
      aliases: [{ name: '하나', other: '유이', turn: 3 }] };
    const { d, calls } = deps([hanaRow, { id: t2, type: 'character', name: '카이토', names: ['카이토'], mentions: 4, links: [] }]);
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    expect(panel().textContent).toContain('하나 ~ 유이');
    button('Split').click();
    await settle();
    const body = { kind: 'name_split', item: '하나', other: '유이', entity_type: 'character' };
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs/preview`, body]]);  // shown first (PHASE-20)
    expect(panel().textContent).toContain('"유이 at harbor" replaces "하나 at chapel" (turn 2)');
    button('Split as shown').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs`, { ...body, expect: 'fp1' }]);
    expect(panel().textContent).toContain('Split "하나" and "유이".');
  });

  const joinable = () => [
    { id: who, type: 'character', name: '하나', names: ['하나'], mentions: 9, links: [], aliases: [] },
    { id: t2, type: 'character', name: '유이', names: ['유이'], mentions: 4, links: [] }];

  it('previews a join, and shows the new preview when memory changed since (PHASE-20 Q4)', async () => {
    const { d, calls, state } = deps(joinable());
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    button('Join').click();
    await settle();
    expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/entity-links/preview`,
      { entity_type: 'character', name: '하나', same_as: '유이' }]]);
    expect(panel().textContent).toContain('하나, 유이 → 하나');
    state.stale = 1;
    button('Join as shown').click();
    await settle();
    await settle();
    expect(panel().textContent).toContain('Memory changed since the preview');
    button('Join as shown').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/entity-links`,
      { entity_type: 'character', name: '하나', same_as: '유이', expect: 'fp2' }]);
    expect(panel().textContent).toContain('Joined "하나" and "유이".');
  });

  it('cancels a preview without writing anything', async () => {
    const { d, calls } = deps(joinable());
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    button('Join').click();
    await settle();
    button('Cancel').click();
    await settle();
    expect(posts(calls).map(([, p]) => p)).toEqual([`/v1/conversations/${id}/entity-links/preview`]);
    expect(button('Join')?.disabled).toBe(false);
  });

  it('undoes a join and re-extracts the turns it covered only when asked (Q7)', async () => {
    const link = '0190f3a4-1b2c-7d3e-8f40-00000000beef';
    const rows = joinable();
    rows[0] = { ...rows[0]!, names: ['하나', '유이'], links: [{ id: link, name: '하나', same_as: '유이' }] } as typeof rows[0];
    const { d, calls, state } = deps(rows);
    state.turns = 2;
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    button('Undo').click();
    await settle();
    expect(panel().textContent).toContain('Re-extract the 2 turns extracted while joined');
    const box = panel().querySelector<HTMLInputElement>('.preview input[type=checkbox]')!;
    expect(box.checked).toBe(false);  // off by default: it costs model calls
    box.checked = true;
    button('Undo as shown').click();
    await settle();
    await settle();
    const base = `/v1/conversations/${id}/entity-links/${link}`;
    expect(posts(calls).map(([, p, b]) => [p, b])).toEqual([[`${base}/remove/preview`, {}],
      [`${base}/remove`, { expect: 'fp1' }], [`${base}/reextract`, { turns: [4, 5] }]]);  // only the turns shown
    expect(panel().textContent).toContain('Queued 2 turns for re-extraction.');
  });

  it('keeps an undo made when its re-extraction fails, and offers to retry only the re-extraction', async () => {
    const link = '0190f3a4-1b2c-7d3e-8f40-00000000beef';
    const rows = joinable();
    rows[0] = { ...rows[0]!, names: ['하나', '유이'], links: [{ id: link, name: '하나', same_as: '유이' }] } as typeof rows[0];
    const { d, calls, state } = deps(rows);
    state.turns = 2;
    state.failReextract = 1;
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    button('Undo').click();
    await settle();
    panel().querySelector<HTMLInputElement>('.preview input[type=checkbox]')!.checked = true;
    button('Undo as shown').click();
    await settle();
    await settle();
    const base = `/v1/conversations/${id}/entity-links/${link}`;
    expect(posts(calls).filter(([, p]) => p === `${base}/remove/preview`)).toHaveLength(1);  // no stale-undo re-preview
    expect(panel().textContent).toContain('The join was undone, but the re-extraction failed');
    button('Retry the re-extraction').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `${base}/reextract`, { turns: [4, 5] }]);
    expect(panel().textContent).toContain('Queued 2 turns for re-extraction.');
  });

  it('drops a preview answer that arrives after the owner picked another name', async () => {
    const rows = [...joinable(), { id: 'c3', type: 'character', name: '소라', names: ['소라'], mentions: 2, links: [] }];
    const { d, state } = deps(rows);
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    let release!: () => void;
    state.hold = new Promise<void>((r) => { release = r; });
    button('Join').click();
    await settle();
    const pick = panel().querySelector<HTMLSelectElement>('select[aria-label="Same as"]')!;
    pick.value = '소라';
    pick.dispatchEvent(new Event('change', { bubbles: true }));
    state.hold = null;
    release();
    await settle();
    await settle();
    expect(panel().querySelector('.preview')).toBeNull();  // the late answer for 유이 is not shown
    expect(button('Join')?.disabled).toBe(false);
  });
});
