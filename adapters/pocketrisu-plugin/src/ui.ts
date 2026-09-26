// NMOS panel, rendered inside the plugin's own sandboxed iframe (full screen): status, inspector and
// settings tabs. Plugin-side settings are PocketRisu plugin args; model/recall/parser settings live in
// the sidecar and are saved together with one request.

import type { StatusInfo } from './core';
import { deadlineAdvice, formatMs } from './deadline';
import { configBody, connArgs, DEFAULT_DEADLINE_MS, dirtySections, fillProject, MAX_DEADLINE_MS, presetMatches, VERTEX_URL,
  type FormValues, type Section } from './form';
import { langOf, t, type Lang, type StringKey } from './i18n';
import { entityNamed, inspectorApiPath, inspectorConversation, inspectorEntity, linkChoices, localTime, safeFragment,
  sectionTarget } from './inspector';
import type { EntityRow } from './inspector';
import { routeFor } from './route';

export type Tab = 'status' | 'inspector' | 'settings';

/** The progress display on the chat screen (D28). */
export interface HudControl {
  /** Asks PocketRisu for main-page access and turns the display on if granted. */
  enable(): Promise<'on' | 'denied' | 'unsupported'>;
  disable(): Promise<void>;
  /** Why the display stopped for this session, if it did. */
  problem(): string | null;
  /** Background work was queued: follow it (this conversation, or the last one seen). */
  background(conversationId?: string): void;
}

export interface PanelDeps {
  api<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<T>;
  status(): Promise<StatusInfo>;
  getArg(key: string): Promise<string>;
  setArg(key: string, value: string | number): Promise<void>;
  show(): Promise<void>;
  hide(): Promise<void>;
  hud: HudControl;
}

interface ServerConfig {
  llm: { url: string; model: string; api_key_set: boolean; json_mode: boolean };
  embeddings: { url: string; model: string; api_key_set: boolean; query_instruction: string };
  recall: { threshold: number; vector_min_sim: number; top_k: number; facts_limit: number };
  extraction: { backfill: number };
  parsers: { rules: unknown; source: string; active_rules: number; errors: string[] };
  queued_jobs?: number;
}

interface Preset { label: string | StringKey; url: string; model?: string }

const LLM_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: 'http://host.docker.internal:11434/v1' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'Google Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.5-flash' },
  { label: 'Google Vertex AI', url: VERTEX_URL, model: 'google/gemini-2.5-flash' },
  { label: 'preset.custom', url: 'custom' },
];

const EMBED_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: 'http://host.docker.internal:11434/v1', model: 'qwen3-embedding:0.6b' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'text-embedding-3-small' },
  { label: 'preset.custom', url: 'custom' },
];

const PARSER_EXAMPLE = {
  rules: [
    { id: 'roster', kind: 'block', role: 'char', start: '<status>', end: '</status>', entity_line: '\\[(?P<entity>[^\\]]+)\\]' },
    { id: 'hp', kind: 'regex', pattern: 'HP\\s*[:：]\\s*(?P<value>\\d+\\s*/\\s*\\d+)', key: 'HP' },
  ],
};

const SECTION_TITLE: Record<Section, StringKey> = {
  conn: 'conn.title', llm: 'llm.title', emb: 'emb.title', tune: 'tune.title', rules: 'rules.title',
};

