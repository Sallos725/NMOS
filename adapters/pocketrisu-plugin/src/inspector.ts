// The sidecar's inspector pages, shown inside the NMOS panel. The sidecar escapes every value; this
// keeps only the markup those pages use, so nothing else can reach the plugin frame.

import type { Lang, StringKey } from './i18n';

const TAGS = new Set(['DIV', 'P', 'H1', 'H2', 'SPAN', 'B', 'BR', 'A', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD',
  'DETAILS', 'SUMMARY']);
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
// Section folds and the contents that links to them (`s-facts`, `#s-facts`).
const SECTION = /^s-[a-z]{1,20}$/;

/** The sidecar API path for an inspector link (`/inspector`, `/inspector/c/<id>`, `/inspector/c/<id>/e/<id>`), or null. */
export function inspectorApiPath(href: string | null): string | null {
  const m = new RegExp(`^/inspector(/c/${UUID}(?:/e/${UUID})?)?(?:[?#]|$)`, 'i').exec(href ?? '');
  return m ? `/v1/inspector${m[1] ?? ''}` : null;
}

/** The conversation id of an inspector conversation or character API path, or null. */
export function inspectorConversation(path: string): string | null {
  const m = new RegExp(`^/v1/inspector/c/(${UUID})(?:/e/${UUID})?$`, 'i').exec(path);
  return m ? (m[1] as string) : null;
}

/** The conversation and entity of an inspector character API path, or null. */
export function inspectorEntity(path: string): { conversation: string; entity: string } | null {
  const m = new RegExp(`^/v1/inspector/c/(${UUID})/e/(${UUID})$`, 'i').exec(path);
  return m ? { conversation: m[1] as string, entity: m[2] as string } : null;
}

/** An entity as `GET /v1/conversations/<id>/entities` lists it; `links` only from sidecars with ADR 0025. */
export interface EntityRow {
  id: string;
  type: string;
  name: string;
  names: string[];
  mentions: number;
  persona?: boolean;
  links?: { id: string; name: string; same_as: string }[];
  aliases?: { name: string; other: string; turn: number | null }[];
}

/** A repair the inspector marks for the panel (ADR 0044): what to do, to which item, and a character or field. */
export interface RepairAction { kind: string; item: string; extra: string | null }

const REPAIR = /^(thread_close|thread_reopen|secret_found_out|secret_keep|fact_retract|fact_correct|fact_lock|undo):(-?[0-9a-f-]{1,64})(?::([A-Za-z0-9%._~,-]{1,600}))?$/;

/** Parse a `data-repair` value (`kind:item[:extra]`, the extra percent-encoded, so a name is any text); null for
 * anything else. The extra is data only: a request body and a button's text. */
export function repairAction(value: string | null): RepairAction | null {
  const m = value ? REPAIR.exec(value) : null;
  if (!m?.[1] || !m[2]) return null;
  let extra: string | null = null;
  if (m[3] !== undefined) {
    try {
      extra = decodeURIComponent(m[3]);
    } catch {
      return null;
    }
    if (!extra.trim() || extra.length > 120 || /[\u0000-\u001f\u007f]/.test(extra)) return null;
  }
  return { kind: m[1], item: m[2], extra };
}

/** The outcomes a close mark offers (`kind,kind…`, the default first); empty for a mark without them. */
export function closeOutcomes(extra: string | null): string[] {
  return (extra ?? '').split(',').filter((o) => /^[a-z_]{1,24}$/.test(o));
}

/** The story's aliases the owner can split on an entity's page (ADR 0044, K8): each pair once, and only while both
 * names are this entity's (an alias resolution refused joins nothing). */
export function splitChoices(self: EntityRow): { name: string; other: string }[] {
  const own = new Set(self.names.map((n) => n.trim().toLowerCase()));
  const seen = new Set<string>();
  const out: { name: string; other: string }[] = [];
  for (const { name, other } of self.aliases ?? []) {
    const a = name.trim().toLowerCase();
    const b = other.trim().toLowerCase();
    const key = a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
    if (a === b || !own.has(a) || !own.has(b) || seen.has(key)) continue;
    seen.add(key);
    out.push({ name, other });
  }
  return out;
}

