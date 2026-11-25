// @vitest-environment happy-dom
// Wave 4 Inspector UI buttons: branch-inherit preview+confirm, attention_dismiss, told_retract, fact_hidden, fact_add.
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { bulkMark, repairAction } from '../src/inspector';
import { openPanel, type PanelDeps } from '../src/ui';

const id = '0190f3a4-1b2c-7d3e-8f40-123456789abc';
const settle = async () => { for (let i = 0; i < 6; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;

function makeDeps(pageHtml: string) {
  const calls: [string, string, unknown][] = [];
  const d: PanelDeps = {
    api: async <T>(method: 'GET' | 'POST' | 'PUT', address: string, body?: unknown) => {
      const path = address.replace(/\?.*$/, '');
      calls.push([method, path, body]);
      if (path === '/v1/inspector') return { html: `<a href="/inspector/c/${id}">chat</a>` } as T;
      if (path.startsWith(`/v1/inspector/c/${id}`)) return { html: pageHtml } as T;
      if (path === `/v1/conversations/${id}/branch-inherit`) {
        const dry = (body as { dry_run?: boolean })?.dry_run ?? true;
        return { status: 'done', dry_run: dry, prefix: 8,
          copied: { extractions: 4, summaries: 1, embeddings: 8, repairs: 2, links: 1 } } as T;
      }
      if (path === `/v1/conversations/${id}/messages`) {
        return [{ host_logical_id: 'msg-9', turn: 4, position: 8, role: 'char', name: 'Sera',
          preview: 'Sera arrived at the harbor.' }] as T;
      }
      if (path === `/v1/conversations/${id}/repairs`) return { repair: { id: 'r1' }, applied: true } as T;
      if (path.endsWith('/memory-mode') || path.endsWith('/status/candidates')) throw new Error('404');
      return {} as T;
    },
    status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
      version: '0.5.0', features: {}, last: null }),
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

async function openChat(d: PanelDeps): Promise<void> {
  await openPanel(d, 'inspector');
  await settle();
  panel().querySelector<HTMLAnchorElement>(`a[href="/inspector/c/${id}"]`)!.click();
  await settle();
}

describe('Wave 4 Inspector buttons', () => {
  afterEach(() => { document.body.replaceChildren(); document.head.replaceChildren(); });

  it('allows new repair and bulk kinds in inspector allowlists', () => {
    expect(repairAction(`branch_inherit:${id}`)).toEqual({ kind: 'branch_inherit', item: id, extra: null });
    expect(repairAction('attention_dismiss:42:role_held')).toEqual({ kind: 'attention_dismiss', item: '42', extra: 'role_held' });
    expect(repairAction('told_retract:55')).toEqual({ kind: 'told_retract', item: '55', extra: null });
    expect(repairAction('fact_hidden:77')).toEqual({ kind: 'fact_hidden', item: '77', extra: null });
    const bulk = bulkMark(JSON.stringify({
      g: 'role_held', l: 'Held',
      retract: { kind: 'attention_dismiss', item: '42', attention: 'role_held' },
    }));
    expect(bulk?.retract).toEqual({ kind: 'attention_dismiss', item: '42', attention: 'role_held' });
  });

  it('previews branch-inherit with dry_run:true then runs dry_run:false on confirm', async () => {
    const html = `<p class="muted">branched from origin <span class="rp" data-repair="branch_inherit:${id}"></span></p>`;
    const { d, calls } = makeDeps(html);
    await openChat(d);
    const btn = [...panel().querySelectorAll('button')].find((b) => b.textContent === 'Inherit from origin branch')!;
    expect(btn).toBeTruthy();
    btn.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/branch-inherit')
      && (b as { dry_run: boolean }).dry_run === true)).toBe(true);
    expect(panel().textContent).toContain('8 shared messages');
    const confirm = [...panel().querySelectorAll('button')].find((b) => b.textContent === 'Inherit now')!;
    confirm.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/branch-inherit')
      && (b as { dry_run: boolean }).dry_run === false)).toBe(true);
  });

  it('sends attention_dismiss, told_retract, fact_hidden, and fact_add repairs', async () => {
    const html = `<details id="s-attention" open><span class="rp" data-repair="attention_dismiss:101:role_held"></span></details>`
      + `<details id="s-told" open><p>Sera → Kaito: map <span class="rp" data-repair="told_retract:55"></span></p></details>`
      + `<details id="s-facts" open><table><tbody><tr><td>Sera <span class="rp" data-repair="fact_retract:77"></span></td></tr></tbody></table></details>`;
    const { d, calls } = makeDeps(html);
    await openChat(d);

    // attention_dismiss
    const dismissBtn = [...panel().querySelectorAll('button')].find((b) => b.textContent === 'Dismiss')!;
    dismissBtn.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>).kind === 'attention_dismiss'
      && (b as Record<string, unknown>).attention === 'role_held')).toBe(true);

    // fact_hidden (injected client-side next to fact_retract in #s-facts)
    const hidBtn = [...panel().querySelectorAll('button')].find((b) => b.textContent === 'Hidden')!;
    hidBtn.click();
    const who = panel().querySelector<HTMLInputElement>('input[placeholder="Character name"]')!;
    who.value = 'Kaito';
    const saveHid = [...who.parentElement!.querySelectorAll('button')].find((b) => b.textContent === 'Save')!;
    saveHid.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>).kind === 'fact_hidden'
      && (b as Record<string, unknown>).character === 'Kaito'
      && (b as Record<string, unknown>).hidden === true)).toBe(true);

    // fact_add form
    const addBtn = [...panel().querySelectorAll('button')].find((b) => b.textContent === 'Add fact')!;
    addBtn.click();
    await settle();
    const subj = panel().querySelector<HTMLInputElement>('input[placeholder="Subject"]')!;
    const val = panel().querySelector<HTMLInputElement>('input[placeholder="Value (optional)"]')!;
    subj.value = 'Sera';
    val.value = 'injured';
    const saveAdd = [...subj.closest('.card')!.querySelectorAll('button')].find((b) => b.textContent === 'Save')!;
    saveAdd.click();
    await settle();
    expect(calls.some(([m, p, b]) => m === 'POST' && p.endsWith('/repairs')
      && (b as Record<string, unknown>).kind === 'fact_add'
      && (b as Record<string, unknown>).item === 'msg-9'
      && ((b as Record<string, Record<string, unknown>>).fact?.subject === 'Sera'))).toBe(true);
  });
});