// Opaque on purpose: the host settings page behind the full-screen frame must not show through.
const CSS = `
html,body{margin:0;background:#0c0c10}
.nmos{position:fixed;inset:0;overflow:auto;background:#0c0c10;font:14px/1.55 system-ui,-apple-system,"Noto Sans KR",sans-serif;color:#e8e8ec}
.nmos *{box-sizing:border-box}
.nmos .wrap{max-width:760px;margin:0 auto;padding:16px 14px 24px}
.nmos header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.nmos h1{font-size:19px;margin:0;flex:1;white-space:nowrap}
.nmos .tabs{display:flex;gap:4px;border-bottom:1px solid #30323b;margin:6px 0 4px}
.nmos .tabs button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;padding:8px 14px;color:#9a9ca8}
.nmos .tabs button.on{color:#e8e8ec;border-bottom-color:#4c6ef5}
.nmos .card{background:#1d1e24;border:1px solid #30323b;border-radius:10px;padding:16px;margin:12px 0}
.nmos h2{font-size:15px;margin:0 0 2px}
.nmos .sub{color:#9a9ca8;font-size:12.5px;margin:0 0 12px}
.nmos label{display:block;font-size:12.5px;color:#b8bac4;margin:10px 0 4px}
.nmos input,.nmos select,.nmos textarea{width:100%;background:#15161b;color:#e8e8ec;border:1px solid #3a3c46;border-radius:6px;padding:8px 10px;font:inherit}
.nmos header select{width:auto;padding:5px 8px}
.nmos textarea{min-height:160px;font-family:ui-monospace,monospace;font-size:12.5px}
.nmos .row{display:flex;gap:10px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.nmos button{background:#2b2d36;color:#e8e8ec;border:1px solid #444654;border-radius:6px;padding:7px 14px;font:inherit;cursor:pointer}
.nmos button.primary{background:#4c6ef5;border-color:#4c6ef5;color:#fff}
.nmos button.danger{background:#c92a2a;border-color:#c92a2a;color:#fff}
.nmos button:disabled{opacity:.45;cursor:default}
.nmos .msg{margin-top:10px;font-size:13px;white-space:pre-wrap}
.nmos .ok{color:#69db7c}.nmos .err{color:#ff8787}.nmos .warn{color:#ffd43b}.nmos .muted{color:#9a9ca8}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px}.nmos .check input{width:auto}
.nmos .line{display:flex;align-items:baseline;gap:8px;margin:4px 0}
.nmos .dot{flex:none;width:9px;height:9px;border-radius:50%;background:#6b6d78;transform:translateY(-1px)}
.nmos .dot.ok{background:#51cf66}.nmos .dot.err{background:#ff6b6b}.nmos .dot.warn{background:#fcc419}
.nmos .pills{display:flex;gap:8px;flex-wrap:wrap}
.nmos .pill{border:1px solid #3a3c46;border-radius:999px;padding:3px 12px;font-size:13px;color:#9a9ca8}
.nmos .pill.on{border-color:#2f9e44;color:#8ce99a}
.nmos .mono{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-all}
.nmos.wide>.wrap{max-width:1100px}
.nmos .insp{margin-top:14px}.nmos .insp+.sub{margin-top:18px}
.nmos .insp h1{font-size:17px;margin:4px 0}
.nmos .insp h2{margin:22px 0 8px}
.nmos .insp .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nmos .insp .top p{margin:0}
.nmos .insp a{color:#91a7ff;text-decoration:none;cursor:pointer}
.nmos .insp .ref{display:block;font-family:ui-monospace,monospace;font-size:11px;color:#9a9ca8}
.nmos .insp .wrap{max-width:none;margin:0;padding:0;overflow-x:auto}
.nmos .insp table{width:100%;border-collapse:collapse;font-size:13px}
.nmos .insp th,.nmos .insp td{text-align:left;padding:6px 8px;border-bottom:1px solid #30323b;vertical-align:top}
.nmos .insp th{font-weight:600;color:#9a9ca8;font-size:12px;white-space:nowrap}
.nmos .insp .chip{display:inline-block;padding:0 6px;border-radius:4px;background:#2b2d36;font-size:12px}
.nmos .inspbar{position:sticky;top:0;z-index:1;background:#0c0c10;padding:8px 0;margin-top:4px}
.nmos .help{margin:8px 0 0}.nmos .help summary{cursor:pointer}.nmos .help p{margin:6px 0 0}
.nmos .packet{margin:8px 0 0;max-height:420px;overflow:auto;background:#15161b;border:1px solid #30323b;border-radius:6px;padding:10px;font-family:ui-monospace,monospace;font-size:12.5px;white-space:pre-wrap;word-break:break-word}
.nmos .insp.busy{opacity:.55;transition:opacity .15s}
.nmos .insp details>summary{cursor:pointer;list-style:none}.nmos .insp details>summary::-webkit-details-marker{display:none}
.nmos .insp details>summary h2{display:inline-block}
.nmos .insp details>summary h2::before{content:"▸ ";color:#6b6d78}.nmos .insp details[open]>summary h2::before{content:"▾ "}
.nmos .insp .n{color:#9a9ca8;font-weight:400;font-size:12px}
.nmos .insp .toc{font-size:13px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:#ffd43b}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:12px;margin-top:2px}.nmos .insp details.meta p{margin:4px 0}
.nmos .bar{position:sticky;bottom:0;background:#15161b;border-top:1px solid #30323b;padding:10px max(14px,calc((100% - 760px) / 2 + 14px));display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.nmos .bar .text{flex:1;min-width:160px;font-size:13px}
`;

type Attrs = Record<string, string | number | boolean | undefined>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    if (k === 'class') node.className = String(v);
    else if (k === 'text') node.textContent = String(v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const child of children) node.append(child);
  return node;
}

function say(target: HTMLElement, text: string, kind: 'ok' | 'err' | 'warn' | 'muted' = 'muted'): void {
  target.className = `${target.classList.contains('text') ? 'text' : 'msg'} ${kind}`;
  target.textContent = text;
}

function field(labelText: string, input: HTMLElement): HTMLElement {
  return el('div', {}, el('label', { text: labelText }), input);
}

function presetIndex(presets: Preset[], url: string): number {
  if (!url) return 0;
  const i = presets.findIndex((p) => presetMatches(p.url, url));
  return i >= 0 ? i : presets.length - 1;
}

function errorText(lang: Lang, error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, 'invalid')).replace(/^\/v1\/\S+ -> /, t(lang, 'sidecar_error'));
}

let current: { root: HTMLElement; select(tab: Tab): void } | null = null;

/** Open the NMOS panel on `tab` (or switch tabs if it is already open). */
export async function openPanel(deps: PanelDeps, tab: Tab): Promise<void> {
  if (current && document.body.contains(current.root)) {
    current.select(tab);
    await deps.show();
    return;
  }
  if (!document.getElementById('nmos-style')) document.head.append(el('style', { id: 'nmos-style', text: CSS }));
  const lang = langOf(await deps.getArg('language'));
  current = await render(deps, lang, tab);
  await deps.show();
}