/** What the panel offers on an entity's page (ADR 0025): the entity, the others of its type it can be
 * joined with (most mentioned first), and the owner's links it has. Null when the entity is gone or the
 * sidecar has no owner links. */
export function linkChoices(entities: EntityRow[], id: string): { self: EntityRow; others: EntityRow[] } | null {
  const self = entities.find((e) => e.id === id);
  if (!self || !Array.isArray(self.links)) return null;
  const others = entities.filter((e) => e.id !== id && e.type === self.type).sort((a, b) => b.mentions - a.mentions);
  return { self, others };
}

/** The entity that now holds a name, after a link was added or removed (its id may have changed). */
export function entityNamed(entities: EntityRow[], type: string, name: string): EntityRow | null {
  return entities.find((e) => e.type === type && e.names.includes(name)) ?? null;
}

/** The section a contents link points to (`#s-facts` → `s-facts`), or null. */
export function sectionTarget(href: string | null): string | null {
  const id = href?.startsWith('#') ? href.slice(1) : '';
  return SECTION.test(id) ? id : null;
}

/** Whether an attribute of the inspector markup survives: styling, tooltips, folds, inspector links and where a
 * repair can be made (ADR 0044). */
export function keepAttribute(name: string, value: string): boolean {
  switch (name) {
    case 'class': case 'title': case 'open': return true;
    case 'id': return SECTION.test(value);
    case 'href': return inspectorApiPath(value) !== null || sectionTarget(value) !== null;
    case 'data-repair': return repairAction(value) !== null;
    default: return false;
  }
}

/** Parse inspector HTML inertly and drop every element and attribute the inspector does not use. */
export function safeFragment(html: string): DocumentFragment {
  const template = document.createElement('template');
  template.innerHTML = html; // template content is inert: no scripts run, nothing loads
  const clean = (parent: Node): void => {
    for (const node of Array.from(parent.childNodes)) {
      if (node.nodeType === Node.TEXT_NODE) continue;
      if (node.nodeType !== Node.ELEMENT_NODE || !TAGS.has((node as Element).nodeName)) {
        node.remove();
        continue;
      }
      const element = node as Element;
      for (const { name, value } of Array.from(element.attributes)) {
        if (!keepAttribute(name, value)) element.removeAttribute(name);
      }
      clean(element);
    }
  };
  clean(template.content);
  return template.content;
}

/** A sidecar timestamp for the viewer: relative within a week ("3분 전"), else local date and time. */
export function localTime(iso: string, lang: Lang, now: Date = new Date()): { text: string; title: string } | null {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const locale = lang === 'en' ? 'en' : 'ko';
  const title = then.toLocaleString(locale);
  const seconds = Math.round((then.getTime() - now.getTime()) / 1000);
  const ago = Math.abs(seconds);
  if (seconds > 60 || ago >= 7 * 86400) { // a clock ahead of the viewer's, or long ago
    const date = then.toLocaleDateString(locale, { year: 'numeric', month: '2-digit', day: '2-digit' });
    const time = then.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
    return { text: `${date} ${time}`, title };
  }
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const [value, unit]: [number, Intl.RelativeTimeFormatUnit] =
    ago < 45 ? [0, 'second'] : ago < 2700 ? [Math.round(seconds / 60), 'minute']
      : ago < 79200 ? [Math.round(seconds / 3600), 'hour'] : [Math.round(seconds / 86400), 'day'];
  return { text: rtf.format(value, unit), title };
}

/** A join, split or undo previewed before it is made (PHASE-20, ADR 0055), as the sidecar answers it. */
export interface PreviewEntity { id: string; name: string; names: string[]; persona: boolean }
export interface PreviewItem { id?: number | string; text?: string | null; turn?: number | null; by?: string; status?: string }
export interface PreviewLine {
  kind: string;
  fact?: PreviewItem; by?: PreviewItem; instead_of?: PreviewItem;
  thread?: PreviewItem; status?: string;
  secret?: PreviewItem; kept_from_holder?: boolean; kept_from_holder_gone?: boolean;
  repair?: { kind: string }; before?: unknown; after?: unknown;
  conflict?: PreviewItem;
  name?: string; other?: string;
}
export interface Preview {
  action: string; changes: boolean; before: PreviewEntity[]; after: PreviewEntity[]; lines: PreviewLine[];
  counts: Record<string, number>; fingerprint: string; reextract?: { turns: number };
}
type Say = (key: StringKey, vars?: Record<string, string | number>) => string;

