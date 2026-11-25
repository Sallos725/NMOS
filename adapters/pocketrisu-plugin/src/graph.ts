// The memory map's drawing in the panel (PHASE-55 step 6). The sidecar lays it out and sends numbers and names as data
// (`/v1/views/c/<id>/map/graph`); this draws it with SVG elements of its own, every name as text, never as markup, so
// nothing goes through the sanitizer. Pan, pinch or wheel zoom, and a tap that shows one person's ties; a second tap
// opens their own map. No layout runs here: an iPhone only draws what the sidecar placed.

const SVG = 'http://www.w3.org/2000/svg';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const KINDS = new Set(['character', 'group', 'place']);
const EDGE_KINDS = new Set(['tie', 'group', 'place']);
const MARKS = new Set(['setting', 'story', 'changed']);
const LIMIT = { nodes: 2000, edges: 6000, text: 200 };
const LABEL_PX = 14; // a name's size on screen at any zoom
const ARC = 96; // the sidecar's room per node along a ring (memorymap.ARC): names show once it is this many px apart
const NAMES_FROM = 60;
const NAME_MAX = 24; // a drawn name's length (the sidecar's too); the whole name is in the caption and the lines below

export interface GraphNode { id: string; name: string; kind: string; lead: boolean; entity: string | null; x: number; y: number }
export interface GraphEdge { a: string; b: string; kind: string; mark: string }
export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  suspects: { a: string; b: string }[];
  focus: string | null;
  everyone: boolean;
  capped: boolean;
  words: Record<'legend' | 'fit' | 'all' | 'fewer' | 'tap' | 'ties' | 'left', string>;
}
export interface View { x: number; y: number; w: number; h: number }

const str = (v: unknown, max = LIMIT.text): string | null => (typeof v === 'string' && v.length <= max ? v : null);
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && Math.abs(v) < 1e6 ? v : null);

/** The sidecar's answer as a graph, or null when anything in it is not what the drawing expects. */
export function parseGraph(raw: unknown): Graph | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  if (!Array.isArray(r.nodes) || !Array.isArray(r.edges) || !Array.isArray(r.suspects)) return null;
  if (r.nodes.length > LIMIT.nodes || r.edges.length + r.suspects.length > LIMIT.edges) return null;
  const nodes: GraphNode[] = [];
  for (const n of r.nodes as Record<string, unknown>[]) {
    const id = str(n?.id), name = str(n?.name), kind = str(n?.kind), x = num(n?.x), y = num(n?.y);
    const entity = n?.entity === null ? null : str(n?.entity);
    if (id === null || name === null || kind === null || !KINDS.has(kind) || x === null || y === null) return null;
    if (entity !== null && !UUID.test(entity)) return null;
    nodes.push({ id, name, kind, lead: n.lead === true, entity, x, y });
  }
  const ids = new Set(nodes.map((n) => n.id));
  const ends = (e: Record<string, unknown>) => {
    const a = str(e?.a), b = str(e?.b);
    return a !== null && b !== null && ids.has(a) && ids.has(b) ? { a, b } : null;
  };
  const edges: GraphEdge[] = [];
  for (const e of r.edges as Record<string, unknown>[]) {
    const ab = ends(e), kind = str(e?.kind), mark = str(e?.mark);
    if (!ab || kind === null || !EDGE_KINDS.has(kind) || mark === null || !MARKS.has(mark)) return null;
    edges.push({ ...ab, kind, mark });
  }
  const suspects = [];
  for (const s of r.suspects as Record<string, unknown>[]) {
    const ab = ends(s);
    if (!ab) return null;
    suspects.push(ab);
  }
  const w = (r.words ?? {}) as Record<string, unknown>;
  const words = {} as Graph['words'];
  for (const k of ['legend', 'fit', 'all', 'fewer', 'tap', 'ties', 'left'] as const) words[k] = str(w[k], 400) ?? '';
  const focus = r.focus === null || r.focus === undefined ? null : str(r.focus);
  return { nodes, edges, suspects, focus: focus !== null && ids.has(focus) ? focus : null,
    everyone: r.everyone === true, capped: r.capped === true, words };
}

