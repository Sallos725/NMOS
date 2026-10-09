// Status-rule drafts and templates only; Python pattern validation and activation belong to the sidecar.
export type ParserRule = Record<string, unknown>;
export interface ParserPreset { name: string; rules: ParserRule[] }
export type ParserDraft = { ok: true; rules: ParserRule[] } | { ok: false; error: 'blank' | 'json' | 'shape' };

export function parserDraft(text: string): ParserDraft {
  if (!text.trim()) return { ok: false, error: 'blank' };
  let spec: unknown;
  try { spec = JSON.parse(text); } catch { return { ok: false, error: 'json' }; }
  if (!spec || typeof spec !== 'object' || Array.isArray(spec) || !('rules' in spec)
    || !Array.isArray(spec.rules) || spec.rules.some((r) => !r || typeof r !== 'object' || Array.isArray(r))) {
    return { ok: false, error: 'shape' };
  }
  return { ok: true, rules: spec.rules as ParserRule[] };
}

/** A preset never remembers the card it was copied from. Applying it always has an explicit target. */
export function presetRules(rules: ParserRule[]): ParserRule[] {
  return rules.map(({ card: _card, ...rule }) => rule);
}

export function parserBindings(spec: unknown): { cards: { name: string; count: number }[]; unbound: number } {
  const parsed = parserDraft(JSON.stringify(spec) ?? '');
  const cards = new Map<string, number>();
  let unbound = 0;
  if (parsed.ok) for (const rule of parsed.rules) {
    if (typeof rule.card !== 'string' || !rule.card.trim()) unbound += 1;
    else cards.set(rule.card, (cards.get(rule.card) ?? 0) + 1);
  }
  return { cards: [...cards].map(([name, count]) => ({ name, count })), unbound };
}
