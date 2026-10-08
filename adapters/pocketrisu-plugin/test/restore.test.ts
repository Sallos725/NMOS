// @vitest-environment happy-dom
// Restore from the panel (PHASE-38): the chunked upload, the polling, and the Settings card.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { createChatSwitch } from '../src/chatoff';
import { base64Of, uploadArchive, waitFor, type Method, type UploadView } from '../src/restore';
import { openPanel, type PanelDeps } from '../src/ui';

const bytesOf = (n: number) => Uint8Array.from({ length: n }, (_, i) => (i * 7 + 3) % 256);
const sha = (b: Uint8Array | Buffer) => createHash('sha256').update(b).digest('hex');

/** A file that counts how it is read: by slices only, never whole. */
function countedFile(data: Uint8Array) {
  const file = new Blob([data]);
  const reads = { slices: 0, whole: 0 };
  const slice = file.slice.bind(file);
  return {
    reads,
    file: {
      size: file.size,
      slice: (start: number, end: number) => { reads.slices++; return slice(start, end); },
      arrayBuffer: () => { reads.whole++; return file.arrayBuffer(); },
    } as unknown as Blob,
  };
}

describe('the upload', () => {
  it('encodes base64 as the sidecar decodes it', () => {
    const data = bytesOf(100_000);
    expect(base64Of(data)).toBe(Buffer.from(data).toString('base64'));
  });

  it('sends the file in order, one slice at a time, each chunk with its hash', async () => {
    const data = bytesOf(2500);
    const { file, reads } = countedFile(data);
    const sent: { path: string; data: Buffer; sha256: string }[] = [];
    const progress: number[] = [];
    const api = async <T>(method: Method, path: string, body?: unknown): Promise<T> => {
      if (method === 'POST') {
        expect(body).toEqual({ bytes: 2500 });
        return { id: 'u1', state: 'receiving', bytes: 2500, received: 0, chunk_bytes: 1000 } as T;
      }
      const b = body as { data: string; sha256: string };
      sent.push({ path, data: Buffer.from(b.data, 'base64'), sha256: b.sha256 });
      return {} as T;
    };
    await uploadArchive(api, file, (s) => progress.push(s));
    expect(sent.map((s) => s.path)).toEqual(['/v1/archive/uploads/u1/chunks/0', '/v1/archive/uploads/u1/chunks/1',
      '/v1/archive/uploads/u1/chunks/2']);
    expect(Buffer.concat(sent.map((s) => s.data))).toEqual(Buffer.from(data));
    for (const s of sent) expect(s.sha256).toBe(sha(s.data));
    expect(progress).toEqual([0, 1000, 2000, 2500]);
    expect(reads).toEqual({ slices: 3, whole: 0 });  // acceptance 4: never the whole file at once
  });

  it('sends a chunk again once when its answer is lost, then gives up', async () => {
    const tries: string[] = [];
    let fail = 1;
    const api = async <T>(method: Method, path: string): Promise<T> => {
      if (method === 'POST') return { id: 'u2', chunk_bytes: 10 } as T;
      tries.push(path);
      if (fail-- > 0) throw new Error('timeout');
      return {} as T;
    };
    await uploadArchive(api, new Blob([bytesOf(15)]), () => {});
    expect(tries).toEqual(['/v1/archive/uploads/u2/chunks/0', '/v1/archive/uploads/u2/chunks/0',
      '/v1/archive/uploads/u2/chunks/1']);
    fail = 2;
    await expect(uploadArchive(api, new Blob([bytesOf(5)]), () => {})).rejects.toThrow('timeout');
  });

  it('polls until the upload reaches a wanted state', async () => {
    const states: UploadView['state'][] = ['checking', 'checking', 'checked'];
    const api = async <T>(): Promise<T> => ({ id: 'u3', state: states.shift() } as T);
    const slept: number[] = [];
    const view = await waitFor(api, 'u3', ['checked', 'refused'], async (ms) => { slept.push(ms); }, 500);
    expect(view.state).toBe('checked');
    expect(slept).toEqual([500, 500]);
  });
});

