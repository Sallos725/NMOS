// Canonical JSON for revision hashing (format v1). Must match apps/sidecar/src/nmos_sidecar/canonical.py.

export function normalizeText(value: unknown): string {
  return String(value ?? '').normalize('NFC').replace(/\r\n/g, '\n');
}

export function canonicalize(value: unknown): unknown {
  if (value === null || typeof value !== 'object') {
    return typeof value === 'string' ? normalizeText(value) : value;
  }
  if (Array.isArray(value)) return value.map(canonicalize);
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(value).sort()) {
    const v = (value as Record<string, unknown>)[key];
    if (v !== undefined) out[key] = canonicalize(v);
  }
  return out;
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}