async function render(deps: PanelDeps, lang: Lang, tab: Tab): Promise<{ root: HTMLElement; select(tab: Tab): void }> {
  const L = (key: StringKey, vars?: Record<string, string | number>) => t(lang, key, vars);
  const root = el('div', { class: 'nmos', id: 'nmos-panel' });
  const wrap = el('div', { class: 'wrap' });
  root.append(wrap);

  // --- header: title, language, close, tabs ---------------------------------------------------
  const language = el('select', { 'aria-label': L('language') },
    el('option', { value: 'ko', text: '한국어' }), el('option', { value: 'en', text: 'English' }));
  language.value = lang;
  const close = el('button', { text: L('close') });
  const tabStatus = el('button', { text: L('tab.status') });
  const tabInspector = el('button', { text: L('tab.inspector') });
  const tabSettings = el('button', { text: L('tab.settings') });
  wrap.append(el('header', {}, el('h1', { text: L('title') }), language, close),
    el('nav', { class: 'tabs' }, tabStatus, tabInspector, tabSettings));
  const statusView = el('div');
  const inspectorView = el('div');
  const settingsView = el('div');
  wrap.append(statusView, inspectorView, settingsView);
  let shown: Tab = tab;

  // --- status tab ------------------------------------------------------------------------------
  async function refreshStatus(): Promise<void> {
    statusView.replaceChildren(el('div', { class: 'card muted', text: L('status.checking') }));
    const s = await deps.status();
    const base = s.sidecarUrl.replace(/\/+$/, '');
    const conn = el('div', { class: 'card' }, el('h2', { text: L('status.sidecar') }));
    if (s.connected) {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot ok' }),
        el('span', { text: `${L('status.connected')} · NMOS ${s.version ?? ''}` })),
      el('div', { class: 'mono muted', text: base }));
    } else {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot err' }),
        el('span', { class: 'err', text: `${L('status.unreachable')}: ${base}` })),
      el('div', { class: 'muted', text: s.error ?? '' }), el('p', { class: 'sub', text: L('status.fix') }));
    }
    if (!s.enabled) conn.append(el('div', { class: 'line warn' }, el('span', { class: 'dot warn' }),
      el('span', { text: L('status.memory_off') })));

    const features = el('div', { class: 'card' }, el('h2', { text: L('status.features') }));
    const pills = el('div', { class: 'pills' });
    for (const [key, name] of [['state', 'feature.state'], ['extraction', 'feature.extraction'], ['vectors', 'feature.vectors']] as const) {
      const on = Boolean(s.features?.[key]);
      pills.append(el('span', { class: on ? 'pill on' : 'pill', text: `${L(name)} ${on ? L('on') : L('off')}` }));
    }
    features.append(s.connected ? pills : el('div', { class: 'muted', text: '—' }));

    const lastCard = el('div', { class: 'card' }, el('h2', { text: L('status.last') }));
    if (s.last) {
      const kind = s.last.outcome === 'injected' ? 'ok' : s.last.outcome === 'failed' ? 'err' : 'muted';
      const what = s.last.outcome === 'injected' ? L('outcome.injected', { n: s.last.packetChars })
        : s.last.outcome === 'nothing-relevant' ? L('outcome.nothing') : L('outcome.failed');
      lastCard.append(el('div', { class: 'line' }, el('span', { class: `dot ${kind}` }), el('span', { text: what })),
        el('div', { class: 'muted', text: `${L('status.ago', { n: Math.round((Date.now() - s.last.at) / 1000) })} · ${s.last.ms}ms` }));
      if (s.last.packet) lastCard.append(el('details', { class: 'help' },
        el('summary', { text: L('status.packet') }), el('pre', { class: 'packet', text: s.last.packet })));
      if (s.last.error) lastCard.append(el('div', { class: 'mono muted', text: s.last.error }));
    } else {
      lastCard.append(el('div', { class: 'muted', text: L('status.none') }));
    }

    const cards: HTMLElement[] = [conn, features, lastCard];
    // A long chat that runs out of time gets no memory at all (fail open), silently: say it first, with
    // the value to set, and warn before it happens (owner decision on audit A-09).
    const advice = deadlineAdvice(s.last);
    if (advice) {
      const open = el('button', { text: L('deadline.open_settings') });
      open.addEventListener('click', () => select('settings'));
      const took = advice.tookMs === null ? '' : L('deadline.took', { n: formatMs(advice.tookMs) });
      const text = advice.level === 'over'
        ? L('deadline.over', { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) })
        : L('deadline.near', { d: formatMs(advice.deadlineMs), n: formatMs(advice.tookMs ?? 0), s: formatMs(advice.suggestMs) });
      cards.unshift(el('div', { class: 'card' },
        el('h2', { class: advice.level === 'over' ? 'err' : 'warn', text: L(`deadline.${advice.level}.title`) }),
        el('p', { class: 'sub', text }), el('div', { class: 'btns' }, open)));
    }
    const problem = deps.hud.problem();
    if (Number(await deps.getArg('hud')) !== 1) {
      const turnOn = el('button', { text: L('hud.enable') });
      const msg = el('div', { class: 'msg' });
      turnOn.addEventListener('click', async () => {
        turnOn.disabled = true;
        const result = await deps.hud.enable();
        if (result === 'on') return void refreshStatus();
        turnOn.disabled = false;
        say(msg, L(result === 'denied' ? 'hud.denied' : 'hud.unsupported'), 'warn');
      });
      cards.push(el('div', { class: 'card' }, el('h2', { text: L('hud.title') }),
        el('div', { class: 'muted', text: L('hud.hint') }), el('div', { class: 'btns' }, turnOn), msg));
    } else if (problem) {
      cards.push(el('div', { class: 'card' }, el('h2', { text: L('hud.title') }),
        el('div', { class: 'warn', text: L('hud.broken', { e: problem }) })));
    }
    const refresh = el('button', { text: L('refresh') });
    refresh.addEventListener('click', () => void refreshStatus());
    statusView.replaceChildren(...cards, el('div', { class: 'btns' }, refresh));
  }

  // --- inspector tab ---------------------------------------------------------------------------
  // The sidecar's own inspector pages, shown in place: the plugin frame cannot open a tab (H15).
  // Links are handled here; following one would navigate the plugin frame itself.
  let inspectorPath = '/v1/inspector';
  let shownPath: string | null = null; // the page on screen, once it has loaded
  let loads = 0; // the latest load wins: an answer to an older one is dropped
  // Pages read before this one and where the reader was on them, for the Back button.
  interface Place { path: string; scroll: number; open: string[] }
  const visited: Place[] = [];
  const inspectorBody = el('div', { class: 'insp' });
  const inspectorBack = el('button', { text: L('insp.back') });
  const inspectorRefresh = el('button', { text: L('refresh') });
  const inspectorAddress = el('p', { class: 'sub mono' });
  // Per-chat actions (D22, ADR 0009) on a conversation page: they run in the sidecar.
  const historyButton = el('button', { text: L('act.history') });
  const rebuildButton = el('button', { text: L('act.rebuild') });
  const deleteButton = el('button', { text: L('act.delete') });
  const actionMsg = el('div', { class: 'msg' });
  const actions = el('div', {}, el('div', { class: 'btns' }, historyButton, rebuildButton, deleteButton),
    el('details', { class: 'sub help' }, el('summary', { text: L('act.help') }), el('p', { text: L('act.sub') })));
  // The message sits outside the actions so a result stays visible after a delete returns to the list.
  // Back and Refresh stay in reach while reading far down a page.
  // On an entity's page: the owner joins it with another entity of its type, or undoes a join (ADR 0025).
  const linkCard = el('div', { class: 'card', style: 'display:none' });
  inspectorView.append(el('div', { class: 'btns inspbar' }, inspectorBack, inspectorRefresh), actions, actionMsg,
    linkCard, inspectorBody, inspectorAddress);
  let actionConversation: string | null = null;
  function place(): Place {
    const open = Array.from(inspectorBody.querySelectorAll<HTMLDetailsElement>('details[id]')).filter((d) => d.open);
    return { path: inspectorPath, scroll: root.scrollTop, open: open.map((d) => d.id) };
  }
  function restore(at: Place): void {
    for (const d of Array.from(inspectorBody.querySelectorAll<HTMLDetailsElement>('details[id]'))) d.open = at.open.includes(d.id);
    root.scrollTop = at.scroll;
  }
  /** Adapt a page to the panel: times in the viewer's zone, the character links as a drop-down. */
  function enhance(page: DocumentFragment): void {
    for (const span of Array.from(page.querySelectorAll('span.ts[title]'))) {
      const shown = localTime(span.getAttribute('title') ?? '', lang);
      if (!shown) continue;
      span.textContent = shown.text;
      span.setAttribute('title', shown.title);
    }
    const who = page.querySelector('p.who');
    if (!who) return;
    const name = who.querySelector('span')?.textContent ?? '';
    const picker = el('select', { 'aria-label': name });
    for (const choice of Array.from(who.querySelectorAll('a, b'))) {
      const path = choice.tagName === 'B' ? inspectorPath : inspectorApiPath(choice.getAttribute('href'));
      if (path) picker.append(el('option', { value: path, text: choice.textContent ?? '', selected: choice.tagName === 'B' }));
    }
    picker.addEventListener('change', () => go(picker.value));
    who.replaceChildren(el('span', { class: 'muted', text: name }), picker);
  }
  function go(path: string): void {
    if (path === inspectorPath) return void showInspector();
    if (shownPath) visited.push(place());
    if (visited.length > 30) visited.shift();
    void showInspector(path);
  }
  async function showInspector(path = inspectorPath, at?: Place): Promise<void> {
    const load = ++loads;
    const again = path === shownPath; // a refresh keeps the reader's place and open sections
    const keep = at ?? (again ? place() : undefined);
    inspectorPath = path;
    inspectorBack.style.display = visited.length ? '' : 'none';
    const conversation = inspectorConversation(path);
    if (conversation !== actionConversation) {
      actionConversation = conversation;
      say(actionMsg, '');
      disarm();
    }
    actions.style.display = conversation ? '' : 'none';
    const shownEntity = inspectorEntity(path);
    if (!shownEntity) linkCard.style.display = 'none';
    if (again) {
      inspectorBody.classList.add('busy'); // the old page stays until the new one is there
    } else {
      shownPath = null;
      inspectorBody.replaceChildren(el('div', { class: 'card muted', text: L('insp.loading') }));
    }
    // Only a sidecar the browser reaches itself can be opened in a tab; a server-routed one (Docker
    // name, LAN address behind HTTPS) is reachable from the PocketRisu server only.
    const base = ((await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790').replace(/\/+$/, '');
    const direct = routeFor(base, await deps.getArg('route')) === 'direct';
    inspectorAddress.textContent = direct ? L('insp.browser', { url: `${base}/inspector${lang === 'en' ? '?lang=en' : ''}` }) : '';
    try {
      const r = await deps.api<{ html: string }>('GET', `${path}${lang === 'en' ? '?lang=en' : ''}`, undefined, 15_000);
      if (load !== loads) return;
      const page = safeFragment(r.html);
      enhance(page);
      inspectorBody.replaceChildren(page);
      shownPath = path;
      if (keep) restore(keep);
      else root.scrollTop = 0;
      if (shownEntity) void showLinks(shownEntity.conversation, shownEntity.entity, load);
    } catch (error) {
      if (load !== loads) return;
      shownPath = null;
      inspectorBody.replaceChildren(el('div', { class: 'card err', text: errorText(lang, error) }));
    } finally {
      if (load === loads) inspectorBody.classList.remove('busy');
    }
  }
  async function showLinks(conversation: string, entity: string, load: number): Promise<void> {
    let entities: EntityRow[];
    try {
      entities = await deps.api<EntityRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
    } catch {
      entities = []; // the page itself already reports a failing sidecar
    }
    if (load !== loads) return;
    const choices = linkChoices(entities, entity);
    if (!choices) {
      linkCard.style.display = 'none';
      return;
    }
    const { self, others } = choices;
    const msg = el('div', { class: 'msg' });
    const rows: HTMLElement[] = [];
    for (const link of self.links ?? []) {
      const undo = el('button', { text: L('link.remove') });
      undo.addEventListener('click', async () => {
        undo.disabled = true;
        try {
          await deps.api('POST', `/v1/conversations/${conversation}/entity-links/${link.id}/remove`, {}, 15_000);
          const now = await deps.api<EntityRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
          const next = entityNamed(now, self.type, self.name);
          say(actionMsg, L('link.removed'), 'ok');
          if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
          else await showInspector();
        } catch (error) { say(msg, errorText(lang, error), 'err'); undo.disabled = false; }
      });
      rows.push(el('div', { class: 'btns' }, el('span', { text: `${link.name} = ${link.same_as}` }), undo));
    }
    const card: (Node | string)[] = [el('h2', { text: L('link.title') }), el('p', { class: 'sub', text: L('link.sub') }), ...rows];
    if (others.length) {
      const pick = el('select', { 'aria-label': L('link.pick') },
        ...others.map((e) => el('option', { value: e.name, text: `${e.name} (${e.mentions})` })));
      const join = el('button', { text: L('link.join') });
      join.addEventListener('click', async () => {
        join.disabled = true;
        try {
          const r = await deps.api<{ entity: EntityRow | null }>('POST', `/v1/conversations/${conversation}/entity-links`,
            { entity_type: self.type, name: self.name, same_as: pick.value }, 15_000);
          say(actionMsg, L('link.done', { a: self.name, b: pick.value }), 'ok');
          if (r.entity && r.entity.id !== entity) go(`/v1/inspector/c/${conversation}/e/${r.entity.id}`);
          else await showInspector();
        } catch (error) { say(msg, errorText(lang, error), 'err'); join.disabled = false; }
      });
      card.push(el('div', { class: 'row' }, field(L('link.pick'), pick), el('div', { class: 'btns' }, join)));
    } else {
      card.push(el('div', { class: 'muted', text: L('link.none') }));
    }
    linkCard.replaceChildren(...card, msg);
    linkCard.style.display = '';
  }
  inspectorBody.addEventListener('click', (event) => {
    const link = event.target instanceof Element ? event.target.closest('a') : null;
    if (!link) return;
    event.preventDefault();
    const href = link.getAttribute('href');
    const section = sectionTarget(href);
    const target = section ? inspectorBody.querySelector<HTMLElement>(`#${section}`) : null;
    if (target) {
      if (target instanceof HTMLDetailsElement) target.open = true;
      target.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    const path = inspectorApiPath(href);
    if (path) go(path);
  });
  inspectorBack.addEventListener('click', () => {
    const at = visited.pop();
    if (at) void showInspector(at.path, at);
  });
  inspectorRefresh.addEventListener('click', () => void showInspector());
  // Destructive actions take two clicks: the first arms the button for 6 s.
  const confirmable: [HTMLButtonElement, StringKey, string][] = [
    [rebuildButton, 'act.rebuild', 'primary'], [deleteButton, 'act.delete', 'danger']];
  let armed: HTMLButtonElement | null = null;
  let armTimer = 0;
  function disarm(): void {
    window.clearTimeout(armTimer);
    armed = null;
    for (const [button, label] of confirmable) {
      button.textContent = L(label);
      button.className = '';
    }
  }
  function confirmed(button: HTMLButtonElement, confirm: StringKey, cls: string): boolean {
    if (armed === button) {
      disarm();
      return true;
    }
    disarm();
    armed = button;
    button.textContent = L(confirm);
    button.className = cls;
    armTimer = window.setTimeout(disarm, 6000);
    return false;
  }
  function actionError(error: unknown): string {
    return /HTTP 409/.test(error instanceof Error ? error.message : String(error)) ? L('act.off') : errorText(lang, error);
  }
  interface ActionResult { queued: { extract?: number; embed?: number }; discarded?: number }
  historyButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    if (!conversation) return;
    disarm();
    historyButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<ActionResult>('POST', `/v1/conversations/${conversation}/extract-history`, {}, 30_000);
      const n = (r.queued.extract ?? 0) + (r.queued.embed ?? 0);
      say(actionMsg, n ? L('act.history_done', { t: r.queued.extract ?? 0, m: r.queued.embed ?? 0 }) : L('act.history_none'), 'ok');
      if (n) deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { historyButton.disabled = false; }
  });
  rebuildButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    // Two clicks: the chat's facts disappear until they are extracted again.
    if (!conversation || !confirmed(rebuildButton, 'act.rebuild_confirm', 'primary')) return;
    rebuildButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<ActionResult>('POST', `/v1/conversations/${conversation}/rebuild`, {}, 30_000);
      say(actionMsg, L('act.rebuild_done', { d: r.discarded ?? 0, t: r.queued.extract ?? 0 }), 'ok');
      deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { rebuildButton.disabled = false; }
  });
  deleteButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    // Two clicks: everything NMOS recorded for this chat is deleted and cannot be restored (ADR 0009).
    if (!conversation || !confirmed(deleteButton, 'act.delete_confirm', 'danger')) return;
    deleteButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<{ deleted: { messages?: number } }>('POST', `/v1/conversations/${conversation}/delete`, {}, 60_000);
      visited.length = 0; // the deleted conversation's pages are gone
      await showInspector('/v1/inspector');
      say(actionMsg, L('act.delete_done', { m: r.deleted.messages ?? 0 }), 'ok');
    } catch (error) { say(actionMsg, errorText(lang, error), 'err'); } finally { deleteButton.disabled = false; }
  });

  // --- settings tab: progress display (applied at once: it may ask PocketRisu for a permission) --
  const hudBox = el('input', { type: 'checkbox' });
  const hudMsg = el('div', { class: 'msg' });
  hudBox.addEventListener('change', async () => {
    hudBox.disabled = true;
    try {
      if (!hudBox.checked) {
        await deps.hud.disable();
        return say(hudMsg, L('hud.off'), 'muted');
      }
      const result = await deps.hud.enable();
      hudBox.checked = result === 'on';
      if (result === 'on') say(hudMsg, L('hud.on'), 'ok');
      else say(hudMsg, L(result === 'denied' ? 'hud.denied' : 'hud.unsupported'), 'warn');
    } catch (error) {
      say(hudMsg, errorText(lang, error), 'err');
    } finally {
      hudBox.disabled = false;
    }
  });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('hud.title') }), el('p', { class: 'sub', text: L('hud.sub') }),
    el('div', { class: 'check' }, hudBox, el('span', { text: L('hud.toggle') })), hudMsg));

  // --- settings tab: fields ---------------------------------------------------------------------
  const url = el('input', { spellcheck: 'false' });
  const route = el('select', {}, ...['auto', 'direct', 'server'].map((v) => el('option', { value: v, text: v })));
  const enabled = el('input', { type: 'checkbox' });
  const reserved = el('input', { type: 'number', min: 100, max: 8000 });
  const deadline = el('input', { type: 'number', min: 200, max: MAX_DEADLINE_MS, step: 100 });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('conn.title') }), el('p', { class: 'sub', text: L('conn.sub') }),
    field(L('conn.url'), url),
    el('div', { class: 'row' }, field(L('conn.route'), route), field(L('conn.budget'), reserved), field(L('conn.deadline'), deadline)),
    el('div', { class: 'check' }, enabled, el('span', { text: L('conn.enabled') })),
    el('p', { class: 'sub', text: L('conn.hint') }), el('p', { class: 'sub', text: L('conn.deadline_hint') })));

  function modelSection(kind: 'llm' | 'embeddings', title: StringKey, sub: StringKey, presets: Preset[]) {
    const preset = el('select', {}, ...presets.map((p, i) => el('option', { value: String(i),
      text: p.label.includes('.') ? L(p.label as StringKey) : p.label })));
    const endpoint = el('input', { placeholder: 'https://…/v1', spellcheck: 'false' });
    const model = el('input', { placeholder: L(kind === 'llm' ? 'model.llm_placeholder' : 'model.emb_placeholder'), spellcheck: 'false' });
    const list = el('select', { style: 'display:none' });
    const key = el('input', { type: 'password', placeholder: L('model.key_placeholder'), autocomplete: 'off' });
    const msg = el('div', { class: 'msg' });
    const load = el('button', { text: L('model.load') });
    const test = el('button', { text: L('model.test') });
    preset.addEventListener('change', () => {
      const p = presets[Number(preset.value)] as Preset;
      if (p.url !== 'custom') endpoint.value = fillProject(p.url, key.value);
      if (p.model) model.value = p.model;
      if (!p.url) model.value = '';
      say(msg, p.url.includes('{project}') ? L('model.vertex_hint') : '');
      update();
    });
    key.addEventListener('input', () => { endpoint.value = fillProject(endpoint.value, key.value); });
    list.addEventListener('change', () => { model.value = list.value; update(); });
    load.addEventListener('click', async () => {
      say(msg, L('model.loading'));
      try {
        const r = await deps.api<{ ok: boolean; models: string[]; error?: string }>('POST', '/v1/config/models',
          { kind, url: endpoint.value.trim(), api_key: key.value.trim() || undefined });
        if (!r.ok) return say(msg, L('model.list_failed', { e: r.error ?? '' }), 'err');
        list.replaceChildren(el('option', { value: '', text: L('model.pick', { n: r.models.length }) }),
          ...r.models.map((m) => el('option', { value: m, text: m })));
        list.style.display = '';
        say(msg, L('model.found', { n: r.models.length }), 'ok');
      } catch (error) { say(msg, errorText(lang, error), 'err'); }
    });
    test.addEventListener('click', async () => {
      test.disabled = true;
      say(msg, L('model.testing'));
      try {
        const r = await deps.api<{ ok: boolean; ms: number; dimensions?: number; error?: string }>('POST', '/v1/config/test',
          { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || undefined });
        say(msg, r.ok ? L('model.test_ok', { ms: r.ms }) + (r.dimensions ? L('model.dims', { n: r.dimensions }) : '')
          : L('model.test_failed', { e: r.error ?? '' }), r.ok ? 'ok' : 'err');
      } catch (error) { say(msg, errorText(lang, error), 'err'); } finally { test.disabled = false; }
    });
    settingsView.append(el('div', { class: 'card' },
      el('h2', { text: L(title) }), el('p', { class: 'sub', text: L(sub) }),
      field(L('model.provider'), preset), field(L('model.endpoint'), endpoint),
      field(L('model.model'), model), list, field(L('model.key'), key),
      el('div', { class: 'btns' }, load, test), msg));
    return {
      values: () => ({ url: endpoint.value, model: model.value, key: key.value }),
      fill(cfg: { url: string; model: string; api_key_set: boolean }) {
        preset.value = String(presetIndex(presets, cfg.url));
        endpoint.value = cfg.url;
        model.value = cfg.model;
        key.value = '';
        key.placeholder = L(cfg.api_key_set ? 'model.key_saved' : 'model.key_placeholder');
      },
    };
  }
  const llm = modelSection('llm', 'llm.title', 'llm.sub', LLM_PRESETS);
  const emb = modelSection('embeddings', 'emb.title', 'emb.sub', EMBED_PRESETS);

  const threshold = el('input', { type: 'number', step: 0.05, min: 0.05, max: 1 });
  const minSim = el('input', { type: 'number', step: 0.01, min: 0, max: 1 });
  const topK = el('input', { type: 'number', min: 0, max: 20 });
  const factsLimit = el('input', { type: 'number', min: 0, max: 30 });
  const backfill = el('input', { type: 'number', min: 0, max: 5000 });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('tune.title') }), el('p', { class: 'sub', text: L('tune.sub') }),
    el('div', { class: 'row' }, field(L('tune.threshold'), threshold), field(L('tune.min_sim'), minSim)),
    el('div', { class: 'row' }, field(L('tune.top_k'), topK), field(L('tune.facts'), factsLimit), field(L('tune.backfill'), backfill))));

  const rules = el('textarea', { spellcheck: 'false' });
  const example = el('button', { text: L('rules.example') });
  example.addEventListener('click', () => { rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2); update(); });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('rules.title') }), el('p', { class: 'sub', text: L('rules.sub') }),
    rules, el('div', { class: 'btns' }, example)));

  // --- settings tab: one save bar ---------------------------------------------------------------
  const barText = el('span', { class: 'text muted' });
  const revert = el('button', { text: L('revert') });
  const save = el('button', { class: 'primary', text: L('save') });
  const bar = el('div', { class: 'bar' }, barText, revert, save);
  root.append(bar);

  function values(): FormValues {
    return {
      conn: { url: url.value, route: route.value, enabled: enabled.checked, reserved: reserved.value, deadline: deadline.value },
      llm: llm.values(), emb: emb.values(),
      tune: { threshold: threshold.value, minSim: minSim.value, topK: topK.value, facts: factsLimit.value, backfill: backfill.value },
      rules: rules.value,
    };
  }
  let baseline: FormValues = values();
  let closing = false;
  const dirty = () => dirtySections(baseline, values());

  function update(message?: { text: string; kind: 'ok' | 'err' | 'warn' | 'muted' }): void {
    const d = dirty();
    save.disabled = d.length === 0;
    revert.disabled = d.length === 0;
    if (message) say(barText, message.text, message.kind);
    else if (d.length) say(barText, L('unsaved', { s: d.map((s) => L(SECTION_TITLE[s])).join(', ') }), 'warn');
    else say(barText, '', 'muted');
  }
  settingsView.addEventListener('input', () => update());
  settingsView.addEventListener('change', () => update());

  async function loadConn(): Promise<void> {
    url.value = (await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790';
    route.value = (await deps.getArg('route')) || 'auto';
    enabled.checked = Number(await deps.getArg('disabled')) !== 1;
    reserved.value = String(Number(await deps.getArg('reserved_memory_tokens')) || 600);
    deadline.value = String(Number(await deps.getArg('deadline_ms')) || DEFAULT_DEADLINE_MS);
    hudBox.checked = Number(await deps.getArg('hud')) === 1;
  }

  function fillServer(cfg: ServerConfig): void {
    llm.fill(cfg.llm); emb.fill(cfg.embeddings);
    threshold.value = String(cfg.recall.threshold);
    minSim.value = String(cfg.recall.vector_min_sim);
    topK.value = String(cfg.recall.top_k);
    factsLimit.value = String(cfg.recall.facts_limit);
    backfill.value = String(cfg.extraction.backfill);
    rules.value = cfg.parsers.source === 'ui' ? JSON.stringify(cfg.parsers.rules, null, 2) : '';
    rules.placeholder = cfg.parsers.source === 'file' ? L('rules.from_file', { n: cfg.parsers.active_rules }) : L('rules.none');
  }

  async function loadAll(): Promise<void> {
    await loadConn();
    try { fillServer(await deps.api<ServerConfig>('GET', '/v1/config', undefined, 5000)); } catch { /* the status tab shows why */ }
    baseline = values();
    update();
  }

  async function saveAll(): Promise<boolean> {
    const d = dirty();
    if (!d.length) { update({ text: L('no_changes'), kind: 'muted' }); return true; }
    save.disabled = true;
    say(barText, L('saving'));
    const v = values();
    if (d.includes('conn')) {
      // First, so the server update below already goes to a changed sidecar address.
      for (const [k, value] of Object.entries(connArgs(v.conn))) await deps.setArg(k, value);
      baseline = { ...baseline, conn: v.conn };
    }
    const body = configBody(d, v);
    if (!Object.keys(body).length) { update({ text: L('saved'), kind: 'ok' }); return true; }
    try {
      const r = await deps.api<ServerConfig>('PUT', '/v1/config', body);
      fillServer(r);
      baseline = values();
      const parts = [r.queued_jobs ? L('saved_queued', { n: r.queued_jobs }) : L('saved')];
      if (r.queued_jobs) deps.hud.background();
      if (d.includes('rules') && r.parsers.active_rules) parts.push(L('saved_rules', { n: r.parsers.active_rules }));
      update({ text: parts.join(' '), kind: 'ok' });
      return true;
    } catch (error) {
      const text = errorText(lang, error);
      update({ text: d.includes('conn') ? L('conn_saved_server_failed', { e: text }) : text, kind: 'err' });
      return false;
    }
  }

  save.addEventListener('click', () => void saveAll());
  revert.addEventListener('click', () => void loadAll());

  // --- closing, language, tabs ------------------------------------------------------------------
  function shut(): void {
    root.remove();
    current = null;
    void deps.hide();
  }
  close.addEventListener('click', () => {
    if (!dirty().length || closing) return shut();
    closing = true;
    const saveClose = el('button', { class: 'primary', text: L('save_and_close') });
    const discard = el('button', { text: L('discard_and_close') });
    const cancel = el('button', { text: L('cancel') });
    const restore = () => { closing = false; bar.replaceChildren(barText, revert, save); update(); };
    saveClose.addEventListener('click', async () => { if (await saveAll()) shut(); else restore(); });
    discard.addEventListener('click', shut);
    cancel.addEventListener('click', restore);
    select('settings');
    bar.replaceChildren(el('span', { class: 'text warn', text: L('close_unsaved') }), cancel, discard, saveClose);
  });

  language.addEventListener('change', async () => {
    if (dirty().length) {
      language.value = lang;
      select('settings');
      update({ text: L('lang_unsaved'), kind: 'warn' });
      return;
    }
    const next = langOf(language.value);
    await deps.setArg('language', next);
    root.remove();
    current = await render(deps, next, shown);
  });

  function select(next: Tab): void {
    shown = next;
    const views: [Tab, HTMLElement, HTMLElement][] = [
      ['status', statusView, tabStatus], ['inspector', inspectorView, tabInspector], ['settings', settingsView, tabSettings]];
    for (const [name, view, button] of views) {
      view.style.display = name === next ? '' : 'none';
      button.className = name === next ? 'on' : '';
    }
    bar.style.display = next === 'settings' ? '' : 'none';
    root.classList.toggle('wide', next === 'inspector');
    if (next === 'status') void refreshStatus();
    if (next === 'inspector') void showInspector();
  }
  tabStatus.addEventListener('click', () => select('status'));
  tabInspector.addEventListener('click', () => select('inspector'));
  tabSettings.addEventListener('click', () => select('settings'));

  document.body.append(root);
  select(tab);
  await loadAll();
  return { root, select };
}
