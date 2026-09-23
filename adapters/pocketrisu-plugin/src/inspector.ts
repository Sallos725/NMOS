// The sidecar's inspector pages, shown inside the NMOS panel. The sidecar escapes every value; this
// keeps only the markup those pages use, so nothing else can reach the plugin frame.

const TAGS = new Set(['DIV', 'P', 'H1', 'H2', 'SPAN', 'B', 'BR', 'A', 'TABLE', 'THEAD', 'TBODY', 'TR', 'TH', 'TD']);

/** The sidecar API path for an inspector link (`/inspector`, `/inspector/c/<id>`), or null. */
export function inspectorApiPath(href: string | null): string | null {
  const m = /^\/inspector(\/c\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?(?:[?#]|$)/i.exec(href ?? '');
  return m ? `/v1/inspector${m[1] ?? ''}` : null;
}

/** The conversation id of an inspector detail API path (`/v1/inspector/c/<id>`), or null. */
export function inspectorConversation(path: string): string | null {
  const m = /^\/v1\/inspector\/c\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i.exec(path);
  return m ? (m[1] as string) : null;
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
        const keep = name === 'class' || name === 'title' || (name === 'href' && inspectorApiPath(value) !== null);
        if (!keep) element.removeAttribute(name);
      }
      clean(element);
    }
  };
  clean(template.content);
  return template.content;
}