/** The view that shows every node, with room in px for a dot and the name under it at any scale, in the box's proportions. */
export function fitView(nodes: GraphNode[], width: number, height: number): View {
  const xs = nodes.map((n) => n.x), ys = nodes.map((n) => n.y);
  const x0 = Math.min(0, ...xs), x1 = Math.max(0, ...xs), y0 = Math.min(0, ...ys), y1 = Math.max(0, ...ys);
  const pad = 36;
  const s = Math.min(Math.max(width - 2 * pad, 1) / Math.max(x1 - x0, 1), Math.max(height - 2 * pad, 1) / Math.max(y1 - y0, 1), 1);
  const w = width / s, h = height / s;
  return { x: (x0 + x1 - w) / 2, y: (y0 + y1 - h) / 2, w, h };
}

/** The view zoomed by `factor` (> 1 closer) around a point in drawing units, within `min`–`max` px per unit. */
export function zoomAt(v: View, factor: number, px: number, py: number, width: number, min: number, max: number): View {
  const scale = Math.min(Math.max((width / v.w) * factor, min), max);
  const f = scale / (width / v.w);
  const w = v.w / f, h = v.h / f;
  return { x: px - (px - v.x) / f, y: py - (py - v.y) / f, w, h };
}

/** A node and everyone it is tied to. */
export function around(g: Graph, id: string): Set<string> {
  const out = new Set([id]);
  for (const e of g.edges) {
    if (e.a === id) out.add(e.b);
    if (e.b === id) out.add(e.a);
  }
  return out;
}

const make = <K extends keyof SVGElementTagNameMap>(tag: K, cls: string): SVGElementTagNameMap[K] => {
  const node = document.createElementNS(SVG, tag);
  if (cls) node.setAttribute('class', cls);
  return node;
};

export interface GraphUiOpts {
  labels: {
    search: string;
    zoomIn: string;
    zoomOut: string;
    filterAll: string;
    filterSetting: string;
    filterStory: string;
    filterChanged: string;
    filterSplit: string;
    openPerson: string;
    focusPerson: string;
    noTies: string;
  };
  openPerson?: (entity: string) => void;
}

/** Draw the graph in `box`: a lead line under it says whom a tap picked; `open` takes a character's entity id, `toggle`
 * asks for the whole cast or the capped one. When `opts` is given, adds search, source filter chips, zoom +/- buttons
 * and a 1-tap relation summary card without breaking legacy callers. */