describe('the Settings card', () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  const config = {
    llm: { url: '', model: '', api_key_set: false, json_mode: true },
    embeddings: { url: '', model: '', api_key_set: false, query_instruction: '' },
    recall: { threshold: 0.3, vector_min_sim: 0.3, top_k: 4, facts_limit: 6 },
    extraction: { backfill: 20 },
    parsers: { rules: null, source: 'none', active_rules: 0, errors: [] as string[] },
  };
  const summary = (here: boolean) => ({
    scope: 'install', nmos_version: '0.4.0', created_at: '2026-10-08T07:00:00+00:00', schema: '0028_reveal_checks.sql',
    migrations: [], settings_added: [{ key: 'llm_url', value: 'https://llm.example/v1' }, { key: 'recall_top_k' }],
    conversations: [{ id: 'c1', host: 'pocketrisu', host_chat_ref: 'chat-1', character: 'Mina', chat: 'Tower', here }],
  });

  function deps(here: boolean) {
    const calls: [string, string][] = [];
    let state: UploadView['state'] = 'receiving';
    const d: PanelDeps = {
      api: async <T>(method: Method, path: string): Promise<T> => {
        calls.push([method, path]);
        if (path === '/v1/config') return config as T;
        if (path === '/v1/archive/uploads') return { id: 'u9', state, bytes: 30, received: 0, chunk_bytes: 16 } as T;
        if (path.endsWith('/check')) { state = 'checked'; return {} as T; }
        if (path.endsWith('/restore')) { state = 'restored'; return {} as T; }
        if (path === '/v1/archive/uploads/u9' && method === 'GET') {
          return { id: 'u9', state, bytes: 30, received: 30, chunk_bytes: 16, summary: summary(here),
            ...(state === 'restored' ? { result: { conversations: [{ id: 'c1', host_chat_ref: 'chat-1' }], rows: {},
              renumbered: [], settings_kept: [], links_cleared: [], migrated: [], queued_jobs: 12 } } : {}) } as T;
        }
        return {} as T;
      },
      status: async () => ({ enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: 'en', connected: true,
        version: '0.4.0', features: { extraction: true }, last: null }),
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

  async function pick(panel: HTMLElement): Promise<void> {
    const input = panel.querySelector('input[type="file"][accept=".zip,application/zip"]') as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: [new File([bytesOf(30)], 'nmos-all.nmos.zip')], configurable: true });
    input.dispatchEvent(new Event('change'));
  }

  const button = (panel: HTMLElement, text: string) =>
    [...panel.querySelectorAll('button')].find((b) => b.textContent === text) as HTMLButtonElement;

  it('uploads, shows what the archive holds, then restores', async () => {
    const { d, calls } = deps(false);
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    await pick(panel);
    await vi.waitFor(() => expect(panel.textContent).toContain('Mina — Tower'), { timeout: 5000 });
    expect(panel.textContent).toContain('The whole install · 1 chats · NMOS 0.4.0 · 2026-10-08');
    expect(panel.textContent).toContain('Settings it adds: llm_url = https://llm.example/v1, recall_top_k');
    expect(calls.filter(([m, p]) => m === 'PUT' && p.includes('/chunks/')).map(([, p]) => p))
      .toEqual(['/v1/archive/uploads/u9/chunks/0', '/v1/archive/uploads/u9/chunks/1']);
    const go = button(panel, 'Restore');
    expect(go.style.display).toBe('');
    expect(go.disabled).toBe(false);
    go.click();
    await vi.waitFor(() => expect(panel.textContent).toContain('Restored: 1 chats; 12 jobs queued.'), { timeout: 5000 });
    expect(calls.some(([m, p]) => m === 'POST' && p === '/v1/archive/uploads/u9/restore')).toBe(true);
    expect(button(panel, 'Restore').style.display).toBe('none');
  });

  it('a chat already here blocks the restore, and cancel discards the upload', async () => {
    const { d, calls } = deps(true);
    await openPanel(d, 'settings');
    const panel = document.getElementById('nmos-panel')!;
    await pick(panel);
    await vi.waitFor(() => expect(panel.textContent).toContain('Chats already here block the restore.'), { timeout: 5000 });
    expect(panel.textContent).toContain('Mina — Tower (already here)');
    expect(button(panel, 'Restore').disabled).toBe(true);
    button(panel, 'Cancel').click();
    await vi.waitFor(() => expect(calls).toContainEqual(['DELETE', '/v1/archive/uploads/u9']));
    expect(calls.some(([, p]) => p.endsWith('/restore'))).toBe(false);
  });
});
