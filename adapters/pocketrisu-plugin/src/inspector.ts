// The sidecar's inspector pages, shown inside the NMOS panel. The sidecar escapes every value; this
// keeps only the markup those pages use, so nothing else can reach the plugin frame.

import type { Lang } from './i18n';

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

/** Whether an attribute of the inspector markup survives: styling, tooltips, folds and inspector links. */
export function keepAttribute(name: string, value: string): boolean {
  switch (name) {
    case 'class': case 'title': case 'open': return true;
    case 'id': return SECTION.test(value);
    case 'href': return inspectorApiPath(value) !== null || sectionTarget(value) !== null;
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