export function drawGraph(box: HTMLElement, g: Graph, open: (entity: string) => void, toggle: (everyone: boolean) => void,
  opts?: GraphUiOpts): void {
  const svg = make('svg', 'g-panel');
  const edges = make('g', ''), nodes = make('g', '');
  svg.append(edges, nodes);
  const caption = document.createElement('p');
  caption.className = 'v-note';
  caption.textContent = g.words.legend;
  const buttons = document.createElement('div');
  buttons.className = 'v-graph-btns';
  const button = (text: string, act: () => void) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = text;
    b.addEventListener('click', act);
    buttons.append(b);
  };
  const pos = new Map(g.nodes.map((n) => [n.id, n]));
  const lines: { e: GraphEdge | { a: string; b: string; mark: string; kind?: string }; el: SVGLineElement }[] = [];
  for (const e of [...g.edges, ...g.suspects.map((s) => ({ ...s, mark: 'split' }))]) {
    const a = pos.get(e.a)!, b = pos.get(e.b)!;
    const line = make('line', `g-e ${e.mark}`);
    line.setAttribute('x1', String(a.x)); line.setAttribute('y1', String(a.y));
    line.setAttribute('x2', String(b.x)); line.setAttribute('y2', String(b.y));
    edges.append(line);
    lines.push({ e, el: line });
  }
  const dots = new Map<Element, GraphNode>();
  const parts: { n: GraphNode; dot: SVGCircleElement; label: SVGTextElement; group: SVGGElement }[] = [];
  const far = Math.max(...g.nodes.map((n) => Math.abs(n.x))) / 3; // a name by a side of the drawing runs inward, so it stays in
  for (const n of g.nodes) {
    const group = make('g', 'g-node');
    const dot = make('circle', `g-n ${n.kind}${n.lead ? ' lead' : ''}`);
    dot.setAttribute('cx', String(n.x)); dot.setAttribute('cy', String(n.y));
    const label = make('text', `g-t${n.lead ? ' lead' : ''}`);
    label.setAttribute('x', String(n.x));
    label.setAttribute('text-anchor', n.x < -far ? 'start' : n.x > far ? 'end' : 'middle');
    label.textContent = n.name.length > NAME_MAX ? `${n.name.slice(0, NAME_MAX - 1)}…` : n.name;
    group.append(dot, label);
    nodes.append(group);
    dots.set(group, n);
    parts.push({ n, dot, label, group });
  }

  let searchQuery = '';
  let markFilter = 'all';
  let drawer: HTMLElement | null = null;

  if (opts) {
    const toolbar = document.createElement('div');
    toolbar.className = 'g-toolbar';
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'g-search';
    search.placeholder = opts.labels.search;
    search.setAttribute('aria-label', opts.labels.search);
    const chips = document.createElement('div');
    chips.className = 'g-chips';
    const filterSpecs: [string, string][] = [
      ['all', opts.labels.filterAll],
      ['setting', opts.labels.filterSetting],
      ['story', opts.labels.filterStory],
      ['changed', opts.labels.filterChanged],
      ...(g.suspects.length ? [['split', opts.labels.filterSplit] as [string, string]] : []),
    ];
    const chipBtns: HTMLButtonElement[] = [];
    for (const [key, label] of filterSpecs) {
      const cb = document.createElement('button');
      cb.type = 'button';
      cb.className = `g-chip${key === 'all' ? ' on' : ''}`;
      cb.dataset.mark = key;
      cb.textContent = label;
      cb.addEventListener('click', () => {
        markFilter = key;
        for (const x of chipBtns) x.classList.toggle('on', x.dataset.mark === key);
        apply();
        if (picked) renderDrawer(picked);
      });
      chipBtns.push(cb);
      chips.append(cb);
    }
    search.addEventListener('input', () => {
      searchQuery = search.value.trim().toLowerCase();
      apply();
    });
    toolbar.append(search, chips);

    const stage = document.createElement('div');
    stage.className = 'g-stage';
    const zoomBtns = document.createElement('div');
    zoomBtns.className = 'g-zoom';
    const mkZoom = (txt: string, aria: string, factor: number) => {
      const zb = document.createElement('button');
      zb.type = 'button';
      zb.className = 'mini';
      zb.textContent = txt;
      zb.setAttribute('aria-label', aria);
      zb.setAttribute('title', aria);
      zb.addEventListener('click', () => {
        const cx = view.x + view.w / 2, cy = view.y + view.h / 2;
        view = zoomAt(view, factor, cx, cy, size().w, ...limits());
        apply();
      });
      zoomBtns.append(zb);
    };
    mkZoom('+', opts.labels.zoomIn, 1.35);
    mkZoom('−', opts.labels.zoomOut, 1 / 1.35);
    stage.append(svg, zoomBtns);

    drawer = document.createElement('div');
    drawer.className = 'g-drawer';
    drawer.style.display = 'none';
    box.replaceChildren(toolbar, stage, caption, drawer, buttons);
  } else {
    box.replaceChildren(svg, caption, buttons);
  }

  const size = () => ({ w: svg.clientWidth || 360, h: svg.clientHeight || 420 });
  let fit = fitView(g.nodes, size().w, size().h);
  let view = fit;
  let picked: string | null = null;
  const scaleOf = (v: View) => size().w / v.w;

  const markLabel = (mark: string): string => {
    if (!opts) return mark;
    if (mark === 'setting') return opts.labels.filterSetting;
    if (mark === 'story') return opts.labels.filterStory;
    if (mark === 'changed') return opts.labels.filterChanged;
    if (mark === 'split') return opts.labels.filterSplit;
    return mark;
  };

  const renderDrawer = (id: string | null) => {
    if (!drawer || !opts) return;
    const n = id ? pos.get(id) : null;
    if (!n) {
      drawer.style.display = 'none';
      drawer.replaceChildren();
      return;
    }
    const connected = lines.filter(({ e }) => (e.a === n.id || e.b === n.id) && (markFilter === 'all' || e.mark === markFilter));
    const head = document.createElement('div');
    head.className = 'g-drawer-head';
    const title = document.createElement('b');
    title.textContent = n.name;
    const acts = document.createElement('div');
    acts.className = 'g-drawer-acts';
    if (n.entity && n.kind === 'character') {
      if (opts.openPerson) {
        const personBtn = document.createElement('button');
        personBtn.type = 'button';
        personBtn.className = 'mini primary';
        personBtn.textContent = opts.labels.openPerson;
        personBtn.addEventListener('click', () => opts.openPerson!(n.entity!));
        acts.append(personBtn);
      }
      const focusBtn = document.createElement('button');
      focusBtn.type = 'button';
      focusBtn.className = 'mini';
      focusBtn.textContent = opts.labels.focusPerson;
      focusBtn.addEventListener('click', () => open(n.entity!));
      acts.append(focusBtn);
    }
    head.append(title, acts);
    const list = document.createElement('div');
    list.className = 'g-drawer-list';
    if (!connected.length) {
      const empty = document.createElement('div');
      empty.className = 'v-meta';
      empty.textContent = opts.labels.noTies;
      list.append(empty);
    } else {
      for (const { e } of connected.slice(0, 12)) {
        const other = pos.get(e.a === n.id ? e.b : e.a);
        if (!other) continue;
        const row = document.createElement('div');
        row.className = 'g-drawer-row';
        const nm = document.createElement('span');
        nm.className = 'g-drawer-name';
        nm.textContent = other.name;
        const badge = document.createElement('span');
        badge.className = `g-m ${e.mark}`;
        badge.textContent = markLabel(e.mark);
        row.append(nm, badge);
        if (other.entity && other.kind === 'character') {
          row.classList.add('clickable');
          row.addEventListener('click', () => pick(other.id));
        }
        list.append(row);
      }
    }
    drawer.replaceChildren(head, list);
    drawer.style.display = '';
  };

  const apply = () => {
    svg.setAttribute('viewBox', `${view.x} ${view.y} ${view.w} ${view.h}`);
    const s = scaleOf(view);
    const near = picked ? around(g, picked) : null;
    const names = ARC * s >= NAMES_FROM;
    const activeNodes = markFilter === 'all' ? null : new Set<string>();
    for (const { e, el } of lines) {
      const shown = markFilter === 'all' || e.mark === markFilter;
      el.style.display = shown ? '' : 'none';
      if (shown && activeNodes) { activeNodes.add(e.a); activeNodes.add(e.b); }
    }
    for (const { n, dot, label, group } of parts) {
      const matchesSearch = !searchQuery || n.name.toLowerCase().includes(searchQuery);
      const matchesMark = !activeNodes || activeNodes.has(n.id);
      group.classList.toggle('dim', !matchesSearch || !matchesMark);
      dot.setAttribute('r', String((n.lead ? 9 : 6) / s));
      label.setAttribute('y', String(n.y + ((n.lead ? 9 : 6) + LABEL_PX + 2) / s));
      label.style.fontSize = `${LABEL_PX / s}px`; // over the stylesheet's size
      label.style.display = (searchQuery && matchesSearch) || names || n.lead || near?.has(n.id) ? '' : 'none';
    }
  };
  const pick = (id: string | null) => {
    picked = id;
    svg.classList.toggle('sel', id !== null);
    const near = id ? around(g, id) : new Set<string>();
    for (const { n, group } of parts) group.classList.toggle('on', near.has(n.id));
    for (const { e, el } of lines) el.classList.toggle('on', id !== null && (e.a === id || e.b === id));
    const n = id ? pos.get(id) : null;
    caption.textContent = n
      ? `${n.name} · ${g.words.ties.replace('{n}', String(near.size - 1))}${n.entity ? ` · ${g.words.tap}` : ''}`
      : g.words.legend;
    renderDrawer(id);
    apply();
  };
  button(g.words.fit, () => { view = fit = fitView(g.nodes, size().w, size().h); apply(); });
  if (g.capped || g.everyone) button(g.everyone ? g.words.fewer : g.words.all, () => toggle(!g.everyone));
  if (g.capped && g.words.left) {
    const left = document.createElement('span');
    left.className = 'v-meta';
    left.textContent = g.words.left;
    buttons.append(left);
  }
  // Gestures: one pointer pans, two pinch, a wheel zooms; a pointer that barely moved is a tap.
  const pointers = new Map<number, { x: number; y: number }>();
  let moved = 0;
  let downOn: Element | null = null; // what the finger went down on: a captured pointer's `up` targets the drawing
  const unit = (clientX: number, clientY: number) => {
    const r = svg.getBoundingClientRect();
    const s = scaleOf(view);
    return { x: view.x + (clientX - r.left) / s, y: view.y + (clientY - r.top) / s };
  };
  const limits = () => [scaleOf(fit) * 0.8, Math.max(scaleOf(fit) * 8, 3)] as const;
  svg.addEventListener('pointerdown', (ev) => {
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (pointers.size === 1) { moved = 0; downOn = ev.target instanceof Element ? ev.target : null; }
    svg.setPointerCapture?.(ev.pointerId);
  });
  svg.addEventListener('pointermove', (ev) => {
    const last = pointers.get(ev.pointerId);
    if (!last) return;
    const s = scaleOf(view);
    if (pointers.size === 1) {
      moved += Math.abs(ev.clientX - last.x) + Math.abs(ev.clientY - last.y);
      view = { ...view, x: view.x - (ev.clientX - last.x) / s, y: view.y - (ev.clientY - last.y) / s };
    } else if (pointers.size === 2) {
      const [p, q] = [...pointers.entries()].map(([id, at]) => (id === ev.pointerId ? { x: ev.clientX, y: ev.clientY } : at));
      const [p0, q0] = [...pointers.values()];
      const before = Math.hypot(p0!.x - q0!.x, p0!.y - q0!.y), after = Math.hypot(p!.x - q!.x, p!.y - q!.y);
      const mid = unit((p!.x + q!.x) / 2, (p!.y + q!.y) / 2);
      if (before > 0) view = zoomAt(view, after / before, mid.x, mid.y, size().w, ...limits());
      moved += 99;
    }
    pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    apply();
  });
  const up = (ev: PointerEvent) => {
    const single = pointers.size === 1;
    pointers.delete(ev.pointerId);
    if (!single || moved > 8 || ev.type === 'pointercancel') return;
    const target = downOn?.closest('.g-node') ?? null;
    const n = target ? dots.get(target) : undefined;
    if (!n) return pick(null);
    if (picked === n.id && n.entity) return open(n.entity);
    pick(n.id);
  };
  svg.addEventListener('pointerup', up);
  svg.addEventListener('pointercancel', up);
  svg.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const at = unit(ev.clientX, ev.clientY);
    view = zoomAt(view, Math.exp(-ev.deltaY * 0.0015), at.x, at.y, size().w, ...limits());
    apply();
  }, { passive: false });
  pick(g.focus);
}
