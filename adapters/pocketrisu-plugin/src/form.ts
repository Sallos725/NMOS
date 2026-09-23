// Settings form model: which sections changed, and the single sidecar update they add up to.

export type Section = 'conn' | 'llm' | 'emb' | 'tune' | 'rules';

/** Request-path deadline when the plugin arg is unset (0). 3 s: on PocketRisu v1.12.0 a warm
 *  generation needs ≈1.5 s at 5,000 messages and ≈2.7 s at 10,000 (docs/perf/scale.md). */
export const DEFAULT_DEADLINE_MS = 3000;
export const MAX_DEADLINE_MS = 30_000;
export const SECTIONS: Section[] = ['conn', 'llm', 'emb', 'tune', 'rules'];

export interface ModelValues { url: string; model: string; key: string }

export interface FormValues {
  conn: { url: string; route: string; enabled: boolean; reserved: string; deadline: string };
  llm: ModelValues;
  emb: ModelValues;
  tune: { threshold: string; minSim: string; topK: string; facts: string; backfill: string };
  rules: string;
}

/** Sections whose values differ from the last loaded or saved baseline. */
export function dirtySections(baseline: FormValues, current: FormValues): Section[] {
  return SECTIONS.filter((s) => JSON.stringify(baseline[s]) !== JSON.stringify(current[s]));
}

/** A number field as the sidecar expects it; anything unparsable is sent as typed so the sidecar
 *  rejects it with a message instead of it silently becoming 0 or a reset. */
function num(value: string): number | string {
  const n = Number(value.trim());
  return value.trim() !== '' && Number.isFinite(n) ? n : value;
}

/** One PUT /v1/config body for every changed server-side section (validated and saved atomically). */
export function configBody(dirty: Section[], v: FormValues): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const [section, prefix] of [['llm', 'llm'], ['emb', 'embed']] as const) {
    if (!dirty.includes(section)) continue;
    body[`${prefix}_url`] = v[section].url.trim();
    body[`${prefix}_model`] = v[section].model.trim();
    if (v[section].key.trim()) body[`${prefix}_api_key`] = v[section].key.trim();
  }
  if (dirty.includes('tune')) {
    Object.assign(body, {
      recall_threshold: num(v.tune.threshold), vector_min_sim: num(v.tune.minSim), recall_top_k: num(v.tune.topK),
      facts_limit: num(v.tune.facts), extract_backfill: num(v.tune.backfill),
    });
  }
  if (dirty.includes('rules')) body.parsers = v.rules.trim() ? v.rules : null;
  return body;
}

/** Plugin args for the connection section (stored in PocketRisu, not the sidecar). */
export function connArgs(v: FormValues['conn']): Record<string, string | number> {
  return {
    sidecar_url: v.url.trim(),
    route: v.route,
    disabled: v.enabled ? 0 : 1,
    reserved_memory_tokens: Number(v.reserved) || 600,
    deadline_ms: Math.min(MAX_DEADLINE_MS, Math.max(200, Math.floor(Number(v.deadline)) || DEFAULT_DEADLINE_MS)),
  };
}
