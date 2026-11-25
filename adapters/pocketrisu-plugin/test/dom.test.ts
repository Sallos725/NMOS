// @vitest-environment happy-dom
// DOM code (audit follow-up, 2026-09-27 review): the inspector sanitizer's tree walk and the settings panel.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StatusInfo } from '../src/core';
import { createChatSwitch } from '../src/chatoff';
import { markDetail, placeMarks, safeFragment } from '../src/inspector';
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

describe('timeline marks (PHASE-32 step 3)', () => {
  const lane = '<div class="tl"><div class="tl-row"><div class="tl-lab">located in</div><div class="tl-track">'
    + '<span class="tl-rule"></span>'
    + '<span class="tl-bar past" data-v="library" data-s="t2 – t6" data-o="superseded" data-l="18.182" data-w="45.454" '
    + 'style="background:url(https://x)" onclick="__ran=true" title="t">library</span>'
    + '<span class="tl-bar owner" data-v="&lt;b&gt;harbor&lt;/b&gt;" data-s="t7 – now" data-o="current" data-l="63.636" '
    + 'data-w="36.364">harbor</span><span class="tl-dot" data-l="50;left:0" data-v="x"></span></div></div>'
    + '<script>__ran=true</script></div>';

  it('places marks from their numbers, drops what could run, and shows a mark\'s text as text', () => {
    ran.__ran = false;
    const part = safeFragment(lane);
    placeMarks(part);
    const [past, current] = Array.from(part.querySelectorAll<HTMLElement>('.tl-bar'));
    expect(past.getAttribute('style')).toBe('left: 18.182%; width: calc(45.454% - 2px);');
    expect(past.getAttribute('onclick')).toBeNull();
    expect(part.querySelector('script')).toBeNull();
    expect(part.querySelector<HTMLElement>('.tl-dot')!.getAttribute('style')).toBeNull(); // not a plain number
    const card = markDetail(current, { canon: 'canon', owner: "The owner's version." });
    expect(card.querySelector('.v')!.textContent).toBe('<b>harbor</b>');
    expect(card.querySelector('b')).toBeNull();
    expect(card.textContent).toContain("The owner's version.");
    expect(Array.from(card.querySelectorAll('.tl-hist p')).map((p) => p.className)).toEqual(['', 'cur']);
    expect(ran.__ran).toBe(false);
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

  it('offers the matching plugin file, the token fix and the insecure page (pre-0.4.0 audit F24, F26, F27)', async () => {
    const mismatch = deps({ pluginExpected: 'other-build' });
    await openPanel(mismatch.d, 'status');
    await settle();
    const get = Array.from(document.querySelectorAll<HTMLButtonElement>('#nmos-panel button'))
      .find((b) => b.textContent === 'Get the matching plugin file')!;
    get.click();
    await settle();
    expect(mismatch.calls).toContainEqual(['DOWNLOAD', '/v1/plugin/nmos-pocketrisu.js', 'nmos-pocketrisu.js']);
    expect(document.getElementById('nmos-panel')!.textContent).toContain('Saved nmos-pocketrisu.js');
    document.body.replaceChildren();

    const refused = deps({ connected: false, error: '/v1/health -> HTTP 401: unauthorized' });
    await openPanel(refused.d, 'status');
    await settle();
    expect(document.getElementById('nmos-panel')!.textContent).toContain('The token does not match');
    document.body.replaceChildren();

    const insecure = deps({ insecure: true });
    await openPanel(insecure.d, 'status');
    await settle();
    const cards = Array.from(document.querySelectorAll('#nmos-panel .card'));
    expect(cards.some((c) => c.classList.contains('err') && (c.textContent ?? '').includes('not a secure context'))).toBe(true);
  });

  it('keeps the token with the connection settings (audit F27)', async () => {
    const { d, args } = deps();
    await openPanel(d, 'settings');
    await settle();
    const token = document.querySelector<HTMLInputElement>('#nmos-panel input[type="password"][placeholder^="Leave empty"]')!;
    token.value = 'abc';
    token.dispatchEvent(new Event('input', { bubbles: true }));
    Array.from(document.querySelectorAll<HTMLButtonElement>('#nmos-panel button')).find((b) => b.textContent === 'Save')!.click();
    await settle(); await settle();
    expect(args.auth_token).toBe('abc');
  });

  it.each(['sidecar_url', 'route'])('recovers Save after the host rejects %s, showing confirmed partial writes', async (failed) => {
    const { d, args, calls } = deps();
    const setArg = d.setArg;
    let reject = true;
    d.setArg = async (key, value) => {
      if (reject && key === failed) throw new Error('host connection write failed');
      await setArg(key, value);
    };
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const url = [...panel.querySelectorAll('input')].find((i) => i.value === args.sidecar_url)!;
    url.value = 'http://127.0.0.1:8801';
    url.dispatchEvent(new Event('input', { bubbles: true }));
    const save = [...panel.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent === 'Save')!;
    save.click();
    await vi.waitFor(() => expect(save.disabled).toBe(false));
    const bar = panel.querySelector('.bar .text')!;
    expect(bar.textContent).toContain(`${failed === 'route' ? 1 : 0}/6 settings confirmed saved`);
    expect(bar.textContent).toContain('host connection write failed');
    expect(args.sidecar_url).toBe(failed === 'route' ? url.value : 'http://127.0.0.1:8790');
    expect(calls.filter(([method]) => method === 'PUT')).toEqual([]);
    reject = false;
    save.click();
    await vi.waitFor(() => expect(bar.textContent).toBe('Saved.'));
    expect(args.sidecar_url).toBe(url.value);
    expect(save.disabled).toBe(true);
  });

  it('keeps Save and close failures visible and allows retry from the restored save bar', async () => {
    const { d, args } = deps();
    const setArg = d.setArg;
    d.setArg = async (key, value) => {
      if (key === 'route') throw new Error('host connection write failed');
      await setArg(key, value);
    };
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    const url = [...panel.querySelectorAll('input')].find((i) => i.value === args.sidecar_url)!;
    url.value = 'http://127.0.0.1:8801';
    url.dispatchEvent(new Event('input', { bubbles: true }));
    const button = (text: string) => [...panel.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent === text)!;
    button('Close').click();
    button('Save and close').click();
    await vi.waitFor(() => expect(button('Save')).toBeDefined());
    expect(document.getElementById('nmos-panel')).toBe(panel);
    expect(button('Save').disabled).toBe(false);
    expect(panel.querySelector('.bar .text')!.textContent).toContain('1/6 settings confirmed saved');
    expect(panel.querySelector('.bar .text')!.textContent).toContain('host connection write failed');
    d.setArg = setArg;
    button('Close').click();
    button('Save and close').click();
    await vi.waitFor(() => expect(document.getElementById('nmos-panel')).toBeNull());
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

  it('shows what the worker is doing after the sidecar card, and no card when the sidecar cannot say (PHASE-61 S5)', async () => {
    const worker = { queued: { extract: 642, reveal: 0, summarize: 56, canon: 1010, embed: 0 }, queued_total: 1708,
      running: 2, retrying: 35, dead_recent: 1, done_recent: 96, recent_minutes: 30, dead_hours: 24,
      last_error: { kind: 'canon', status: 'queued', at: new Date().toISOString(), text: 'HTTP 504: upstream' } };
    const titles = () => Array.from(document.querySelectorAll('#nmos-panel h2')).map((h) => h.textContent);
    const show = async (answer: () => Promise<unknown>) => {
      document.body.replaceChildren();
      const { d, calls } = deps();
      const usual = d.api;
      d.api = <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown) => (path === '/v1/worker/status'
        ? (calls.push([method, path, body]), answer() as Promise<T>) : usual<T>(method, path, body));
      await openPanel(d, 'status');
      await vi.waitFor(() => expect(document.querySelector('#nmos-panel .card')!.textContent).toContain('NMOS on'));
      for (let i = 0; i < 3; i++) await settle();
      expect(calls.filter(([, path]) => path === '/v1/worker/status')).toHaveLength(1);
    };

    await show(async () => worker);
    const shown = titles();
    expect(shown.indexOf('Model work')).toBe(shown.indexOf('Sidecar') + 1);
    const card = Array.from(document.querySelectorAll<HTMLElement>('#nmos-panel .card'))
      .find((c) => c.querySelector('h2')?.textContent === 'Model work')!;
    const lines = Array.from(card.querySelectorAll('div')).map((x) => [x.className, x.textContent]);
    expect(lines).toEqual([
      ['muted', '1,708 waiting (extraction 642 · summaries 56 · canon 1,010) · 2 running'],
      ['muted', 'Last 30 min: 96 finished · 35 being retried · 1 given up (24 h)'],
      ['warn', expect.stringMatching(/^Last error \d\d:\d\d \(canon\): HTTP 504: upstream$/)]]);

    // the last hour of model calls (S6), between the queue and the recent counts
    await show(async () => ({ ...worker, calls: { minutes: 60, total: 131, ok: 96, failed: 35, median_ms: 3200,
      by_fault: { timeout: 0, transport: 0, bad_reply: 0, http_other: 0, '429': 6, '504': 29 } } }));
    const withCalls = Array.from(document.querySelectorAll<HTMLElement>('#nmos-panel .card'))
      .find((c) => c.querySelector('h2')?.textContent === 'Model work')!;
    expect(Array.from(withCalls.querySelectorAll('div')).map((x) => x.textContent).slice(0, 3)).toEqual([
      '1,708 waiting (extraction 642 · summaries 56 · canon 1,010) · 2 running',
      "Last hour's calls: 96 ok · 35 failed (504 29 · 429 6) · median 3.2 s",
      'Last 30 min: 96 finished · 35 being retried · 1 given up (24 h)']);

    const without = shown.filter((x) => x !== 'Model work');
    await show(async () => { throw new Error('/v1/worker/status -> HTTP 404: Not Found'); });  // an older sidecar
    expect(titles()).toEqual(without);
    await show(() => { throw new TypeError('Failed to fetch'); });  // thrown before any promise
    expect(titles()).toEqual(without);
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
      const warning = [...document.querySelectorAll('#nmos-panel .card')]
        .find((c) => c.textContent!.includes('Memory was recalled without semantic search'));
      if (shown) expect(warning!.textContent).toContain('raise Embedding wait (ms)');
      document.getElementById('nmos-panel')?.remove();
    }
  });

  describe('trimming on the status card (PHASE-60 S1 "Shown")', () => {
    // The clock stands still: the "ago" line of two renders compared must not cross a second (it did, now and then).
    const NOW = Date.now();
    beforeEach(() => { vi.spyOn(Date, 'now').mockReturnValue(NOW); });
    afterEach(() => { vi.mocked(Date.now).mockRestore(); });
    const last = { at: NOW, ms: 900, packetChars: 10, packet: 'x', outcome: 'injected' as const, deadlineMs: 3000 };
    const lastCard = (title: string) => [...document.querySelectorAll<HTMLElement>('#nmos-panel .card')]
      .find((c) => c.querySelector('h2')?.textContent === title)!;
    const lineOf = (card: HTMLElement, text: string) => [...card.querySelectorAll<HTMLElement>('div')]
      .find((e) => e.textContent === text);
    const render = async (status: Partial<StatusInfo>, language: 'ko' | 'en') => {
      const { d, args } = deps(status);
      args.language = language;
      await openPanel(d, 'status');
      await settle();
      const card = lastCard(language === 'en' ? 'Last request' : '마지막 요청');
      document.getElementById('nmos-panel')?.remove();
      return card;
    };
    const dropped = { dropped: 12, savedTokens: 3400, reason: null, keepFromTurn: 40 };

    it('says how many old messages were left out and the tokens saved, right after the "ago · ms" line', async () => {
      for (const [language, text] of [['ko', '오래된 대화 12개를 빼고 보냈습니다 (약 3,400토큰 절약)'],
        ['en', 'Left out 12 old messages (about 3,400 tokens saved)']] as const) {
        const card = await render({ last: { ...last, trim: dropped } }, language);
        const line = lineOf(card, text)!;
        expect(line).toBeDefined();
        expect(line.className).toBe('muted');
        expect(line.classList.contains('mono')).toBe(false);
        expect(line.previousElementSibling!.textContent).toContain('900ms');
      }
    });

    it('says why nothing was left out', async () => {
      const card = await render({ last: { ...last, trim: { dropped: 0, savedTokens: 0, reason: 'uncovered', keepFromTurn: null } } },
        'ko');
      const line = lineOf(card, '오래된 대화를 빼지 않았습니다: 기억 정리(추출·요약)가 아직 따라오지 못함')!;
      expect(line).toBeDefined();
      expect(line.classList.contains('mono')).toBe(false);
    });

    it('adds nothing without a trimming outcome', async () => {
      for (const language of ['ko', 'en'] as const) {
        const plain = await render({ last }, language);
        const trimmed = await render({ last: { ...last, trim: dropped } }, language);
        const text = language === 'en' ? 'Left out 12 old messages (about 3,400 tokens saved)'
          : '오래된 대화 12개를 빼고 보냈습니다 (약 3,400토큰 절약)';
        lineOf(trimmed, text)!.remove();
        expect(plain.innerHTML).toBe(trimmed.innerHTML);
        expect(plain.children.length).toBe(4); // title, outcome, "ago · ms", packet
      }
    });

    const coverage = { recordedThroughTurn: 48, coveredThroughTurn: 40 };
    const recorded = { ko: '기억은 48턴까지 기록되어 있습니다', en: 'Memory is recorded through turn 48' } as const;

    it('says the turn memory is recorded through, as a muted line after the trimming line', async () => {
      for (const language of ['ko', 'en'] as const) {
        const card = await render({ last: { ...last, trim: dropped, coverage } }, language);
        const line = lineOf(card, recorded[language])!;
        expect(line).toBeDefined();
        expect(line.className).toBe('muted');
        expect(line.classList.contains('mono')).toBe(false);
        expect(line.previousElementSibling!.textContent).toContain(language === 'en' ? 'Left out 12' : '오래된 대화 12개');
        expect(line.nextElementSibling!.tagName).toBe('DETAILS');
        const alone = await render({ last: { ...last, coverage } }, language);  // trimming off: the line still shows
        expect(lineOf(alone, recorded[language])!.previousElementSibling!.textContent).toContain('900ms');
      }
    });

    it('adds nothing without a recorded turn', async () => {
      for (const language of ['ko', 'en'] as const) {
        const plain = await render({ last }, language);
        for (const without of [null, { recordedThroughTurn: null, coveredThroughTurn: 40 }]) {
          const card = await render({ last: { ...last, coverage: without } }, language);
          expect(card.innerHTML).toBe(plain.innerHTML);
        }
        const shown = await render({ last: { ...last, coverage } }, language);
        lineOf(shown, recorded[language])!.remove();
        expect(shown.innerHTML).toBe(plain.innerHTML);
      }
    });
  });

  describe('trimming settings (PHASE-60 S1)', () => {
    const titles = { ko: '오래된 대화 빼기', en: 'Leave out old dialogue' } as const;
    const sentences = {
      ko: '기억이 이미 담고 있는 오래된 대화는 보내는 내용에서 뺍니다. 빼는 지점은 아래 턴 수만큼씩 한꺼번에 옮겨서, 제공자의 프롬프트 캐시가 계속 맞습니다. 채팅에서는 아무것도 지우지 않습니다. 장면 요약 만들기가 켜져 있어야 합니다.',
      en: "Old dialogue that memory already holds is left out of what is sent, in steps of the number of turns below, so the provider's prompt cache keeps working. Nothing is removed from the chat. It needs Scene summaries on.",
    } as const;
    const open = async (language: 'ko' | 'en', stored: Record<string, string> = {}, views = false) => {
      const h = deps(views ? { features: { extraction: true, views: true } } : {});
      h.args.language = language;
      Object.assign(h.args, stored);
      const api = h.d.api;
      h.d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) =>
        (path.startsWith('/v1/views/') ? { html: '<div class="v"></div>' } as T : api<T>(method, path, body, timeout));
      const writes: [string, string | number][] = [];
      const setArg = h.d.setArg;
      h.d.setArg = async (key, value) => { writes.push([key, value]); await setArg(key, value); };
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      const card = [...panel.querySelectorAll<HTMLElement>('.card')]
        .find((c) => c.querySelector('h2')?.textContent === titles[language])!;
      expect(card).toBeDefined();
      const save = panel.querySelector<HTMLButtonElement>('.bar button.primary')!;
      return { ...h, writes, panel, card, save, bar: panel.querySelector('.bar .text')!,
        box: card.querySelector<HTMLInputElement>('input[type="checkbox"]')!,
        keep: card.querySelector<HTMLInputElement>('input[type="number"]')!,
        warn: card.querySelector<HTMLElement>('div.warn')! };
    };
    const set = (input: HTMLInputElement, value: string | boolean) => {
      if (typeof value === 'boolean') input.checked = value; else input.value = value;
      input.dispatchEvent(new Event(typeof value === 'boolean' ? 'change' : 'input', { bubbles: true }));
    };

    it('shows its own card in the memory group, in plain words', async () => {
      for (const language of ['ko', 'en'] as const) {
        const { panel, card, keep } = await open(language, {}, true);
        expect(card.dataset.group).toBe('memory');
        expect(card.querySelector('p.sub')!.textContent).toBe(sentences[language]);
        expect(card.querySelector('.check')!.textContent)
          .toBe(language === 'en' ? 'Leave out old dialogue memory holds' : '기억이 담은 오래된 대화 빼기');
        expect(keep.previousElementSibling!.textContent).toBe(language === 'en' ? 'Recent turns always sent' : '항상 보내는 최근 턴 수');
        expect([keep.min, keep.max, keep.step]).toEqual(['4', '200', '1']);
        panel.querySelector<HTMLButtonElement>('.groups button[data-group="memory"]')!.click();
        expect(card.style.display).toBe('');
        panel.querySelector<HTMLButtonElement>('.groups button[data-group="models"]')!.click();
        expect(card.style.display).toBe('none');
        panel.remove();
      }
    });

    it('loads the stored args, and is off with 16 turns when they are unset', async () => {
      const stored = await open('en', { trim_old_turns: '1', keep_recent_turns: '40' });
      expect([stored.box.checked, stored.keep.value, stored.save.disabled]).toEqual([true, '40', true]);
      stored.panel.remove();
      const unset = await open('en');
      expect([unset.box.checked, unset.keep.value, unset.save.disabled]).toEqual([false, '16', true]);
    });

    it('saves the two plugin args alone, with no sidecar request', async () => {
      const { box, keep, save, bar, calls, writes } = await open('en');
      set(box, true);
      set(keep, '30');
      expect(bar.textContent).toBe('Unsaved changes: Leave out old dialogue');
      const before = calls.length;
      save.click();
      await vi.waitFor(() => expect(bar.textContent).toBe('Saved.'));
      expect(writes).toEqual([['trim_old_turns', 1], ['keep_recent_turns', 30]]);
      expect(calls.slice(before)).toEqual([]);  // no PUT /v1/config, and no reload of the sidecar's settings
      expect(save.disabled).toBe(true);
      set(box, false);
      save.click();
      await vi.waitFor(() => expect(writes.at(-2)).toEqual(['trim_old_turns', 0]));
      expect(calls.filter(([method]) => method === 'PUT')).toEqual([]);
    });

    it('stores and shows a count past the limit as 200', async () => {
      const { box, keep, save, bar, args } = await open('ko');
      set(box, true);
      set(keep, '500');
      save.click();
      await vi.waitFor(() => expect(bar.textContent).toBe('저장했습니다.'));
      expect(save.disabled).toBe(true);
      expect([args.trim_old_turns, args.keep_recent_turns, keep.value]).toEqual(['1', '200', '200']);
    });

    it('says a failed write in the bar and keeps the change to save again', async () => {
      const { box, save, bar, d } = await open('en');
      const setArg = d.setArg;
      d.setArg = async (key, value) => {
        if (key === 'keep_recent_turns') throw new Error('host argument write failed');
        await setArg(key, value);
      };
      set(box, true);
      save.click();
      await vi.waitFor(() => expect(bar.textContent).toBe('host argument write failed'));
      expect(save.disabled).toBe(false);
    });

    it('warns, in words, only while the switch is on and scene summaries are off', async () => {
      for (const language of ['ko', 'en'] as const) {
        const { panel, box, warn } = await open(language);
        const summaries = [...panel.querySelectorAll('.check')]
          .find((c) => c.textContent === (language === 'en' ? 'Scene summaries' : '장면 요약 만들기'))!
          .querySelector('input') as HTMLInputElement;
        expect(warn.textContent).toBe(language === 'en' ? 'Note: Scene summaries are off, so nothing is left out until they are on.'
          : '주의: 장면 요약 만들기가 꺼져 있어서, 켜기 전까지는 아무것도 빼지 않습니다.');
        const shown = () => warn.style.display !== 'none';
        expect(shown()).toBe(false);  // off, summaries on
        set(summaries, false);
        expect(shown()).toBe(false);  // off, summaries off
        set(box, true);
        expect(shown()).toBe(true);
        set(summaries, true);
        expect(shown()).toBe(false);
        set(summaries, false);
        set(box, false);
        expect(shown()).toBe(false);
        panel.remove();
      }
    });
  });

  describe('optional reranker settings (PHASE-60 S5)', () => {
    const titles = { ko: '재정렬 모델 (선택)', en: 'Reranker (optional)' } as const;
    const sentences = {
      ko: '주소와 모델을 모두 넣으면, 매 요청마다 사용자 메시지와 찾은 기억 후보 최대 30개의 글을 그 주소로 보내 더 알맞은 순서로 다시 매깁니다(임베딩 모델에 대화 글을 보내는 것과 같습니다). 유료 서비스는 요청마다 비용이 들 수 있습니다. 응답이 늦거나 오류가 나면 기억은 원래 순서 그대로 들어갑니다. 임베딩 대기와 재정렬 대기를 합쳐 플러그인의 요청 제한 시간(기본 3초)보다 넉넉히 짧게 두세요. 끄려면 주소나 모델을 비워 두세요.',
      en: 'With both an address and a model set, each request sends your message and the text of up to 30 recalled memory candidates to that address to put them in a better order, just as chat text goes to the embedder. Paid services may charge for each request. If it is slow or fails, memory goes out in its usual order. Keep the embedding wait plus the reranker wait well under the plugin request deadline (3 s by default). Leave the address or model empty to turn it off.',
    } as const;
    const states = {
      on: { ko: '켜짐: 요청마다 순서를 다시 매깁니다', en: 'On: reorders memory candidates on every request' },
      off: { ko: '꺼짐: 주소와 모델이 비어 있습니다', en: 'Off: address and model are empty' },
    } as const;
    type RerankCfg = { url: string; model: string; timeout_ms: number; format: string; key_set: boolean;
      configured: boolean; note: string };
    const defaultRerank = (over: Partial<RerankCfg> = {}): RerankCfg => ({
      url: '', model: '', timeout_ms: 600, format: 'standard', key_set: false, configured: false,
      note: 'SIDECAR_ENGLISH_NOTE_NOT_SHOWN', ...over,
    });
    const open = async (language: 'ko' | 'en', initial: RerankCfg | null, views = false) => {
      const h = deps(views ? { features: { extraction: true, views: true } } : {});
      h.args.language = language;
      let rr = initial ? { ...initial } : null;
      const snapshot = () => (rr ? { ...config, rerank: { ...rr } } : { ...config });
      h.d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown) => {
        h.calls.push([method, path, body]);
        if (path.startsWith('/v1/views/')) return { html: '<div class="v"></div>' } as T;
        if (path.startsWith('/v1/conversations?')) return [] as T;
        if (path === '/v1/config/preview') return { model_change: false, queued: {} } as T;
        if (method === 'PUT' && path === '/v1/config' && rr && body && typeof body === 'object') {
          const b = body as Record<string, unknown>;
          if ('rerank_url' in b) rr.url = String(b.rerank_url);
          if ('rerank_model' in b) rr.model = String(b.rerank_model);
          if ('rerank_timeout_ms' in b) rr.timeout_ms = Number(b.rerank_timeout_ms);
          if ('rerank_api_key' in b && String(b.rerank_api_key)) rr.key_set = true;
          if (!rr.url.trim()) rr.key_set = false;
          rr.configured = Boolean(rr.url.trim() && rr.model.trim());
          return { ...snapshot(), queued_jobs: 0 } as T;
        }
        return (method === 'PUT' ? { ...snapshot(), queued_jobs: 0 } : snapshot()) as T;
      };
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      if (views) {
        panel.querySelector<HTMLButtonElement>('.groups button[data-group="models"]')!.click();
        await settle();
      }
      const card = [...panel.querySelectorAll<HTMLElement>('.card')]
        .find((c) => c.querySelector('h2')?.textContent === titles[language])!;
      const inputs = [...card.querySelectorAll<HTMLInputElement>('input')];
      return { ...h, panel, card,
        save: panel.querySelector<HTMLButtonElement>('.bar button.primary')!,
        bar: panel.querySelector('.bar .text')!,
        state: card.querySelector<HTMLElement>('.line')!,
        url: inputs[0]!, model: inputs[1]!, key: inputs[2]!, wait: inputs[3]! };
    };
    const type = (input: HTMLInputElement, value: string) => {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    };

    it('renders in the models group right after embeddings with the plain sentence and on/off state (KO and EN)', async () => {
      for (const language of ['ko', 'en'] as const) {
        for (const configured of [false, true]) {
          const initial = configured
            ? defaultRerank({ url: 'https://rr.example/v1', model: 'rerank-1', timeout_ms: 800, configured: true, key_set: true })
            : defaultRerank();
          const { panel, card, state, key, wait } = await open(language, initial, true);
          expect(card.dataset.group).toBe('models');
          expect(card.style.display).toBe('');
          const visibleModels = [...panel.querySelectorAll<HTMLElement>('[data-group="models"]')]
            .filter((c) => !c.closest('.groups') && c.style.display !== 'none')
            .map((c) => c.querySelector('h2')?.textContent);
          expect(visibleModels).toEqual(language === 'en'
            ? ['Fact extraction LLM', 'Semantic recall embeddings', 'Reranker (optional)']
            : ['사실 추출 LLM', '의미 검색 임베딩', '재정렬 모델 (선택)']);
          expect(card.querySelector('p.sub')!.textContent).toBe(sentences[language]);
          expect(card.textContent).not.toContain('SIDECAR_ENGLISH_NOTE_NOT_SHOWN');
          expect(state.textContent).toBe(states[configured ? 'on' : 'off'][language]);
          expect(state.classList.contains(configured ? 'ok' : 'muted')).toBe(true);
          expect(state.querySelector('.dot')!.classList.contains('ok')).toBe(configured);
          expect(state.classList.contains('mono')).toBe(false);
          expect([key.type, key.getAttribute('autocomplete'), key.value]).toEqual(['password', 'off', '']);
          expect(key.placeholder).toBe(configured
            ? (language === 'en' ? 'saved — type only to change' : '저장됨 — 바꿀 때만 입력')
            : (language === 'en' ? 'only if needed' : '필요할 때만 입력'));
          expect(wait.previousElementSibling!.textContent).toBe(language === 'en' ? 'Reranker wait (ms)' : '재정렬 대기(ms)');
          expect([wait.type, wait.min, wait.max, wait.value]).toEqual(['number', '50', '5000', configured ? '800' : '600']);
          // no test action, no format control
          expect(card.querySelectorAll('button')).toHaveLength(0);
          expect(card.querySelectorAll('select')).toHaveLength(0);
          panel.remove();
        }
      }
    });

    it('saves URL, model and wait through the single Save bar, sends the key only when typed, and clears URL and model to turn off', async () => {
      for (const language of ['ko', 'en'] as const) {
        const { panel, calls, url, model, key, wait, state, save, bar } = await open(language, defaultRerank());
        // 1. Save URL, model, wait without typing a key
        type(url, ' https://rr.example/v1 ');
        type(model, ' rerank-1 ');
        type(wait, '900');
        expect(bar.textContent).toBe(language === 'en'
          ? 'Unsaved changes: Reranker (optional)'
          : '저장하지 않은 변경: 재정렬 모델 (선택)');
        const saved = language === 'en' ? 'Saved.' : '저장했습니다.';
        save.click();
        await vi.waitFor(() => expect(bar.textContent).toBe(saved));
        expect(save.disabled).toBe(true);
        expect(calls.filter(([m]) => m === 'PUT')).toEqual([['PUT', '/v1/config', {
          rerank_url: 'https://rr.example/v1', rerank_model: 'rerank-1', rerank_timeout_ms: 900,
        }]]);
        expect(calls.some(([, p]) => p === '/v1/config/preview')).toBe(false);
        expect(state.textContent).toBe(states.on[language]);
        expect(key.value).toBe('');
        expect(key.placeholder).toBe(language === 'en' ? 'only if needed' : '필요할 때만 입력');

        // 2. Type a key and save: key is sent, then emptied with the saved placeholder
        type(key, ' rk-live-1 ');
        save.click();
        await vi.waitFor(() => expect(bar.textContent).toBe(saved));
        expect(save.disabled).toBe(true);
        expect(calls.filter(([m]) => m === 'PUT').at(-1)).toEqual(['PUT', '/v1/config', {
          rerank_url: 'https://rr.example/v1', rerank_model: 'rerank-1', rerank_timeout_ms: 900, rerank_api_key: 'rk-live-1',
        }]);
        expect(key.value).toBe('');
        expect(key.placeholder).toBe(language === 'en' ? 'saved — type only to change' : '저장됨 — 바꿀 때만 입력');

        // 3. Clear URL and model to turn off: empty strings sent, no key sent, state line returns to off
        type(url, '');
        type(model, '');
        save.click();
        await vi.waitFor(() => expect(bar.textContent).toBe(saved));
        expect(save.disabled).toBe(true);
        expect(calls.filter(([m]) => m === 'PUT').at(-1)).toEqual(['PUT', '/v1/config', {
          rerank_url: '', rerank_model: '', rerank_timeout_ms: 900,
        }]);
        expect(state.textContent).toBe(states.off[language]);
        expect(state.classList.contains('muted')).toBe(true);
        expect(key.value).toBe('');
        panel.remove();
      }
    });

    it('never logs the typed reranker key and never shows it again after the save', async () => {
      const logged: unknown[][] = [];
      const spies = (['log', 'info', 'warn', 'error', 'debug'] as const)
        .map((m) => vi.spyOn(console, m).mockImplementation((...args: unknown[]) => { logged.push(args); }));
      try {
        const { panel, url, model, key, save, bar } = await open('en', defaultRerank());
        type(url, 'https://rr.example/v1');
        type(model, 'rerank-1');
        type(key, 'rk-secret-7');
        save.click();
        await vi.waitFor(() => expect(bar.textContent).toBe('Saved.'));
        expect(key.value).toBe('');
        expect([...panel.querySelectorAll<HTMLInputElement>('input')].some((i) => i.value.includes('rk-secret-7')))
          .toBe(false);
        expect(panel.textContent).not.toContain('rk-secret-7');
        expect(JSON.stringify(logged)).not.toContain('rk-secret-7');
        panel.remove();
      } finally {
        for (const s of spies) s.mockRestore();
      }
    });

    it('shows no reranker card and sends no rerank keys when /v1/config omits rerank (KO and EN)', async () => {
      for (const language of ['ko', 'en'] as const) {
        for (const views of [false, true]) {
          const { panel, card, calls, save, bar } = await open(language, null, views);
          expect(card.style.display).toBe('none');
          if (views) {
            const visibleModels = [...panel.querySelectorAll<HTMLElement>('[data-group="models"]')]
              .filter((c) => !c.closest('.groups') && c.style.display !== 'none')
              .map((c) => c.querySelector('h2')?.textContent);
            expect(visibleModels).toEqual(language === 'en'
              ? ['Fact extraction LLM', 'Semantic recall embeddings']
              : ['사실 추출 LLM', '의미 검색 임베딩']);
          }
          // saving another section sends no rerank_* keys
          const llmEndpoint = [...panel.querySelectorAll<HTMLInputElement>('input')]
            .find((i) => i.value === 'https://llm.example/v1')!;
          type(llmEndpoint, 'https://llm.example/v2');
          save.click();
          await vi.waitFor(() => expect(bar.textContent).toBe(language === 'en' ? 'Saved.' : '저장했습니다.'));
          expect(save.disabled).toBe(true);
          const put = calls.filter(([m]) => m === 'PUT').at(-1)![2] as Record<string, unknown>;
          expect(Object.keys(put).filter((k) => k.startsWith('rerank_'))).toEqual([]);
          panel.remove();
        }
      }
    });
  });

  describe('extra request values on the extraction model (PHASE-61 S4)', () => {
    const OR = 'https://openrouter.ai/api/v1';
    const labels = {
      en: { body: 'Extra request values (JSON)', effort: 'Reasoning effort', noTemp: 'Do not send a temperature',
        invalid: 'Not a JSON object', title: 'Fact extraction LLM' },
      ko: { body: '추가 요청 값 (JSON)', effort: '추론 강도', noTemp: 'temperature 보내지 않기',
        invalid: 'JSON 객체가 아닙니다', title: '사실 추출 LLM' },
    } as const;
    const open = async (language: 'ko' | 'en', llm: Record<string, unknown>, preview = true) => {
      const h = deps();
      h.args.language = language;
      const state = { llm: { ...config.llm, ...llm } as Record<string, unknown> };
      const snapshot = () => ({ ...config, llm: { ...state.llm } });
      h.d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown) => {
        h.calls.push([method, path, body]);
        if (path.startsWith('/v1/conversations?')) return [] as T;
        if (path === '/v1/config/test') return { ok: true, ms: 12 } as T;
        if (path === '/v1/config/preview') {
          return (preview ? { model_change: true, queued: { continue: { extract: 0 }, recent: { extract: 40 } } }
            : { model_change: false, queued: {} }) as T;
        }
        if (method === 'PUT' && path === '/v1/config') {
          const b = body as Record<string, unknown>;
          if ('llm_url' in b) state.llm.url = b.llm_url;
          if ('llm_model' in b) state.llm.model = b.llm_model;
          if ('llm_extra_body' in b) state.llm.extra_body = b.llm_extra_body;
          if ('llm_no_temperature' in b) state.llm.no_temperature = b.llm_no_temperature;
          return { ...snapshot(), queued_jobs: 0 } as T;
        }
        return snapshot() as T;
      };
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      const L = labels[language];
      const card = [...panel.querySelectorAll<HTMLElement>('.card')].find((c) => c.querySelector('h2')?.textContent === L.title)!;
      const button = (text: string) => [...panel.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent === text)!;
      return { ...h, panel, card, L,
        text: card.querySelector<HTMLTextAreaElement>(`textarea[aria-label="${L.body}"]`)!,
        effort: card.querySelector<HTMLSelectElement>(`select[aria-label="${L.effort}"]`)!,
        noTemp: card.querySelector<HTMLInputElement>('input[type="checkbox"]')!,
        endpoint: card.querySelector<HTMLInputElement>('input[placeholder="https://…/v1"]')!,
        error: [...card.querySelectorAll<HTMLElement>('.msg.err')].find((e) => e.textContent === L.invalid)!,
        save: panel.querySelector<HTMLButtonElement>('.bar button.primary')!,
        bar: panel.querySelector('.bar .text')!,
        button };
    };
    const shown = (node: HTMLElement | null): boolean => {
      for (let n = node; n; n = n.parentElement) if (n.style.display === 'none') return false;
      return Boolean(node);
    };
    const type = (input: HTMLInputElement | HTMLTextAreaElement, value: string) => {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    };
    // As a browser does it: picking an option fires `input`, then `change`, both bubbling to the settings view.
    const choose = (select: HTMLSelectElement, value: string) => {
      select.value = value;
      select.dispatchEvent(new Event('input', { bubbles: true }));
      select.dispatchEvent(new Event('change', { bubbles: true }));
    };
    const puts = (calls: [string, string, unknown][]) => calls.filter(([m, p]) => m === 'PUT' && p === '/v1/config').map(([, , b]) => b);

    it('loads the body and the switch, with every label in both languages', async () => {
      for (const language of ['ko', 'en'] as const) {
        const body = { provider: { sort: 'price' }, reasoning: { effort: 'low' } };
        const h = await open(language, { url: OR, extra_body: body, no_temperature: true });
        expect(shown(h.text)).toBe(true);
        expect(h.text.value).toBe(JSON.stringify(body, null, 2));
        expect(shown(h.effort)).toBe(true);
        expect(h.effort.value).toBe('low');
        expect([...h.effort.options].map((o) => o.value)).toEqual(['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']);
        expect(h.effort.options[0]!.text).toBe('—');
        expect(h.noTemp.checked).toBe(true);
        expect(h.card.textContent).toContain(h.L.noTemp);
        expect(h.card.textContent).toContain(h.L.effort);
        expect(shown(h.error)).toBe(false);
        expect(h.save.disabled).toBe(true);  // loading is no change
        h.panel.remove();
        const empty = await open(language, { url: OR, extra_body: {}, no_temperature: false });
        expect(empty.text.value).toBe('');
        expect(empty.effort.value).toBe('');
        expect(empty.noTemp.checked).toBe(false);
        empty.panel.remove();
      }
    });

    it('writes the chosen effort into the text and saves it beside the other keys through the model-change preview', async () => {
      const h = await open('en', { url: OR, extra_body: { provider: { sort: 'price' } }, no_temperature: false });
      choose(h.effort, 'high');
      expect(JSON.parse(h.text.value)).toEqual({ provider: { sort: 'price' }, reasoning: { effort: 'high' } });
      expect(h.bar.textContent).toBe('Unsaved changes: Fact extraction LLM');
      h.save.click();
      await vi.waitFor(() => expect(h.panel.querySelector('.bar .model-change')).not.toBeNull());
      const sent = { llm_url: OR, llm_model: 'm', llm_extra_body: { provider: { sort: 'price' }, reasoning: { effort: 'high' } } };
      expect(h.calls.filter(([, p]) => p === '/v1/config/preview').map(([, , b]) => b)).toEqual([sent]);
      expect(puts(h.calls)).toEqual([]);  // nothing saved before the answer
      h.button('Save').click();
      await vi.waitFor(() => expect(h.bar.textContent).toBe('Saved.'));
      expect(puts(h.calls)).toEqual([{ ...sent, on_model_change: { mode: 'continue', canon: false } }]);
      // "—" takes it out again, and reasoning with it
      choose(h.effort, '');
      expect(JSON.parse(h.text.value)).toEqual({ provider: { sort: 'price' } });
      h.panel.remove();
    });

    it('moves the dropdown when the JSON is typed by hand: a value, custom, or disabled while not an object', async () => {
      const h = await open('ko', { url: OR, extra_body: {}, no_temperature: false });
      const values = () => [...h.effort.options].map((o) => o.value);
      type(h.text, '{"reasoning": {"effort": "medium"}, "max_tokens": 900}');
      expect([h.effort.value, h.effort.disabled, values().includes('custom')]).toEqual(['medium', false, false]);
      type(h.text, '{"reasoning": {"effort": "turbo"}}');
      expect([h.effort.value, h.effort.disabled]).toEqual(['custom', false]);
      expect(h.effort.selectedOptions[0]!.text).toBe('직접 입력');
      type(h.text, '{"reasoning": {"effort": "medium"');
      expect(h.effort.disabled).toBe(true);
      expect(values().includes('custom')).toBe(false);
      expect(shown(h.error)).toBe(true);
      type(h.text, '{"a": 1}');
      expect([h.effort.value, h.effort.disabled, shown(h.error)]).toEqual(['', false, false]);
      h.panel.remove();
    });

    it('shows the dropdown only for an OpenRouter address, following the address field and the preset', async () => {
      const h = await open('en', { url: 'https://llm.example/v1', extra_body: {}, no_temperature: false });
      expect(shown(h.text)).toBe(true);
      expect(shown(h.noTemp)).toBe(true);
      expect(shown(h.effort)).toBe(false);
      type(h.endpoint, 'https://openrouter.ai/api/v1');
      expect(shown(h.effort)).toBe(true);
      type(h.endpoint, 'https://openrouter.ai.example.com/v1');
      expect(shown(h.effort)).toBe(false);
      const preset = h.card.querySelector('select')!;
      choose(preset, String([...preset.options].findIndex((o) => o.text === 'OpenRouter')));
      expect(h.endpoint.value).toBe(OR);
      expect(shown(h.effort)).toBe(true);
      choose(preset, '0');  // "Off" empties the address
      expect(h.endpoint.value).toBe('');
      expect(shown(h.effort)).toBe(false);
      h.panel.remove();
    });

    it('sends neither field when they did not change, and the switch alone as a model change', async () => {
      const h = await open('en', { url: OR, extra_body: { b: 2, a: 1 }, no_temperature: false });
      type(h.text, '{"a":1,"b":2}');  // same object, other text
      expect(h.save.disabled).toBe(true);
      const model = [...h.card.querySelectorAll('input')].find((i) => i.value === 'm')!;
      type(model, 'm2');
      h.save.click();
      await vi.waitFor(() => expect(h.panel.querySelector('.bar .model-change')).not.toBeNull());
      h.button('Save').click();
      await vi.waitFor(() => expect(h.bar.textContent).toBe('Saved.'));
      expect(puts(h.calls).at(-1)).toEqual({ llm_url: OR, llm_model: 'm2', on_model_change: { mode: 'continue', canon: false } });
      h.noTemp.click();
      h.save.click();
      await vi.waitFor(() => expect(h.panel.querySelector('.bar .model-change')).not.toBeNull());
      expect(h.calls.filter(([, p]) => p === '/v1/config/preview').at(-1)![2])
        .toEqual({ llm_url: OR, llm_model: 'm2', llm_no_temperature: true });
      h.button('Save').click();
      await vi.waitFor(() => expect(h.bar.textContent).toBe('Saved.'));
      expect(puts(h.calls).at(-1)).toEqual({ llm_url: OR, llm_model: 'm2', llm_no_temperature: true,
        on_model_change: { mode: 'continue', canon: false } });
      expect(h.noTemp.checked).toBe(true);
      h.panel.remove();
    });

    it('sends nothing while the text is not a JSON object, neither the save nor the test', async () => {
      const h = await open('en', { url: OR, extra_body: {}, no_temperature: false });
      h.args.trim_old_turns = '0';
      const trim = [...h.panel.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((i) =>
        i.nextElementSibling?.textContent?.startsWith('Leave out old dialogue'))!;
      type(h.text, '[1, 2]');
      trim.click();  // another unsaved change: still nothing is written
      h.save.click();
      await settle(); await settle();
      expect(h.bar.textContent).toBe('Not a JSON object');
      expect(h.calls.filter(([m, p]) => m !== 'GET' && p.startsWith('/v1/config'))).toEqual([]);
      expect(h.args.trim_old_turns).toBe('0');
      expect(h.save.disabled).toBe(false);
      h.button('Test').click();
      await settle();
      expect(h.calls.some(([, p]) => p === '/v1/config/test')).toBe(false);
      expect(h.card.querySelector('.btns ~ .msg')!.textContent).toBe('Not a JSON object');
      h.panel.remove();
    });

    it("sends the form's body and switch with the extraction model's test", async () => {
      const h = await open('en', { url: OR, extra_body: {}, no_temperature: false });
      choose(h.effort, 'minimal');
      h.noTemp.click();
      h.button('Test').click();
      await vi.waitFor(() => expect(h.calls.some(([, p]) => p === '/v1/config/test')).toBe(true));
      expect(h.calls.find(([, p]) => p === '/v1/config/test')![2]).toEqual({ kind: 'llm', url: OR, model: 'm',
        api_key: undefined, extra_body: { reasoning: { effort: 'minimal' } }, no_temperature: true });
      h.panel.remove();
    });

    it('shows none of the three and sends neither field to a sidecar from before the setting (KO and EN)', async () => {
      for (const language of ['ko', 'en'] as const) {
        const h = await open(language, { url: OR });
        expect(shown(h.text)).toBe(false);
        expect(shown(h.effort)).toBe(false);
        expect(shown(h.noTemp)).toBe(false);
        h.button(language === 'en' ? 'Test' : '연결 테스트').click();
        await vi.waitFor(() => expect(h.calls.some(([, p]) => p === '/v1/config/test')).toBe(true));
        expect(h.calls.find(([, p]) => p === '/v1/config/test')![2]).toEqual({ kind: 'llm', url: OR, model: 'm', api_key: undefined });
        type(h.endpoint, 'https://openrouter.ai/api/v2');
        h.save.click();
        await vi.waitFor(() => expect(h.panel.querySelector('.bar .model-change')).not.toBeNull());
        h.panel.querySelector<HTMLButtonElement>('.bar .model-change button.primary')!.click();
        await vi.waitFor(() => expect(puts(h.calls)).toHaveLength(1));
        expect(puts(h.calls)[0]).toEqual({ llm_url: 'https://openrouter.ai/api/v2', llm_model: 'm',
          on_model_change: { mode: 'continue', canon: false } });
        h.panel.remove();
      }
    });
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

  it('asks what a changed extraction model redoes, with what each choice queues (PHASE-57 A3)', async () => {
    for (const pick of ['cancel', 'recent', 'continue'] as const) {
      const { d, calls } = deps();
      const api = d.api;
      d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) => {
        if (path === '/v1/config/preview') {
          calls.push([method, path, body]);
          return { model_change: true, queued: { continue: { extract: 0, summarize: 0, canon: 0 },
            recent: { extract: 90, summarize: 12, canon: 0 }, canon: { extract: 0, summarize: 0, canon: 7 } } } as T;
        }
        return api<T>(method, path, body, timeout);
      };
      await openPanel(d, 'settings');
      const panel = document.getElementById('nmos-panel')!;
      const model = [...panel.querySelectorAll('input')].find((i) => i.value === 'm')!;
      model.value = 'm2';
      model.dispatchEvent(new Event('input', { bubbles: true }));
      (panel.querySelector('.bar button.primary') as HTMLButtonElement).click();
      await settle();
      const box = panel.querySelector('.bar .model-change')!;
      expect(box.textContent).toContain('Carry on: nothing is redone');
      expect(box.textContent).toContain('(102 jobs)');  // the latest turns and their summaries
      expect(box.textContent).toContain('(+7 jobs)');
      expect(calls.filter(([method]) => method === 'PUT')).toEqual([]);  // nothing saved before the answer
      if (pick === 'recent') {
        (box.querySelector('input[value="recent"]') as HTMLInputElement).click();
        (box.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
      }
      const button = [...box.querySelectorAll('button')].find((b) => b.textContent === (pick === 'cancel' ? 'Cancel' : 'Save'))!;
      button.click();
      await settle();
      const puts = calls.filter(([method]) => method === 'PUT');
      if (pick === 'cancel') {
        expect(puts).toEqual([]);
        expect(panel.querySelector('.bar')!.textContent).toContain('Not saved.');
      } else {
        expect(puts).toEqual([['PUT', '/v1/config', { llm_url: 'https://llm.example/v1', llm_model: 'm2',
          on_model_change: pick === 'recent' ? { mode: 'recent', canon: true } : { mode: 'continue', canon: false } }]]);
      }
      panel.remove();
    }
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

  it('sets the embedding wait, and leaves it alone on a sidecar that has no such setting (K34)', async () => {
    const wait = () => document.querySelector<HTMLInputElement>('#nmos-panel input[type="number"][max="5000"][min="100"]')!;
    let { d, calls } = deps();
    await openPanel(d, 'settings');
    await settle();
    expect(wait().disabled).toBe(true);  // an older sidecar: nothing to show, nothing sent
    document.body.replaceChildren();
    (config.recall as Record<string, number>).embed_timeout_ms = 300;
    try {
      ({ d, calls } = deps());
      await openPanel(d, 'settings');
      await settle();
      expect(wait().disabled).toBe(false);
      expect(wait().value).toBe('300');
      wait().value = '1000';
      wait().dispatchEvent(new Event('input', { bubbles: true }));
      (document.querySelector('#nmos-panel button.primary') as HTMLButtonElement).click();
      await settle();
      expect(calls.filter(([method]) => method === 'PUT').at(-1)![2]).toMatchObject({ embed_timeout_ms: 1000 });
      const bar = () => document.querySelector('#nmos-panel .bar .text')!;
      expect(bar().textContent).not.toContain('minus 500 ms');
      wait().value = '2800';  // the deadline is the default 3000: the wait leaves it too little (audit F20)
      wait().dispatchEvent(new Event('input', { bubbles: true }));
      (document.querySelector('#nmos-panel button.primary') as HTMLButtonElement).click();
      await settle();
      expect(calls.filter(([method]) => method === 'PUT').at(-1)![2]).toMatchObject({ embed_timeout_ms: 2800 });
      expect(bar().textContent).toContain('minus 500 ms');
    } finally {
      delete (config.recall as Record<string, number>).embed_timeout_ms;
    }
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

  describe('@name pins (PHASE-60 S8)', () => {
    const labels = { ko: '메시지에서 @이름으로 인물 고정', en: 'Pin a character with @name in a message' } as const;
    const hints = {
      ko: '켜면 "@세라 어디 있어?"처럼 메시지에 @이름으로 쓴 인물은, 장면에 이름이 나오지 않아도 그 답장의 기억에 들어갑니다. 단어 안의 @(이메일 주소, 아이디)나 이 채팅의 인물이 아닌 이름 앞의 @는 아무 일도 하지 않습니다.',
      en: 'On: a message like "@Sera where are you?" keeps Sera in memory for that reply even when the scene does not name her. An @ inside a word (an e-mail address, a handle) or before a name that is no character of this chat does nothing.',
    } as const;
    const open = async (language: 'ko' | 'en', reported?: boolean) => {
      const h = deps();
      h.args.language = language;
      if (reported !== undefined) (config.recall as Record<string, unknown>).pin_at_mentions = reported;
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      const label = [...panel.querySelectorAll('.check')].find((c) => c.textContent === labels[language])!;
      return { ...h, panel, label, box: label.querySelector('input') as HTMLInputElement,
        save: panel.querySelector<HTMLButtonElement>('.bar button.primary')! };
    };
    const puts = (calls: [string, string, unknown][]) => calls.filter(([method]) => method === 'PUT').map(([, , body]) => body);
    afterEach(() => { delete (config.recall as Record<string, unknown>).pin_at_mentions; });

    it('shows the setting with its example in the recall tuning card', async () => {
      for (const language of ['ko', 'en'] as const) {
        const { panel, label } = await open(language, false);
        expect(label.closest('.card')!.querySelector('h2')!.textContent).toBe(language === 'en' ? 'Recall tuning' : '검색 조정');
        expect(label.nextElementSibling!.textContent).toBe(hints[language]);
        expect(label.nextElementSibling!.classList.contains('mono')).toBe(false);
        panel.remove();
      }
    });

    it('loads what the sidecar reports and saves it as pin_at_mentions', async () => {
      const on = await open('en', true);
      expect([on.box.checked, on.box.disabled]).toEqual([true, false]);
      on.box.checked = false;
      on.box.dispatchEvent(new Event('change', { bubbles: true }));
      on.save.click();
      await vi.waitFor(() => expect(puts(on.calls)).toHaveLength(1));
      expect(puts(on.calls)[0]).toMatchObject({ pin_at_mentions: false });
      on.panel.remove();
      const off = await open('ko', false);
      expect([off.box.checked, off.box.disabled]).toEqual([false, false]);
      off.box.checked = true;
      off.box.dispatchEvent(new Event('change', { bubbles: true }));
      off.save.click();
      await vi.waitFor(() => expect(puts(off.calls)).toHaveLength(1));
      expect(puts(off.calls)[0]).toMatchObject({ pin_at_mentions: true });
    });

    it('is disabled and never sent on a sidecar that has no such setting', async () => {
      const { panel, box, save, calls } = await open('en');
      expect([box.checked, box.disabled]).toEqual([false, true]);
      const topK = [...panel.querySelectorAll<HTMLInputElement>('input[type="number"][max="20"]')][0]!;
      topK.value = '3';
      topK.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).toMatchObject({ recall_top_k: 3 });
      expect(puts(calls)[0]).not.toHaveProperty('pin_at_mentions');
    });
  });

  describe('embedding chunks per message (ADR 0062, Tier 4 E8)', () => {
    const open = async (reported?: number) => {
      const h = deps();
      if (reported !== undefined) (config.embeddings as Record<string, unknown>).max_chunks = reported;
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      const label = [...panel.querySelectorAll('label')].find((l) => l.textContent === 'Embedding chunks per message')!;
      const input = label.nextElementSibling as HTMLInputElement;
      return { ...h, panel, input, hint: input.closest('.row')!.nextElementSibling as HTMLElement,
        save: panel.querySelector<HTMLButtonElement>('.bar button.primary')! };
    };
    const puts = (calls: [string, string, unknown][]) => calls.filter(([method]) => method === 'PUT').map(([, , body]) => body);
    afterEach(() => { delete (config.embeddings as Record<string, unknown>).max_chunks; });

    it('shows the reported cap in the tuning card with the characters it covers, and saves a change', async () => {
      const { input, hint, save, calls } = await open(8);
      expect(input.closest('.card')!.querySelector('h2')!.textContent).toBe('Recall tuning');
      expect([input.value, input.disabled, input.min, input.max]).toEqual(['8', false, '1', '64']);
      expect(hint.textContent).toContain('8 chunks = 5,600 characters');
      input.value = '16';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      expect(hint.textContent).toContain('16 chunks = 11,200 characters');
      expect(hint.textContent).toContain('embeds every chat again');
      input.value = '65';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      expect(hint.textContent).toBe('Enter a whole number from 1 to 64.');
      input.value = '16';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).toMatchObject({ embed_max_chunks: 16 });
    });

    it('is not sent with another tuning change while it is unchanged', async () => {
      const { panel, save, calls } = await open(8);
      const topK = [...panel.querySelectorAll<HTMLInputElement>('input[type="number"][max="20"]')][0]!;
      topK.value = '3';
      topK.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).toMatchObject({ recall_top_k: 3 });
      expect(puts(calls)[0]).not.toHaveProperty('embed_max_chunks');
    });

    it('is disabled and never sent on a sidecar that does not report it', async () => {
      const { panel, input, hint, save, calls } = await open();
      expect([input.value, input.disabled]).toEqual(['', true]);
      expect(hint.textContent).toContain('NMOS_EMBED_MAX_CHUNKS');
      const topK = [...panel.querySelectorAll<HTMLInputElement>('input[type="number"][max="20"]')][0]!;
      topK.value = '3';
      topK.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).not.toHaveProperty('embed_max_chunks');
    });
  });

  describe('extract right after a reply (PHASE-67)', () => {
    const open = async (reported?: boolean) => {
      const h = deps();
      if (reported !== undefined) (config.extraction as Record<string, unknown>).on_output = reported;
      await openPanel(h.d, 'settings');
      await settle();
      const panel = document.getElementById('nmos-panel')!;
      const check = [...panel.querySelectorAll('.check')].find((c) => c.textContent === 'Extract right after a reply')!;
      return { ...h, panel, box: check.querySelector('input') as HTMLInputElement,
        hint: check.nextElementSibling as HTMLElement, save: panel.querySelector<HTMLButtonElement>('.bar button.primary')! };
    };
    const puts = (calls: [string, string, unknown][]) => calls.filter(([method]) => method === 'PUT').map(([, , body]) => body);
    afterEach(() => { delete (config.extraction as Record<string, unknown>).on_output; });

    it('shows the reported switch in the tuning card, says what it costs, and saves a change', async () => {
      const { box, hint, save, calls } = await open(false);
      expect(box.closest('.card')!.querySelector('h2')!.textContent).toBe('Recall tuning');
      expect([box.checked, box.disabled]).toEqual([false, false]);
      expect(hint.textContent).toContain('about 20 seconds after it finishes instead of when you answer it');
      expect(hint.textContent).toContain('the last reply of a session is not lost');
      expect(hint.textContent).toContain('pays for one extraction that is thrown away');
      box.checked = true;
      box.dispatchEvent(new Event('change', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).toMatchObject({ extract_on_output: true });
    });

    it('is not sent with another tuning change while it is unchanged', async () => {
      const { panel, box, save, calls } = await open(true);
      expect(box.checked).toBe(true);
      const topK = [...panel.querySelectorAll<HTMLInputElement>('input[type="number"][max="20"]')][0]!;
      topK.value = '3';
      topK.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).not.toHaveProperty('extract_on_output');
    });

    it('is disabled and never sent on a sidecar that does not report it', async () => {
      const { panel, box, save, calls } = await open();
      expect([box.checked, box.disabled]).toEqual([false, true]);
      const topK = [...panel.querySelectorAll<HTMLInputElement>('input[type="number"][max="20"]')][0]!;
      topK.value = '3';
      topK.dispatchEvent(new Event('input', { bubbles: true }));
      save.click();
      await vi.waitFor(() => expect(puts(calls)).toHaveLength(1));
      expect(puts(calls)[0]).not.toHaveProperty('extract_on_output');
    });
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
      hold: null as Promise<void> | null, prompt: 'List outfits.', failPrompt: false,
      cut: null as unknown };  // PHASE-62: what `cut-turns` answers; null: a sidecar without the route
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
        if (path.endsWith('/retry-failed')) return { retried: { extract: 1, embed: 1, canon: 0 } } as T;
        if (path.endsWith('/cut-turns')) {  // PHASE-62 S3
          if (state.cut === null) throw new Error(`${path} -> HTTP 404`);
          return state.cut as T;
        }
        if (path.endsWith('/read-cut')) {
          return { queued: { extract: 3, ...((body as { summaries?: boolean }).summaries ? { summarize: 1 } : {}) } } as T;
        }
        if (path === '/v1/notes/prompt') {  // PHASE-56
          if (method === 'PUT') {
            if (state.failPrompt) throw new Error(`${path} -> HTTP 503`);
            state.prompt = (body as { prompt: string }).prompt;
          }
          return { prompt: state.prompt } as T;
        }
        if (path.endsWith('/notes')) {  // PHASE-50
          return { last_turn: 12, chars: 60, text: '[NMOS note · t12 · 2026-10-23]\n## Address and standing\n- Hana ↔ Kaito: x\n[/NMOS note]',
            sections: [{ kind: 'chronicle', made: 'none', cached: false, held: 0, reason: 'no_scenes' },
              { kind: 'address', made: 'facts', cached: false, held: 0, reason: '' },
              { kind: 'diverged', made: 'model', cached: false, held: 0, reason: '', entries: 3, left_out: 1 }].map((p, i) => (i ? p : { ...p, stale: 21 })) } as T;
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

  it('makes one note for the author\'s note and shows it to copy (PHASE-50)', async () => {
    const { d, calls } = deps();
    await openChat(d);
    button("For the author's note").click();
    const boxes = [...panel().querySelectorAll<HTMLInputElement>('input[type=checkbox][value]')];
    // PHASE-53: what diverged from the setting first and on; the chronicle and address off.
    expect(boxes.map((b) => [b.value, b.checked])).toEqual([['diverged', true], ['chronicle', false], ['address', false],
      ['custom', false]]);
    boxes[2]!.click(); // and "address"
    button('Make').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/notes`,
      { sections: ['diverged', 'address'], chars: 3000, secrets: false }]);
    const shown = [...panel().querySelectorAll<HTMLTextAreaElement>('textarea[readonly]')];
    expect(shown.map((b) => b.value)).toEqual(['[NMOS note · t12 · 2026-10-23]\n## Address and standing\n- Hana ↔ Kaito: x\n[/NMOS note]']);
    expect(panel().textContent).toContain('chronicle: no scene summary yet');
    expect(panel().textContent).toContain('address and standing: straight from memory');
    expect(panel().textContent).toContain('diverged from the setting: written by the model');
    expect(panel().textContent).toContain('3 lorebook entries compared, 1 left out for length');
    expect(panel().textContent).toContain('Left out 21 open threads not mentioned again for more than 30 turns');
    expect(button('Copy')).toBeTruthy();
  });

  it("asks for the note's parts in the chat's language or in English (Tier 4 C2)", async () => {
    const { d, calls } = deps();
    await openChat(d);
    button("For the author's note").click();
    const language = panel().querySelector<HTMLSelectElement>('select[aria-label="Note language"]')!;
    expect([...language.options].map((o) => [o.value, o.textContent])).toEqual([['chat', "The chat's language"],
      ['en', 'English']]);
    expect(language.value).toBe('chat');
    button('Make').click();
    await settle();
    // The default is not sent (review nit 12): the body an older sidecar was sent before the setting existed.
    expect(posts(calls).at(-1)![2]).not.toHaveProperty('language');
    language.value = 'en';
    button('Make').click();
    await settle();
    expect(posts(calls).at(-1)![2]).toMatchObject({ sections: ['diverged'], language: 'en' });
  });

  it('writes a custom part from the saved prompt and saves an edited one (PHASE-56)', async () => {
    const { d, calls, state } = deps();
    await openChat(d);
    button("For the author's note").click();
    await settle();
    const prompt = panel().querySelector<HTMLTextAreaElement>('textarea[aria-label="Custom prompt"]')!;
    expect(prompt.closest('div')!.style.display).toBe('none');
    const box = (v: string) => panel().querySelector<HTMLInputElement>(`input[type=checkbox][value="${v}"]`)!;
    box('diverged').click(); // off: custom alone
    box('custom').click();
    expect(prompt.closest('div')!.style.display).toBe('');
    expect(prompt.value).toBe('List outfits.'); // one prompt for every chat, from the sidecar
    expect(panel().textContent).toContain('NMOS cannot check it line by line');
    button('Make').click();
    await settle();
    expect(calls.filter(([m]) => m === 'PUT')).toEqual([]); // unchanged: not saved again
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/notes`,
      { sections: ['custom'], chars: 3000, secrets: false, custom_prompt: 'List outfits.',
        custom_setting: false }]);
    prompt.value = '  Who owes whom?  ';
    const setting = [...panel().querySelectorAll<HTMLInputElement>('input[type=checkbox]:not([value])')]
      .find((b) => b.nextElementSibling?.textContent === 'Include the setting (card, lorebook)')!;
    setting.click();
    button('Make').click();
    await settle();
    expect(calls.filter(([m]) => m === 'PUT')).toEqual([['PUT', '/v1/notes/prompt', { prompt: 'Who owes whom?' }]]);
    expect(posts(calls).at(-1)![2]).toMatchObject({ custom_prompt: 'Who owes whom?', custom_setting: true });
    state.failPrompt = true;
    prompt.value = 'Something else.';
    button('Make').click();
    await settle();
    expect(posts(calls).at(-1)![2]).toMatchObject({ custom_prompt: 'Something else.' }); // made from the box anyway
    expect(panel().textContent).toContain('The prompt could not be saved');
    prompt.value = '   ';
    button('Make').click();
    await settle();
    expect(panel().textContent).toContain('Write a custom prompt.');
  });

  it('says why a custom part was left out and that NMOS did not check it (PHASE-56)', async () => {
    const { d } = deps();
    const api = d.api;
    d.api = (async (method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) => {
      if (path.endsWith('/notes') && method === 'POST') {
        return { last_turn: 12, chars: 10, text: '', sections: [
          { kind: 'chronicle', made: 'assembled', cached: false, held: 0, reason: '', stale: 4 },
          { kind: 'custom', made: 'none', cached: false, held: 0, reason: 'held', stale: 4 }] };
      }
      return api(method, path, body, timeout);
    }) as PanelDeps['api'];
    await openChat(d);
    button("For the author's note").click();
    await settle();
    panel().querySelector<HTMLInputElement>('input[type=checkbox][value="custom"]')!.click();
    button('Make').click();
    await settle();
    expect(panel().textContent).toContain('custom: left out, it told a secret');
    expect(panel().textContent).toContain('Left out 4 open threads'); // the same threads, counted once
  });

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

  it('offers "Read the cut turns again" only when the sidecar counts some, says what it would read, and posts on the second click (PHASE-62 S3)', async () => {
    const { d, calls, state } = deps();
    await openChat(d);
    const cut = () => button('Read the cut turns again');
    expect(cut().style.display).toBe('none');
    // a page that says so, on a sidecar without the route: nothing is shown
    state.html = '<div class="has-cut"><p class="muted">3 turns were read only in part.</p></div>';
    button('Refresh').click();
    await settle();
    expect(cut().style.display).toBe('none');
    state.cut = { cap: 24000, extract: { turns: 3, pending: 0, failed: 0, characters: 9000, input_tokens: [41000, 52000] } };
    button('Refresh').click();
    await settle();
    expect(cut().style.display).toBe('');
    expect(panel().querySelector<HTMLInputElement>('label.sub input[type=checkbox]')!.parentElement!.style.display).toBe('none');
    cut().click();
    await settle();
    expect(posts(calls)).toEqual([]);  // the first click only says what it would read
    const armed = [...panel().querySelectorAll('button')].find((b) => b.textContent!.startsWith('3 turns'))!;
    expect(armed.textContent).toBe('3 turns · about 41,000–52,000 input tokens · click again to read');
    armed.click();
    await settle();
    expect(posts(calls).map(([, path, body]) => [path, body])).toEqual([[`/v1/conversations/${id}/read-cut`, { summaries: false }]]);
    expect(panel().textContent).toContain('Queued 3 turns to read again and 0 summaries to write again.');
    // with summaries to write again: offered apart, and sent only when ticked
    state.cut = { cap: 24000, extract: { turns: 3, input_tokens: [41000, 52000] }, summarize: { windows: 2, input_tokens: [60000, 110000] } };
    button('Refresh').click();
    await settle();
    const box = panel().querySelector<HTMLInputElement>('label.sub input[type=checkbox]')!;
    expect(box.parentElement!.style.display).toBe('');
    expect(box.parentElement!.textContent).toContain('Also write 2 scene summaries again (about 60,000–110,000 more input tokens)');
    box.checked = true;
    cut().click();
    await settle();
    const both = [...panel().querySelectorAll('button')].find((b) => b.textContent!.startsWith('3 turns and 2 summaries'))!;
    expect(both.textContent).toBe('3 turns and 2 summaries · about 101,000–162,000 input tokens · click again to read');
    both.click();
    await settle();
    expect(posts(calls).at(-1)!.slice(1)).toEqual([`/v1/conversations/${id}/read-cut`, { summaries: true }]);
    // nothing left to read: the button goes
    state.html = '<p>all read</p>';
    state.cut = { cap: 24000, extract: { turns: 0, input_tokens: [0, 0] } };
    button('Refresh').click();
    await settle();
    expect(cut().style.display).toBe('none');
  });

  it('offers "Retry failed" only while the page shows failed work, and posts it (owner, 2026-10-14)', async () => {
    const { d, calls, state } = deps();
    await openChat(d);
    expect(button('Retry failed').style.display).toBe('none');
    state.html = '<div class="has-failed"><p class="warn">2 failed jobs.</p></div>';
    button('Refresh').click();
    await settle();
    expect(button('Retry failed').style.display).toBe('');
    button('Retry failed').click();
    await settle();
    expect(posts(calls).map(([, path]) => path)).toEqual([`/v1/conversations/${id}/retry-failed`]);
    expect(panel().textContent).toContain('Running 2 failed jobs again.');
    state.html = '<p>all done</p>';
    button('Refresh').click();
    await settle();
    expect(button('Retry failed').style.display).toBe('none');
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

  it('selects rows of Needs attention, previews, then applies or retracts them at once (PHASE-57 B1, B2)', async () => {
    const { d, calls, state } = deps();
    const bulk = (data: unknown) => `<span class="rq" data-bulk="${JSON.stringify(data).replace(/"/g, '&quot;')}"></span>`;
    const lock = { kind: 'fact_lock', item: '81' };
    const off = { kind: 'fact_retract', item: '81' };
    const restore = { kind: 'fact_restore', item: '93' };
    state.html = `<details id="s-attention" open><summary>Needs attention</summary><table>`
      + `<tr><td>canon</td><td>${mark('fact_lock:81')}${mark('fact_correct:81:value.lock')}${mark('fact_correct:82:value')}`
      + `${bulk({ g: 'canon', l: 'Conflicts with the setting', apply: lock, retract: off })}</td></tr>`
      + `<tr><td>dropped</td><td>${bulk({ g: 'dropped', l: 'Facts a re-extraction dropped', apply: restore })}</td></tr>`
      + `<tr><td>forged</td><td>${bulk({ g: 'dropped', l: 'x', apply: { kind: 'name_split', item: '1' } })}</td></tr>`
      + `</table></details><p>${mark(`undo_batch:${t1}`)}</p>`;
    const api = d.api;
    d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) => {
      if (path.endsWith('/repairs/batch')) {
        calls.push([method, path, body]);
        const b = body as { items: { kind: string }[]; undo: string[] };
        const counts: Record<string, number> = {};
        for (const i of b.items) counts[i.kind] = (counts[i.kind] ?? 0) + 1;
        return { counts, errors: 0, plan: [] } as T;
      }
      return api<T>(method, path, body, timeout);
    };
    await openChat(d);
    const boxes = [...panel().querySelectorAll<HTMLInputElement>('span.rq input[type=checkbox]')];
    expect(boxes).toHaveLength(2);  // the forged mark (a repair that needs its preview) is dropped
    button('Select all Facts a re-extraction dropped (1)').click();
    boxes[0]!.click();
    await settle();
    expect(button('Apply selected (2)')).toBeDefined();
    expect(button('Retract selected (1)')).toBeDefined();
    button('Apply selected (2)').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs/batch`,
      { items: [restore, lock], undo: [], preview: true }]);
    expect(panel().textContent).toContain('Restore 1, Lock 1 · 0 skipped. Click again to save them at once.');
    button('Click again to do it').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs/batch`, { items: [restore, lock], undo: [] }]);
    expect(panel().textContent).toContain('Done for 2 at once.');
    // retract: the dropped row has none, so it is skipped
    for (const b of [...panel().querySelectorAll<HTMLInputElement>('span.rq input[type=checkbox]')]) b.click();
    await settle();
    button('Retract selected (1)').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs/batch`,
      { items: [off], undo: [], preview: true }]);
    expect(panel().textContent).toContain('Retract 1 · 1 skipped.');
    // canon's statement corrected and kept; a bulk action undone at once
    button('Correct the setting value').click();
    const form = panel().querySelector('span.rpform')!;
    form.querySelector('input')!.value = 'elder sister';
    button('Save').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs`,
      { kind: 'fact_correct', item: '81', new_value: 'elder sister', lock: true }]);
    button('Undo all').click();
    await settle();
    expect(posts(calls).at(-1)).toEqual(['POST', `/v1/conversations/${id}/repairs/batch/${t1}/remove`, {}]);
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
    expect(button('Close 0 selected threads')?.style.display).toBe('none');  // and its bar, with no row to pick
    expect(button('Close 0 selected threads')?.closest<HTMLElement>('.btns')?.parentElement?.style.display).toBe('none');
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

  describe("the pin switch on a person's page (PHASE-60 S8)", () => {
    const pin = '0190f3a4-1b2c-7d3e-8f40-0000000000aa';
    const hanaRow = (extra: Record<string, unknown> = {}) =>
      ({ id: who, type: 'character', name: '하나', names: ['하나'], mentions: 9, links: [], aliases: [], ...extra });
    const titles = { ko: '하나 고정', en: 'Pin 하나' } as const;  // the card names whose page it is (SHOTS finding 9)
    const sentences = {
      ko: '고정한 인물의 현재 사실은 장면에 이름이 나오지 않아도 매 답장의 기억에 들어갑니다. 그래서 고정은 요청마다 기억 예산의 일부를 씁니다. 언제든 풀 수 있습니다.',
      en: "A pinned character's current facts go into memory on every reply, even when the scene does not name them, so a pin uses part of the memory budget on every request. You can take it off any time.",
    } as const;
    const pages = { inspector: `/inspector/c/${id}/e/${who}`, sheet: `/views/c/${id}/person/${who}` } as const;
    const cardOf = (language: 'ko' | 'en') => [...panel().querySelectorAll<HTMLElement>('.card')]
      .find((c) => c.querySelector('h2')?.textContent === titles[language] && c.style.display !== 'none');
    /** The entity harness, with a person sheet, a language, and rows that follow a pin and an unpin. */
    const open = async (rows: Record<string, unknown>[] | 'fail', page: keyof typeof pages = 'inspector',
      language: 'ko' | 'en' = 'en', refuse?: string) => {
      const h = deps(rows === 'fail' ? [] : rows);
      const api = h.d.api;
      h.d.getArg = async (key) => (key === 'language' ? language : '');
      h.d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) => {
        if (path.startsWith(`/v1/views/c/${id}/person/`)) {
          h.calls.push([method, path.split('?')[0]!, body]);
          return { html: '<p>a character</p>' } as T;
        }
        if (rows === 'fail' && path.endsWith('/entities')) throw new Error(`${path} -> HTTP 503`);
        const answer = await api<T>(method, path, body, timeout);
        if (method === 'POST' && refuse) throw new Error(`/v1/conversations/${id}/repairs -> HTTP 422: ${refuse}`);
        if (method === 'POST' && rows !== 'fail' && path.endsWith('/repairs')) rows[0]!.pinned = pin;
        if (method === 'POST' && rows !== 'fail' && path.endsWith('/remove')) delete rows[0]!.pinned;
        return answer;
      };
      await openChat(h.d, pages[page]);
      return h;
    };
    const entityGets = (calls: [string, string, unknown][]) =>
      calls.filter(([method, path]) => method === 'GET' && path.endsWith('/entities'));

    it('offers an unpinned character a switch that is off, and pins it with one request', async () => {
      for (const page of ['inspector', 'sheet'] as const) {
        for (const language of ['ko', 'en'] as const) {
          const { calls } = await open([hanaRow()], page, language);
          const card = cardOf(language)!;
          expect(card, `${page} ${language}`).toBeDefined();
          expect(card.querySelector('p.sub')!.textContent).toBe(sentences[language]);
          expect(card.querySelector('.check')!.textContent).toBe(language === 'en' ? 'Always keep in memory' : '항상 기억에 두기');
          const box = card.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
          expect(box.checked).toBe(false);
          expect(entityGets(calls)).toHaveLength(1);  // one list for the join card and this one
          box.click();
          await settle();
          expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs`, { kind: 'entity_pin', item: who }]]);
          const after = cardOf(language)!;  // the page was refreshed
          expect(after.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(true);
          expect(after.querySelector('.msg')!.textContent).toBe(language === 'en' ? 'Pinned' : '고정했습니다');
          document.body.replaceChildren();
        }
      }
    });

    it('shows a pin as on and takes it back with its remove request', async () => {
      for (const language of ['ko', 'en'] as const) {
        const { calls } = await open([hanaRow({ pinned: pin })], 'sheet', language);
        const box = cardOf(language)!.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
        expect(box.checked).toBe(true);
        box.click();
        await settle();
        expect(posts(calls)).toEqual([['POST', `/v1/conversations/${id}/repairs/${pin}/remove`, {}]]);
        const after = cardOf(language)!;
        expect(after.querySelector<HTMLInputElement>('input[type="checkbox"]')!.checked).toBe(false);
        expect(after.querySelector('.msg')!.textContent).toBe(language === 'en' ? 'Unpinned' : '고정을 풀었습니다');
        document.body.replaceChildren();
      }
    });

    it('shows no card for the persona, an excluded character, another kind, an entity not listed, or no list', async () => {
      const cases: (Record<string, unknown>[] | 'fail')[] = [[hanaRow({ persona: true })], [hanaRow({ excluded: true })],
        [hanaRow({ type: 'place' })], [hanaRow({ id: t2 })], 'fail'];
      for (const rows of cases) {
        await open(rows, 'inspector');
        expect(panel().textContent).toContain('a character');  // the page itself is there
        expect(cardOf('en'), JSON.stringify(rows)).toBeUndefined();
        document.body.replaceChildren();
      }
    });

    it('puts the switch back and says the refusal when the sidecar refuses the pin', async () => {
      const { calls } = await open([hanaRow()], 'inspector', 'en', '하나 is not mentioned in this chat');
      const card = cardOf('en')!;
      const box = card.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
      box.click();
      await settle();
      expect(posts(calls)).toHaveLength(1);
      expect(box.checked).toBe(false);
      expect(box.disabled).toBe(false);
      expect(card.querySelector('.msg')!.textContent).toBe('Invalid: 하나 is not mentioned in this chat');
    });

    it("hides one character's switch while another page loads, and when that page fails", async () => {
      const h = deps([hanaRow()]);
      const api = h.d.api;
      let release!: () => void;
      const held = new Promise<void>((r) => { release = r; });
      h.d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeout?: number) => {
        if (path.startsWith(`/v1/inspector/c/${id}/e/${t2}`)) { await held; throw new Error(`${path} -> HTTP 503`); }
        if (path.startsWith(`/v1/inspector/c/${id}/e/${who}`)) return { html: `<a href="/inspector/c/${id}/e/${t2}">카이토</a>` } as T;
        return api<T>(method, path, body, timeout);
      };
      await openChat(h.d, pages.inspector);
      expect(cardOf('en')).toBeDefined();
      panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}/e/${t2}"]`)!.click();
      await settle();
      expect(cardOf('en')).toBeUndefined();  // loading
      release();
      await settle();
      expect(panel().textContent).toContain('HTTP 503');
      expect(cardOf('en')).toBeUndefined();
    });

    it("leaves the sidecar's page as it sent it: the card sits beside it", async () => {
      for (const page of ['inspector', 'sheet'] as const) {
        await open([hanaRow()], page);
        const body = [...panel().querySelectorAll('p')].find((p) => p.textContent === 'a character')!.parentElement!;
        expect(body.innerHTML).toBe('<p>a character</p>');
        expect(body.contains(cardOf('en')!)).toBe(false);
        document.body.replaceChildren();
      }
    });
  });

  it('drops a preview answer that arrives after the owner picked another name', async () => {
    const rows = [...joinable(), { id: 'c3', type: 'character', name: '유현', names: ['유현'], mentions: 2, links: [] }];
    const { d, state } = deps(rows);
    await openChat(d, `/inspector/c/${id}/e/${who}`);
    let release!: () => void;
    state.hold = new Promise<void>((r) => { release = r; });
    button('Join').click();
    await settle();
    const pick = panel().querySelector<HTMLSelectElement>('select[aria-label="Same as"]')!;
    pick.value = '유현';
    pick.dispatchEvent(new Event('change', { bubbles: true }));
    state.hold = null;
    release();
    await settle();
    await settle();
    expect(panel().querySelector('.preview')).toBeNull();  // the late answer for 유이 is not shown
    expect(button('Join')?.disabled).toBe(false);
  });
});

describe('the timeline in the panel (PHASE-32 step 3)', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });
  const who = '5c6d7e8f-9a0b-5c2d-8e3f-0123456789ab';
  const fragment = (span: string) => '<div class="tl"><p class="tl-switch">'
    + (span ? '<span class="tl-span" data-span="">Whole chat</span> · <b>Last 25 turns</b>'
      : '<b>Whole chat</b> · <span class="tl-span" data-span="recent">Last 25 turns</span>')
    + '</p><div class="tl-main"><div class="tl-group"><p class="tl-h">Facts</p><div class="tl-row">'
    + '<div class="tl-lab">located in</div><div class="tl-track"><span class="tl-rule"></span>'
    + '<span class="tl-bar past" data-v="library" data-s="t2 – t6" data-o="superseded" data-l="18.182" data-w="45.454">library</span>'
    + '<span class="tl-bar" data-v="harbor" data-s="t7 – now" data-o="current" data-l="63.636" data-w="36.364">harbor</span>'
    + '</div></div></div></div></div>';

  function deps() {
    const calls: string[] = [];
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT', path: string) => {
        calls.push(`${method} ${path}`);
        if (path.startsWith('/v1/inspector/c/') && path.includes('part=timeline')) {
          return { html: fragment(path.includes('span=recent') ? 'recent' : '') } as T;
        }
        if (path.startsWith(`/v1/inspector/c/${id}/e/${who}`)) {
          return { html: '<h1>Hana</h1><details id="s-timeline"><summary><h2>Over time</h2></summary>'
            + '<div class="tl-lazy"></div></details><details id="s-about" open><summary><h2>Facts</h2></summary>'
            + '<p>table</p></details>' } as T;
        }
        if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: `<a href="/inspector/c/${id}/e/${who}">Hana</a>` } as T;
        if (path.startsWith('/v1/inspector')) return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
        if (path.endsWith('/entities')) return [] as T;
        throw new Error('404');
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.1.0b21', features: {}, last: null }),
      getArg: async (key) => (key === 'language' ? 'en' : ''),
      setArg: async () => {},
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
      chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => null }),
      download: async () => 0,
    };
    return { d, calls };
  }
  const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((resolve) => setTimeout(resolve, 0)); };
  const panel = () => document.getElementById('nmos-panel')!;
  const parts = (calls: string[]) => calls.filter((c) => c.includes('part=timeline'));

  async function openHana(d: PanelDeps): Promise<void> {
    await openPanel(d, 'inspector');
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!.click();
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}/e/${who}"]`)!.click();
    await settle();
  }

  it('asks for the timeline only when its section opens, and only once', async () => {
    const { d, calls } = deps();
    await openHana(d);
    expect(calls).toContain(`GET /v1/inspector/c/${id}/e/${who}?timeline=lazy&status=lazy&lang=en`);
    expect(parts(calls)).toEqual([]); // closed: nothing asked
    const section = panel().querySelector<HTMLDetailsElement>('#s-timeline')!;
    for (let i = 0; i < 4; i += 1) { // open and close it again and again
      section.open = true;
      section.dispatchEvent(new Event('toggle'));
      await settle();
      section.open = false;
      section.dispatchEvent(new Event('toggle'));
      await settle();
    }
    expect(parts(calls)).toEqual([`GET /v1/inspector/c/${id}/e/${who}?part=timeline&lang=en`]);
    const bars = Array.from(panel().querySelectorAll<HTMLElement>('.tl-bar'));
    expect(bars.map((b) => b.style.left)).toEqual(['18.182%', '63.636%']);
  });

  it('shows a tapped mark under its lane, one detail at a time, and switches the window', async () => {
    const { d, calls } = deps();
    await openHana(d);
    const section = panel().querySelector<HTMLDetailsElement>('#s-timeline')!;
    section.open = true;
    section.dispatchEvent(new Event('toggle'));
    await settle();
    for (let i = 0; i < 50; i += 1) {
      for (const bar of Array.from(panel().querySelectorAll<HTMLElement>('.tl-bar'))) bar.click();
    }
    const cards = panel().querySelectorAll('.tl-card');
    expect(cards.length).toBe(1);
    expect(cards[0].querySelector('.v')!.textContent).toBe('harbor');
    expect(cards[0].previousElementSibling!.classList.contains('tl-row')).toBe(true); // right under its lane
    expect(panel().querySelectorAll('.tl .sel').length).toBe(1);
    const selected = panel().querySelector<HTMLElement>('.tl .sel')!;
    selected.click(); // a second tap closes it
    expect(panel().querySelectorAll('.tl-card, .tl .sel').length).toBe(0);
    selected.click();
    expect(panel().querySelectorAll('.tl-card').length).toBe(1);
    panel().querySelector<HTMLElement>('.tl-span[data-span="recent"]')!.click();
    await settle();
    expect(parts(calls).at(-1)).toBe(`GET /v1/inspector/c/${id}/e/${who}?part=timeline&span=recent&lang=en`);
    expect(panel().querySelector('.tl-switch b')!.textContent).toBe('Last 25 turns');
    expect(panel().querySelectorAll('.tl-card').length).toBe(0); // the old detail went with the old timeline
  });

  it('asks for the status window\'s lanes as their own part (PHASE-39 Q3a)', async () => {
    const { d, calls } = deps();
    const api = d.api;
    d.api = async <T>(method: 'GET' | 'POST' | 'PUT', path: string, ...rest: unknown[]) => {
      if (path.startsWith(`/v1/inspector/c/${id}?`) && !path.includes('part=')) {
        calls.push(`${method} ${path}`);
        return { html: '<details id="s-people"><summary><h2>Characters</h2></summary><div class="tl-lazy"></div></details>'
          + '<details id="s-status"><summary><h2>Status over time</h2></summary><div class="tl-lazy tl-status"></div>'
          + '</details>' } as T;
      }
      if (path.includes('part=status')) {
        calls.push(`${method} ${path}`);
        return { html: fragment('') } as T;
      }
      return (api as (...a: unknown[]) => Promise<T>)(method, path, ...rest);
    };
    await openPanel(d, 'inspector');
    await settle();
    panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!.click();
    await settle();
    const section = panel().querySelector<HTMLDetailsElement>('#s-status')!;
    section.open = true;
    section.dispatchEvent(new Event('toggle'));
    await settle();
    expect(calls.filter((c) => c.includes('part='))).toEqual([`GET /v1/inspector/c/${id}?part=status&lang=en`]);
    expect(Array.from(section.querySelectorAll<HTMLElement>('.tl-bar')).map((b) => b.style.left)).toEqual(['18.182%', '63.636%']);
    section.querySelector<HTMLElement>('.tl-span[data-span="recent"]')!.click();
    await settle();
    expect(calls.at(-1)).toBe(`GET /v1/inspector/c/${id}?part=status&span=recent&lang=en`);
  });
});

