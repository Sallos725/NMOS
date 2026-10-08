// Restore from the panel (PHASE-38): an archive uploaded in chunks, checked, then restored by the sidecar.
// The panel reads one slice of the file at a time; a Blob is not a nativeFetch body, so each slice is read into bytes
// and sent as base64 in JSON (H23). Check and restore run in the sidecar's background; the panel polls.
import { sha256HexOf } from './hash';

export type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';
export type Api = <T>(method: Method, path: string, body?: unknown, timeoutMs?: number) => Promise<T>;

export interface ArchiveConversation {
  id: string; host: string; host_chat_ref: string; character: string | null; chat: string | null; here: boolean;
}
export interface ArchiveSummary {
  scope: 'install' | 'conversations'; nmos_version: string | null; created_at: string | null; schema: string;
  migrations: string[]; conversations: ArchiveConversation[]; settings_added: { key: string; value?: unknown }[];
}
export interface RestoreResult {
  conversations: { id: string; host_chat_ref: string; character?: string | null }[];
  rows: Record<string, number>; renumbered: string[]; settings_kept: string[]; links_cleared: string[];
  migrated: string[]; queued_jobs?: number;
}
export interface UploadView {
  id: string; state: 'receiving' | 'received' | 'checking' | 'checked' | 'refused' | 'restoring' | 'restored' | 'failed';
  bytes: number; received: number; chunk_bytes: number; detail?: string; summary?: ArchiveSummary; result?: RestoreResult;
}

/** base64 of bytes, built in slices so a large chunk does not overflow the argument list. */
export function base64Of(bytes: Uint8Array): string {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

const CHUNK_TIMEOUT_MS = 120_000;

/** Upload `file` chunk by chunk (one slice in memory at a time), retrying a chunk once; `progress(sent, total)`. */
export async function uploadArchive(api: Api, file: Blob, progress: (sent: number, total: number) => void): Promise<UploadView> {
  const up = await api<UploadView>('POST', '/v1/archive/uploads', { bytes: file.size });
  const size = up.chunk_bytes;
  progress(0, file.size);
  for (let index = 0, offset = 0; offset < file.size; index++, offset += size) {
    const bytes = await file.slice(offset, offset + size).arrayBuffer();
    const body = { data: base64Of(new Uint8Array(bytes)), sha256: await sha256HexOf(bytes) };
    const path = `/v1/archive/uploads/${up.id}/chunks/${index}`;
    try {
      await api('PUT', path, body, CHUNK_TIMEOUT_MS);
    } catch {
      await api('PUT', path, body, CHUNK_TIMEOUT_MS);  // the same chunk again: the sidecar takes it once
    }
    progress(Math.min(offset + size, file.size), file.size);
  }
  return up;
}

/** Poll the upload until it reaches one of `states`. */
export async function waitFor(api: Api, id: string, states: UploadView['state'][],
                              sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
                              everyMs = 1000): Promise<UploadView> {
  for (;;) {
    const view = await api<UploadView>('GET', `/v1/archive/uploads/${id}`);
    if (states.includes(view.state)) return view;
    await sleep(everyMs);
  }
}
