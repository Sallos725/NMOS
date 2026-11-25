// @vitest-environment happy-dom
// PHASE-68: host chat scan, pure orphan helpers, and Settings -> Backup orphan cleanup card.
import { afterEach, describe, expect, it } from 'vitest';
import type { StatusInfo } from '../src/core';
import { createChatSwitch } from '../src/chatoff';
import { scanHostChats } from '../src/host';
import { chunkIds, orphanLabel, parseHostCharacters, selectionSummary, type HostChatScan, type OrphanPreview,
  type OrphanRow } from '../src/orphans';
import { openPanel, type PanelDeps } from '../src/ui';

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  document.body.replaceChildren();
  document.head.replaceChildren();
  delete (globalThis as { risuai?: unknown }).risuai;
});

describe('parseHostCharacters & scanHostChats (H22)', () => {
  it('extracts deduplicated chat IDs across characters and placeholders', () => {
    const out = parseHostCharacters({
      characters: [
        { name: 'Hana', chats: [{ id: 'c-1', _placeholder: true, message: [] }, { id: 'c-2' }, { id: 'c-1' }] },
        { name: 'Kaito', chats: [{ id: 'c-3' }, { id: '   ' }, { id: '' }, { id: 123 }, null] },
        { name: 'Empty', chats: [] },
      ],
    });
    expect(out).toEqual({ ok: true, chatIds: ['c-1', 'c-2', 'c-3'], characterCount: 3 });
  });

  it('fails closed on denied permission (null) or malformed DB shape', () => {
    expect(parseHostCharacters(null)).toEqual({ ok: false, reason: 'denied' });
    expect(parseHostCharacters(undefined)).toEqual({ ok: false, reason: 'denied' });
    expect(parseHostCharacters({})).toEqual({ ok: false, reason: 'invalid' });
    expect(parseHostCharacters({ characters: 'bad' })).toEqual({ ok: false, reason: 'invalid' });
    expect(parseHostCharacters({ characters: [{ chats: 'not-an-array' }] })).toEqual({ ok: false, reason: 'invalid' });
    expect(parseHostCharacters({ characters: [42] })).toEqual({ ok: false, reason: 'invalid' });
  });

  it('calls risuai.getDatabase(["characters"]) on demand and handles missing/throwing API', async () => {
    (globalThis as { risuai?: unknown }).risuai = {};
    expect(await scanHostChats()).toEqual({ ok: false, reason: 'unsupported' });

    const calls: string[][] = [];
    (globalThis as { risuai?: unknown }).risuai = {
      getDatabase: async (keys: string[]) => {
        calls.push(keys);
        return { characters: [{ chats: [{ id: 'chat-a' }] }] };
      },
    };
    expect(await scanHostChats()).toEqual({ ok: true, chatIds: ['chat-a'], characterCount: 1 });
    expect(calls).toEqual([['characters']]);

    (globalThis as { risuai?: unknown }).risuai = {
      getDatabase: async () => null,
    };
    expect(await scanHostChats()).toEqual({ ok: false, reason: 'denied' });

    (globalThis as { risuai?: unknown }).risuai = {
      getDatabase: async () => { throw new Error('bridge error'); },
    };
    expect(await scanHostChats()).toEqual({ ok: false, reason: 'invalid' });
  });
});

