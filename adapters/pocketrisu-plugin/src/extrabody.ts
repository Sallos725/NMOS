// Extra request values for the extraction model (PHASE-61 S4, ADR 0088): one JSON object the owner writes, and the
// reasoning-effort dropdown as a view of it. Validation, limits and refusals are the sidecar's.

import { canonicalJson } from './canonical';

/** The values OpenRouter's documentation lists for `reasoning.effort` (PHASE-61 Q3). */
export const EFFORTS = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'] as const;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

/** The object to send, or null when the text is not a JSON object; an empty text is `{}`. */
export function bodyOf(text: string): Obj | null {
  if (!text.trim()) return {};
  try {
    const v: unknown = JSON.parse(text);
    return isObj(v) ? v : null;
  } catch { return null; }
}

/** A body as the text area shows it: indented JSON, or nothing for `{}` (what a fresh load shows). */
export function showBody(body: Obj): string {
  return Object.keys(body).length ? JSON.stringify(body, null, 2) : '';
}

/** What a text means for saving: the same string for the same object whatever its spacing or key order; a text that
 *  is not a JSON object stays itself, so it never equals a valid one. */
export function bodyKey(text: string): string {
  const body = bodyOf(text);
  return body ? canonicalJson(body) : `!${text}`;
}

export type EffortState = { state: 'none' } | { state: 'value'; effort: string } | { state: 'custom' } | { state: 'invalid' };

/** What the dropdown shows for a text. */
export function effortOf(text: string): EffortState {
  const body = bodyOf(text);
  if (!body) return { state: 'invalid' };
  if (!('reasoning' in body)) return { state: 'none' };
  const r = body.reasoning;
  if (!isObj(r)) return { state: 'custom' };
  if (!('effort' in r)) return { state: 'none' };
  return typeof r.effort === 'string' && (EFFORTS as readonly string[]).includes(r.effort)
    ? { state: 'value', effort: r.effort } : { state: 'custom' };
}

/** The text with `reasoning.effort` set (every other key kept, in order), or removed for null, `reasoning` with it when
 *  that leaves it empty. A `reasoning` that is not an object is replaced by a value and left alone by null. A text that
 *  is not a JSON object comes back unchanged. */
export function withEffort(text: string, effort: string | null): string {
  const body = bodyOf(text);
  if (!body) return text;
  const r = body.reasoning;
  if (effort !== null) body.reasoning = isObj(r) ? Object.assign(r, { effort }) : { effort };
  else if (isObj(r) && 'effort' in r) {
    delete r.effort;
    if (!Object.keys(r).length) delete body.reasoning;
  }
  return showBody(body);
}

/** Whether a model address is OpenRouter's, where `reasoning.effort` is the unified field (PHASE-61 Q2). */
export function isOpenRouter(url: string): boolean {
  try {
    const host = new URL(url.trim()).hostname.toLowerCase();
    return host === 'openrouter.ai' || host.endsWith('.openrouter.ai');
  } catch { return false; }
}