const PREVIEW_ORDER = ['persona', 'self_relation', 'self_thread', 'secret', 'fact_replaced', 'fact_ended',
  'conflict_new', 'repair', 'canon_alias', 'fact_merged', 'thread_status', 'thread_merged', 'secret_merged',
  'fact_back', 'thread_back', 'secret_back', 'self_relation_gone', 'self_thread_gone', 'conflict_gone',
  'persona_gone', 'canon_alias_gone'];

function previewLine(x: PreviewLine, say: Say, status: (s: string) => string): string | null {
  const a = (i?: PreviewItem) => i?.text ?? '';
  switch (x.kind) {
    case 'fact_replaced': return say('pv.fact_replaced', { a: a(x.fact), b: a(x.by), t: x.by?.turn ?? '' });
    case 'fact_merged': return say('pv.fact_merged', { a: a(x.fact), b: a(x.by) });
    case 'fact_ended': return say('pv.fact_ended', { a: a(x.fact) });
    case 'fact_back': return x.instead_of ? say('pv.fact_back_instead', { a: a(x.fact), b: a(x.instead_of) })
      : say('pv.fact_back', { a: a(x.fact) });
    case 'self_relation': case 'self_relation_gone': return say(`pv.${x.kind}`, { a: a(x.fact) });
    case 'self_thread': case 'self_thread_gone': return say(`pv.${x.kind}`, { a: a(x.thread), w: x.thread?.by ?? '' });
    case 'thread_status': return say('pv.thread_status', { a: a(x.thread), s: status(x.status ?? '') });
    case 'thread_merged': case 'thread_back': return say(`pv.${x.kind}`, { a: a(x.thread) });
    case 'secret':
      if (x.kept_from_holder) return say('pv.secret_holder', { a: a(x.secret) });
      if (x.kept_from_holder_gone) return say('pv.secret_holder_gone', { a: a(x.secret) });
      return say('pv.secret', { a: a(x.secret) });
    case 'secret_merged': case 'secret_back': return say(`pv.${x.kind}`, { a: a(x.secret) });
    case 'repair': {
      const k = x.repair?.kind ?? '';
      if (x.after == null) return say('pv.repair_stops', { k });
      return say(x.before == null ? 'pv.repair_starts' : 'pv.repair_moves', { k });
    }
    case 'conflict_new': case 'conflict_gone': return say(`pv.${x.kind}`, { a: a(x.conflict) });
    case 'persona': case 'persona_gone': return say(`pv.${x.kind}`);
    case 'canon_alias': case 'canon_alias_gone': return say(`pv.${x.kind}`, { a: x.name ?? '', b: x.other ?? '' });
    default: return null; // a kind a newer sidecar lists: counted, not worded
  }
}

/** What a preview says, in reading order: the entities before and after, then at most `max` lines, the warnings
 * first, and how many more. "Nothing changes" when nothing does. Pure: the panel only renders it. */
export function previewText(p: Preview, say: Say, status: (s: string) => string = (s) => s, max = 8): string[] {
  if (!p.changes) return [say('pv.nothing')];
  const names = (es: PreviewEntity[]) => es.map((e) => e.name).join(', ');
  const out = [say('pv.entities', { a: names(p.before), b: names(p.after) })];
  const rank = (k: string) => { const i = PREVIEW_ORDER.indexOf(k); return i < 0 ? PREVIEW_ORDER.length : i; };
  const lines = [...p.lines].sort((x, y) => rank(x.kind) - rank(y.kind))
    .map((x) => previewLine(x, say, status)).filter((x): x is string => x !== null);
  out.push(...lines.slice(0, max));
  const rest = p.lines.length - Math.min(lines.length, max);
  if (rest > 0) out.push(say('pv.more', { n: rest }));
  return out;
}