describe('pure orphan helpers', () => {
  const sampleRows: OrphanRow[] = [
    {
      id: '01900000-0000-7000-8000-000000000001',
      host_chat_ref: 'ref-1',
      character: 'Hana',
      chat: 'Harbor',
      messages: 12,
      commits: 2,
      created_at: '2026-11-20T01:00:00Z',
      last_retrieval: '2026-11-21T02:00:00Z',
      carried_by: [],
      branch_children: 0,
    },
    {
      id: '01900000-0000-7000-8000-000000000002',
      host_chat_ref: 'ref-2',
      character: 'Kaito',
      chat: 'Tower',
      messages: 30,
      commits: 4,
      created_at: '2026-11-18T01:00:00Z',
      last_retrieval: null,
      carried_by: [
        { id: 'live-target', character: 'Kaito', chat: 'Season 2', mode: 'continue', target_missing: false },
        { id: 'dead-target', character: 'Sera', chat: 'Old', mode: 'regression', target_missing: true },
      ],
      branch_children: 1,
    },
  ];

  it('computes selection state, indeterminate flag, total messages, and active carry targets', () => {
    expect(selectionSummary(sampleRows, new Set())).toEqual({
      selectedCount: 0, totalCount: 2, allSelected: false, indeterminate: false, totalMessages: 0, activeCarryTargets: [],
    });
    const one = selectionSummary(sampleRows, new Set([sampleRows[0].id]));
    expect(one.allSelected).toBe(false);
    expect(one.indeterminate).toBe(true);
    expect(one.totalMessages).toBe(12);
    expect(one.activeCarryTargets).toEqual([]);

    const all = selectionSummary(sampleRows, new Set(sampleRows.map((r) => r.id)));
    expect(all.allSelected).toBe(true);
    expect(all.indeterminate).toBe(false);
    expect(all.totalMessages).toBe(42);
    expect(all.activeCarryTargets.map((x) => x.id)).toEqual(['live-target']);
  });

  it('formats labels and chunks batch IDs cleanly', () => {
    expect(orphanLabel({ character: 'Hana', chat: 'Harbor' }, '(unnamed)')).toBe('Hana · Harbor');
    expect(orphanLabel({ character: 'Hana', chat: 'Hana' }, '(unnamed)')).toBe('Hana');
    expect(orphanLabel({ host_chat_ref: 'abcdef123456' }, '(unnamed)')).toBe('abcdef12');
    expect(chunkIds(['a', 'b', 'c', 'd', 'e'], 2)).toEqual([['a', 'b'], ['c', 'd'], ['e']]);
  });
});

