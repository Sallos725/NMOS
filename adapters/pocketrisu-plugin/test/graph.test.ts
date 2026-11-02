// @vitest-environment happy-dom
// PHASE-55 step 6: the memory map's drawing in the panel, drawn from the sidecar's data, names as text.
import { afterEach, describe, expect, it } from 'vitest';
import { around, drawGraph, fitView, parseGraph, zoomAt } from '../src/graph';

const A = '0190f3a4-1b2c-7d3e-8f40-00000000000a';
const B = '0190f3a4-1b2c-7d3e-8f40-00000000000b';
const raw = () => ({
  nodes: [
    { id: A, name: 'Hana', kind: 'character', lead: true, entity: A, x: 0, y: 0 },
    { id: B, name: '<img src=x onerror=alert(1)>', kind: 'character', lead: false, entity: B, x: 120, y: 0 },
    { id: 'text:group:guild', name: 'the guild', kind: 'group', lead: false, entity: null, x: 0, y: 240 },
  ],
  edges: [{ a: A, b: B, kind: 'tie', mark: 'changed' }, { a: A, b: 'text:group:guild', kind: 'group', mark: 'setting' }],
  suspects: [], focus: null, everyone: false, capped: true,
  words: { legend: 'Lines…', fit: 'Fit', all: 'Show all', fewer: 'Show fewer', tap: 'Tap again', ties: '{n} ties',
    left: 'Left out: 3' },
});

describe('the drawing as data', () => {
  it('takes only what it can draw', () => {
    const g = parseGraph(raw())!;
    expect(g.nodes).toHaveLength(3);
    expect(g.edges.map((e) => e.mark)).toEqual(['changed', 'setting']);
    const bad: ((r: ReturnType<typeof raw>) => void)[] = [
      (r) => { r.nodes[0]!.kind = 'script'; },
      (r) => { (r.nodes[0] as { x: unknown }).x = 'NaN'; },
      (r) => { r.nodes[1]!.entity = 'javascript:x'; },
      (r) => { r.edges[0]!.mark = 'evil'; },
      (r) => { r.edges[0]!.b = 'nobody'; },
      (r) => { r.nodes[0]!.name = 'x'.repeat(201); },
    ];
    for (const spoil of bad) {
      const r = raw();
      spoil(r);
      expect(parseGraph(r)).toBeNull();
    }
    expect(parseGraph(null)).toBeNull();
    expect(parseGraph({ nodes: [] })).toBeNull();
    expect(parseGraph({ ...raw(), focus: 'nobody' })!.focus).toBeNull();
  });

  it('fits every node in the box and zooms around a point', () => {
    const g = parseGraph(raw())!;
    const v = fitView(g.nodes, 360, 420);
    for (const n of g.nodes) {
      expect(n.x).toBeGreaterThan(v.x);
      expect(n.x).toBeLessThan(v.x + v.w);
      expect(n.y).toBeGreaterThan(v.y);
      expect(n.y).toBeLessThan(v.y + v.h);
    }
    expect(v.w / v.h).toBeCloseTo(360 / 420);
    const closer = zoomAt(v, 2, 0, 0, 360, 0.01, 100);
    expect(closer.w).toBeCloseTo(v.w / 2);
    expect((0 - closer.x) / closer.w).toBeCloseTo((0 - v.x) / v.w); // the point under the fingers stays put
    expect(zoomAt(v, 1000, 0, 0, 360, 0.01, 3).w).toBeCloseTo(360 / 3); // at most `max` px per unit
    expect([...around(g, A)].sort()).toEqual([A, B, 'text:group:guild'].sort());
  });
});

describe('the drawing in the panel', () => {
  afterEach(() => document.body.replaceChildren());
  // as a browser does it: down on what was touched, up on the drawing that captured the pointer
  const tap = (target: Element) => {
    target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 1, clientX: 10, clientY: 10 }));
    const svg = target.closest('svg') ?? target;
    svg.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1, clientX: 10, clientY: 10 }));
  };

  it('draws names as text, picks a person on a tap and opens their map on the next', () => {
    const box = document.createElement('div');
    document.body.append(box);
    const opened: string[] = [];
    const toggled: boolean[] = [];
    drawGraph(box, parseGraph(raw())!, (e) => opened.push(e), (all) => toggled.push(all));
    const svg = box.querySelector('svg')!;
    expect(svg.querySelectorAll('circle')).toHaveLength(3);
    expect(svg.querySelectorAll('line')).toHaveLength(2);
    expect(box.querySelector('img')).toBeNull();
    expect(Array.from(svg.querySelectorAll('text')).map((t) => t.textContent)).toContain('<img src=x onerror=alert(1)>');
    const hana = svg.querySelectorAll('.g-node')[0]!;
    tap(hana.querySelector('circle')!);
    expect(svg.classList.contains('sel')).toBe(true);
    expect(box.querySelector('p')!.textContent).toBe('Hana · 2 ties · Tap again');
    expect(svg.querySelectorAll('line.on')).toHaveLength(2);
    tap(hana.querySelector('circle')!);
    expect(opened).toEqual([A]);
    tap(svg); // the background clears the pick
    expect(svg.classList.contains('sel')).toBe(false);
    const guild = svg.querySelectorAll('.g-node')[2]!;
    tap(guild);
    tap(guild);
    expect(opened).toEqual([A]); // a group opens nothing
    const buttons = Array.from(box.querySelectorAll('button'));
    expect(buttons.map((b) => b.textContent)).toEqual(['Fit', 'Show all']);
    buttons[1]!.click();
    expect(toggled).toEqual([true]);
  });

  it('a drag is not a tap', () => {
    const box = document.createElement('div');
    document.body.append(box);
    const opened: string[] = [];
    drawGraph(box, { ...parseGraph(raw())!, focus: A }, (e) => opened.push(e), () => {});
    const svg = box.querySelector('svg')!;
    const before = svg.getAttribute('viewBox');
    const dot = svg.querySelector('circle')!;
    dot.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, pointerId: 1, clientX: 10, clientY: 10 }));
    dot.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, pointerId: 1, clientX: 60, clientY: 40 }));
    dot.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, pointerId: 1, clientX: 60, clientY: 40 }));
    expect(svg.getAttribute('viewBox')).not.toBe(before);
    expect(opened).toEqual([]); // the focus was picked already; a drag over it does not open it
  });
});
