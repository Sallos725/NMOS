// What this chat's memory cost in NMOS's own model calls (PHASE-17 Q4, ADR 0051): one line for the Status tab, from
// the sidecar's coverage with `usage`. Only what the provider reported; no money.
import { t, type Lang } from './i18n';

/** `usage.total` of `GET /v1/conversations/{id}/coverage?usage=true`. */
export interface UsageTotal {
  calls: number;
  reported: number;
  input: number;
  output: number;
  cached: number;
  /** Results from before usage was recorded (NMOS 0.2.0 and earlier); older sidecars send none. */
  not_recorded?: number;
  /** Calls that reported input / output tokens (embeddings report input only). Older sidecars send none. */
  input_reported?: number;
  output_reported?: number;
}

const count = (n: number) => n.toLocaleString('en-US');
/** Korean strings put the unit (회) themselves; English needs "1 call" but "2 calls". */
const calls = (n: number, lang: Lang) => (lang === 'en' ? `${count(n)} call${n === 1 ? '' : 's'}` : count(n));

export function usageText(u: UsageTotal, lang: Lang): string {
  const older = u.not_recorded ?? 0;
  if (!u.calls) return t(lang, older ? 'usage.older_only' : 'usage.none');
  const before = older ? t(lang, 'usage.older', { n: count(older) }) : '';
  if (!u.reported) return t(lang, 'usage.unreported', { calls: calls(u.calls, lang) }) + before;
  const cached = u.cached ? t(lang, 'usage.cached', { n: count(u.cached) }) : '';
  const partial = u.reported < u.calls ? t(lang, 'usage.partial', { r: count(u.reported), calls: calls(u.calls, lang) }) : '';
  // A count no call reported (an embedding's output; a provider that gives only one side) is left out, never 0.
  const sides = [u.input_reported === 0 ? '' : t(lang, 'usage.input', { n: count(u.input) }),
    u.output_reported === 0 ? '' : t(lang, 'usage.output', { n: count(u.output) })].filter(Boolean).join(' · ');
  // Neither side reported, only cached (or reasoning) tokens: say those, not an empty "· tokens".
  if (!sides) {
    const only = u.cached ? ` · ${t(lang, 'usage.cached_side', { n: count(u.cached) })}` : '';
    return t(lang, 'usage.calls', { calls: calls(u.calls, lang) }) + only + partial + before;
  }
  return t(lang, 'usage.line', { calls: calls(u.calls, lang), sides, cached }) + partial + before;
}