describe('Settings -> Backup orphan cleanup card (PHASE-68)', () => {
  const baseConfig = {
    llm: { url: 'https://llm.example/v1', model: 'm', api_key_set: true, json_mode: true },
    embeddings: { url: '', model: '', api_key_set: false, query_instruction: '' },
    recall: { threshold: 0.3, vector_min_sim: 0.3, top_k: 4, facts_limit: 6 },
    extraction: { backfill: 20 },
    parsers: { rules: null, source: 'none', active_rules: 0, errors: [] as string[] },
  };

  function setup(opts: {
    scan: HostChatScan;
    preview?: OrphanPreview;
    onDelete?: (ids: string[]) => unknown;
    previewError?: Error;
  }) {
    const calls: [string, string, unknown][] = [];
    const args: Record<string, string> = { sidecar_url: 'http://127.0.0.1:8790', language: 'en' };
    const d: PanelDeps = {
      api: async <T>(method: 'GET' | 'POST' | 'PUT' | 'DELETE', path: string, body?: unknown) => {
        calls.push([method, path, body]);
        if (path === '/v1/conversations/orphans/preview') {
          if (opts.previewError) throw opts.previewError;
          return (opts.preview ?? { host: 'pocketrisu', total_host_conversations: 0, matched_active: 0, orphans: [] }) as T;
        }
        if (path === '/v1/conversations/delete-batch') {
          const ids = (body as { ids: string[] }).ids;
          if (opts.onDelete) return opts.onDelete(ids) as T;
          return {
            deleted: ids.map((id) => ({ id, counts: { messages: 10, revisions: 10, carry_links: 0 } })),
            not_found: [],
            totals: { conversations: ids.length, messages: ids.length * 10, revisions: ids.length * 10, carry_links: 0 },
          } as T;
        }
        return baseConfig as T;
      },
      status: async () => ({
        enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.6.0', features: { extraction: true }, last: null,
      } as StatusInfo),
      getArg: async (k) => args[k] ?? '',
      setArg: async (k, v) => { args[k] = String(v); },
      show: async () => {},
      hide: async () => {},
      hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
      chat: createChatSwitch({
        getArg: async (k) => args[k] ?? '',
        setArg: async (k, v) => { args[k] = v; },
        currentChatId: async () => 'live-chat',
      }),
      scanHostChats: async () => opts.scan,
      download: async () => 0,
    };
    return { d, calls };
  }

  const orphanPreview: OrphanPreview = {
    host: 'pocketrisu',
    total_host_conversations: 4,
    matched_active: 2,
    orphans: [
      {
        id: '01900000-0000-7000-8000-000000000011',
        host_chat_ref: 'gone-1',
        character: 'Hana',
        chat: 'Old Harbor',
        messages: 15,
        commits: 2,
        created_at: '2026-11-20T01:00:00Z',
        last_retrieval: '2026-11-21T02:00:00Z',
        carried_by: [],
        branch_children: 0,
      },
      {
        id: '01900000-0000-7000-8000-000000000012',
        host_chat_ref: 'gone-2',
        character: 'Kaito',
        chat: 'Season 1',
        messages: 25,
        commits: 3,
        created_at: '2026-11-18T01:00:00Z',
        last_retrieval: null,
        carried_by: [
          { id: '01900000-0000-7000-8000-000000000099', character: 'Kaito', chat: 'Season 2', mode: 'continue', target_missing: false },
        ],
        branch_children: 0,
      },
    ],
  };

  it('scans, starts unchecked (Q1 a), warns on carry source while selectable, syncs Select all, and requires 2 clicks', async () => {
    const { d, calls } = setup({
      scan: { ok: true, chatIds: ['live-1', 'live-2'], characterCount: 2 },
      preview: orphanPreview,
      onDelete: (ids) => ({
        deleted: ids.map((id) => ({ id, counts: { messages: 20, revisions: 20, carry_links: 1 } })),
        not_found: [],
        totals: { conversations: ids.length, messages: 40, revisions: 40, carry_links: 1 },
      }),
    });
    await openPanel(d, 'settings');
    await settle();

    const card = document.getElementById('nmos-orphans')!;
    expect(card).toBeTruthy();
    const scanBtn = card.querySelectorAll('button')[0];
    const deleteBtn = card.querySelectorAll('button')[1];
    const selectAll = card.querySelector<HTMLInputElement>('.orph-select-all')!;

    scanBtn.click();
    await settle();

    // Preview called with active_chat_refs
    expect(calls.find((c) => c[1] === '/v1/conversations/orphans/preview')?.[2]).toEqual({
      host: 'pocketrisu',
      active_chat_refs: ['live-1', 'live-2'],
    });

    const rowBoxes = Array.from(card.querySelectorAll<HTMLInputElement>('input[data-orph-id]'));
    expect(rowBoxes).toHaveLength(2);
    // Q1 (a): all unchecked initially; delete disabled
    expect(rowBoxes.every((b) => !b.checked)).toBe(true);
    expect(selectAll.checked).toBe(false);
    expect(selectAll.indeterminate).toBe(false);
    expect(deleteBtn.disabled).toBe(true);
    // Carry warning badge shown on row 2 while checkbox remains enabled
    expect(card.textContent).toContain('Kaito · Season 2');
    expect(rowBoxes[1].disabled).toBe(false);

    // Check first row -> indeterminate select-all, no carry banner
    rowBoxes[0].checked = true;
    rowBoxes[0].dispatchEvent(new Event('change'));
    expect(selectAll.checked).toBe(false);
    expect(selectAll.indeterminate).toBe(true);
    expect(deleteBtn.disabled).toBe(false);
    const banner = card.querySelector<HTMLElement>('.orph-banner')!;
    expect(banner.style.display).toBe('none');

    // First click arms delete; changing checkbox immediately disarms it
    deleteBtn.click();
    expect(deleteBtn.textContent).toContain('Really delete (1');
    expect(calls.filter((c) => c[1] === '/v1/conversations/delete-batch')).toHaveLength(0);

    // Click Select all -> checks both (including carry source), disarms, shows carry banner
    selectAll.checked = true;
    selectAll.dispatchEvent(new Event('change'));
    expect(rowBoxes.every((b) => b.checked)).toBe(true);
    expect(selectAll.indeterminate).toBe(false);
    expect(deleteBtn.textContent).toContain('Delete 2 selected');
    expect(banner.style.display).not.toBe('none');
    expect(banner.textContent).toContain('Kaito · Season 2');

    // First click arms with carry warning; second click executes delete-batch
    deleteBtn.click();
    expect(deleteBtn.textContent).toContain('Really delete (2');
    expect(card.querySelector('.msg')!.textContent).toContain('Carry links for 1 active chat');
    deleteBtn.click();
    await settle();

    const delCall = calls.find((c) => c[1] === '/v1/conversations/delete-batch');
    expect(delCall?.[2]).toEqual({ ids: orphanPreview.orphans.map((o) => o.id) });
    expect(card.querySelectorAll('input[data-orph-id]')).toHaveLength(0);
    expect(card.querySelector('.msg')!.textContent).toContain('Deleted 2 conversation(s)');
    expect(card.querySelector('.msg')!.textContent).toContain('1 carry link');
  });

  it('blocks scan when permission is denied or host returns 0 active chats (Q3 a)', async () => {
    const denied = setup({ scan: { ok: false, reason: 'denied' } });
    await openPanel(denied.d, 'settings');
    await settle();
    const card1 = document.getElementById('nmos-orphans')!;
    card1.querySelectorAll('button')[0].click();
    await settle();
    expect(denied.calls.filter((c) => c[1].includes('orphans'))).toHaveLength(0);
    expect(card1.querySelector('.msg')!.textContent).toContain('permission was denied');

    document.body.replaceChildren();
    const empty = setup({ scan: { ok: true, chatIds: [], characterCount: 0 } });
    await openPanel(empty.d, 'settings');
    await settle();
    const card2 = document.getElementById('nmos-orphans')!;
    card2.querySelectorAll('button')[0].click();
    await settle();
    expect(empty.calls.filter((c) => c[1].includes('orphans'))).toHaveLength(0);
    expect(card2.querySelector('.msg')!.textContent).toContain('0 active chats');
  });

  it('shows a clear message when all conversations exist in the host or sidecar is older', async () => {
    const clean = setup({
      scan: { ok: true, chatIds: ['live-1'], characterCount: 1 },
      preview: { host: 'pocketrisu', total_host_conversations: 1, matched_active: 1, orphans: [] },
    });
    await openPanel(clean.d, 'settings');
    await settle();
    const card1 = document.getElementById('nmos-orphans')!;
    card1.querySelectorAll('button')[0].click();
    await settle();
    expect(card1.querySelector('.msg')!.textContent).toContain('All NMOS conversations exist');

    document.body.replaceChildren();
    const oldSidecar = setup({
      scan: { ok: true, chatIds: ['live-1'], characterCount: 1 },
      previewError: new Error('/v1/conversations/orphans/preview -> HTTP 404: Not Found'),
    });
    await openPanel(oldSidecar.d, 'settings');
    await settle();
    const card2 = document.getElementById('nmos-orphans')!;
    card2.querySelectorAll('button')[0].click();
    await settle();
    expect(card2.querySelector('.msg')!.textContent).toContain('does not support orphan cleanup');
  });

  it('updates remaining rows and summary counts cleanly after partial deletion', async () => {
    const { d } = setup({
      scan: { ok: true, chatIds: ['live-1', 'live-2'], characterCount: 2 },
      preview: orphanPreview,
      onDelete: (ids) => ({
        deleted: ids.map((id) => ({ id, counts: { messages: 15, revisions: 15, carry_links: 0 } })),
        not_found: [],
        totals: { conversations: ids.length, messages: 15, revisions: 15, carry_links: 0 },
      }),
    });
    await openPanel(d, 'settings');
    await settle();
    const card = document.getElementById('nmos-orphans')!;
    const scanBtn = card.querySelectorAll('button')[0];
    const deleteBtn = card.querySelectorAll('button')[1];
    scanBtn.click();
    await settle();

    // Select only the first (non-carry) row and confirm delete
    const firstBox = card.querySelectorAll<HTMLInputElement>('input[data-orph-id]')[0];
    firstBox.checked = true;
    firstBox.dispatchEvent(new Event('change'));
    deleteBtn.click();
    deleteBtn.click();
    await settle();

    expect(card.querySelectorAll('input[data-orph-id]')).toHaveLength(1);
    expect(card.textContent).toContain('1 of 3 NMOS conversations are missing');
    expect(card.textContent).toContain('Kaito · Season 1');
    expect(deleteBtn.disabled).toBe(true);
  });
});