describe("this chat's pinned characters in the settings (PHASE-60 S8)", () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  const pinA = '0190f3a4-1b2c-7d3e-8f40-0000000000a1';
  const pinB = '0190f3a4-1b2c-7d3e-8f40-0000000000b2';
  const row = (name: string, extra: Record<string, unknown> = {}) =>
    ({ id: `e-${name}`, type: 'character', name, names: [name], mentions: 3, ...extra });
  const titles = { ko: '고정한 인물', en: 'Pinned characters' } as const;
  const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((r) => setTimeout(r, 0)); };
  const panel = () => document.getElementById('nmos-panel')!;
  const cardOf = (language: 'ko' | 'en') => [...panel().querySelectorAll<HTMLElement>('.card')]
    .find((c) => c.querySelector('h2')?.textContent === titles[language])!;

  /** A sidecar with the new screens, its hub on one chat, and that chat's entities (or a failing list). */
  async function open(language: 'ko' | 'en', entities: Record<string, unknown>[] | 'fail') {
    const calls: [string, string, unknown][] = [];
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT', address: string, body?: unknown) => {
        const path = address.split('?')[0]!;
        calls.push([method, path, body]);
        if (path === '/v1/views/hub') {
          return { html: '<div class="v"><a class="v-block" data-act="settings"><span>Settings</span></a></div>', conversation: id } as T;
        }
        if (path.startsWith('/v1/views/')) return { html: '<div class="v"></div>' } as T;
        if (path === `/v1/conversations/${id}/entities`) {
          if (entities === 'fail') throw new Error(`${path} -> HTTP 503`);
          return entities as T;
        }
        if (method === 'POST' && path.endsWith('/remove') && entities !== 'fail') {
          const at = entities.findIndex((e) => path.endsWith(`/repairs/${String(e.pinned)}/remove`));
          if (at >= 0) delete entities[at]!.pinned;
          return { removed: path.split('/').at(-2) } as T;
        }
        if (path.startsWith('/v1/conversations?')) return [] as T;
        if (path.includes('/status/candidates') || path.endsWith('/memory-mode')) throw new Error('404');
        return {} as T;
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language, connected: true,
        version: '0.6.0', features: { views: true }, last: null }),
      getArg: async (key) => (key === 'language' ? language : ''),
      setArg: async () => {},
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
      chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => 'host-chat-1' }),
      download: async () => 0,
    };
    await openPanel(d, 'status');
    await settle();
    panel().querySelector<HTMLAnchorElement>('a[data-act="settings"]')!.click();
    await settle();
    panel().querySelector<HTMLButtonElement>('.groups button[data-group="chat"]')!.click();
    await settle();
    return { calls };
  }

  it("lists the chat's pinned characters and unpins one", async () => {
    for (const language of ['ko', 'en'] as const) {
      const entities = [row('하나', { pinned: pinA }), row('카이토'), row('세라', { pinned: pinB }), row('유나', { persona: true })];
      const { calls } = await open(language, entities);
      const card = cardOf(language);
      expect(card.closest('[data-group="chat"]')).not.toBeNull();
      expect(card.querySelector('p.sub')!.textContent).toContain(language === 'en' ? 'part of the memory budget' : '기억 예산의 일부');
      const unpin = language === 'en' ? 'Unpin' : '고정 풀기';
      const rows = () => [...card.querySelectorAll('button')].filter((b) => b.textContent === unpin)
        .map((b) => b.previousElementSibling!.textContent);
      expect(rows()).toEqual(['하나', '세라']);
      const before = calls.length;
      [...card.querySelectorAll('button')].find((b) => b.previousElementSibling?.textContent === '세라')!.click();
      await settle();
      expect(calls.slice(before)).toEqual([['POST', `/v1/conversations/${id}/repairs/${pinB}/remove`, {}],
        ['GET', `/v1/conversations/${id}/entities`, undefined]]);
      expect(rows()).toEqual(['하나']);
      expect(card.querySelector('.msg')!.textContent).toBe(language === 'en' ? 'Unpinned' : '고정을 풀었습니다');
      document.body.replaceChildren();
    }
  });

  it('says so when nothing is pinned', async () => {
    for (const language of ['ko', 'en'] as const) {
      await open(language, [row('하나'), row('카이토')]);
      const line = cardOf(language).querySelector('.muted')!;
      expect(line.textContent).toBe(language === 'en' ? "No pinned characters. Pin one from a person's page."
        : '고정한 인물이 없습니다. 인물 페이지에서 고정할 수 있습니다.');
      expect(cardOf(language).querySelector('button')).toBeNull();
      document.body.replaceChildren();
    }
  });

  it('says it could not load the list, and the rest of the page still shows', async () => {
    for (const language of ['ko', 'en'] as const) {
      await open(language, 'fail');
      const line = cardOf(language).querySelector('.muted')!;
      expect(line.textContent).toBe(language === 'en' ? 'Could not load the pinned characters.' : '고정한 인물 목록을 불러오지 못했습니다.');
      const page = panel().querySelector<HTMLElement>('[data-group="chat"]:not(button)')!;
      expect(page.textContent).toContain(language === 'en' ? 'Extract all history' : '과거 전체 추출');
      expect(page.querySelector('.maint-list')).not.toBeNull();
      document.body.replaceChildren();
    }
  });
});
