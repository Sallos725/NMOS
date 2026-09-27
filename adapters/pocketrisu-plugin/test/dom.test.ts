// @vitest-environment happy-dom
// DOM code (audit follow-up, 2026-09-27 review): the inspector sanitizer's tree walk and the settings panel.
import { afterEach, describe, expect, it } from 'vitest';
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
    const reserved = [...panel.querySelectorAll('input')].find((i) => i.value === '800')!;
    reserved.value = '99999';
    reserved.dispatchEvent(new Event('input', { bubbles: true }));
    (panel.querySelector('button.primary') as HTMLButtonElement).click();
    await settle();
    expect(calls.filter(([method]) => method === 'PUT')).toEqual([['PUT', '/v1/config',
      { llm_url: 'https://llm.example/v2', llm_model: 'm' }]]);  // no key typed: none sent
    expect(args.reserved_memory_tokens).toBe('20000');
  });
});
