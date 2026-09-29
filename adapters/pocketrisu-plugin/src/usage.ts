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
}

const count = (n: number) => n.toLocaleString('en-US');

export function usageText(u: UsageTotal, lang: Lang): string {
  if (!u.calls) return t(lang, 'usage.none');
  if (!u.reported) return t(lang, 'usage.unreported', { calls: count(u.calls) });
  const cached = u.cached ? t(lang, 'usage.cached', { n: count(u.cached) }) : '';
  const partial = u.reported < u.calls ? t(lang, 'usage.partial', { r: count(u.reported), calls: count(u.calls) }) : '';
  return t(lang, 'usage.line', { calls: count(u.calls), input: count(u.input), output: count(u.output), cached }) + partial;
}
