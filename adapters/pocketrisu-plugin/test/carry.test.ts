// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest';
import { createChatSwitch } from '../src/chatoff';
import { localTime } from '../src/inspector';
import type { Method } from '../src/restore';
import { openPanel, type PanelDeps } from '../src/ui';
import type { CarryLink, CarryPreview, CarryState } from '../src/carrytext';

const cid = '0190f3a4-1b2c-7d3e-8f40-000000000010';
const srcA = '0190f3a4-1b2c-7d3e-8f40-000000000020';
const srcB = '0190f3a4-1b2c-7d3e-8f40-000000000030';
const linkId1 = '0190f3a4-1b2c-7d3e-8f40-0000000000a1';
const linkId2 = '0190f3a4-1b2c-7d3e-8f40-0000000000a2';

const TITLES = { ko: '이전 채팅 이어받기', en: "Carry an earlier chat's memory" } as const;
const settle = async () => { for (let i = 0; i < 8; i += 1) await new Promise((r) => setTimeout(r, 0)); };
const panel = () => document.getElementById('nmos-panel')!;
const carryCardOf = (lang: 'ko' | 'en') =>
  [...panel().querySelectorAll<HTMLElement>('.card')].find((c) => c.querySelector('h2')?.textContent === TITLES[lang]) ?? null;

function makePreview(overrides: Partial<CarryPreview> = {}): CarryPreview {
  return {
    mode: 'continue',
    source: { id: srcA, character: '세라', chat: '항구' },
    cutoff: { commit: '0190f3a4-1b2c-7d3e-8f40-0000000000c1', position: 30, turn: 15 },
    counts: { facts: 14, aliases: 2, threads: 3, story: true },
    first_lines: ['세라가 등대 열쇠를 맡겼다', '카이토와 부두에서 만나기로 했다'],
    characters: ['세라', '카이토', '하나'],
    fingerprint: 'fp-initial-1',
    replaces: null,
    ...overrides,
  };
}

function makeLink(overrides: Partial<CarryLink> = {}): CarryLink {
  return {
    id: linkId1,
    target_conversation_id: cid,
    source_conversation_id: srcA,
    mode: 'continue',
    entity_names: [],
    cutoff_commit_id: '0190f3a4-1b2c-7d3e-8f40-0000000000c1',
    cutoff_position: 30,
    cutoff_turn: 15,
    created_at: '2026-10-01T09:30:00Z',
    removed_at: null,
    source: { id: srcA, character: '세라', chat: '항구' },
    ...overrides,
  };
}

interface HarnessOpts {
  lang: 'ko' | 'en';
  carry: CarryState | '404';
  chats?: { id: string; host_character_name?: string | null; host_chat_name?: string | null; messages?: number }[];
  metaChats?: { id: string; name: string }[];
  onPreview?: (body: Record<string, unknown>, count: number) => CarryPreview | Promise<CarryPreview>;
  onLink?: (body: Record<string, unknown>, count: number) => { link: CarryLink; replaced: string | null } | Promise<{ link: CarryLink; replaced: string | null }>;
  onDelete?: () => { removed: CarryLink } | Promise<{ removed: CarryLink }>;
}

async function openThisChat(opts: HarnessOpts) {
  let state: CarryState | '404' = opts.carry;
  const calls: [Method, string, unknown][] = [];
  let previewCount = 0;
  let linkCount = 0;
  const chats = opts.chats ?? [
    { id: cid, host_character_name: '유나', host_chat_name: '현재 채팅', messages: 4 },
    { id: srcA, host_character_name: '세라', host_chat_name: '항구', messages: 30 },
    { id: srcB, host_character_name: '카이토', host_chat_name: '방앗간', messages: 12 },
  ];

  const d: PanelDeps = {
    api: async <T>(method: Method, address: string, body?: unknown) => {
      const path = address.split('?')[0]!;
      calls.push([method, address, body]);
      if (path === '/v1/views/hub') {
        return {
          html: '<div class="v"><a class="v-block" data-act="settings"><span>Settings</span></a></div>',
          conversation: cid,
          meta: {
            conv: { id: cid, name: '유나 · 현재 채팅', turns: 4 },
            ...(opts.metaChats ? { chats: opts.metaChats } : {}),
          },
        } as T;
      }
      if (path.startsWith('/v1/views/')) return { html: '<div class="v"></div>' } as T;
      if (path === '/v1/conversations' && address.includes('host=pocketrisu')) return chats as T;
      if (path === `/v1/conversations/${cid}/entities`) return [] as T;
      if (path.endsWith('/memory-mode') || path.includes('/status/candidates')) throw new Error(`${path} -> HTTP 404: Not Found`);
      if (path === `/v1/conversations/${cid}/carry` && method === 'GET') {
        if (state === '404') throw new Error(`${path} -> HTTP 404: Not Found`);
        return state as T;
      }
      if (path === `/v1/conversations/${cid}/carry/preview` && method === 'POST') {
        previewCount += 1;
        if (opts.onPreview) return await opts.onPreview(body as Record<string, unknown>, previewCount) as T;
        return makePreview() as T;
      }
      if (path === `/v1/conversations/${cid}/carry` && method === 'POST') {
        linkCount += 1;
        const b = body as Record<string, unknown>;
        const out = opts.onLink
          ? await opts.onLink(b, linkCount)
          : {
            link: makeLink({
              id: linkId2,
              source_conversation_id: String(b.source_conversation_id),
              mode: b.mode as 'continue' | 'regression',
              entity_names: (b.entity_names as string[]) ?? [],
              cutoff_turn: (b.cutoff_turn as number | null) ?? 15,
            }),
            replaced: state !== '404' && state.in_force ? state.in_force.id : null,
          };
        state = { in_force: out.link, removed: state !== '404' ? state.removed : [] };
        return out as T;
      }
      if (path === `/v1/conversations/${cid}/carry` && method === 'DELETE') {
        const out = opts.onDelete ? await opts.onDelete() : { removed: makeLink({ removed_at: '2026-10-02T00:00:00Z' }) };
        state = { in_force: null, removed: [out.removed] };
        return out as T;
      }
      return {} as T;
    },
    status: async () => ({
      enabled: true, sidecarUrl: 'http://127.0.0.1:8790', language: opts.lang, connected: true,
      version: '0.6.0', features: { views: true }, last: null,
    }),
    getArg: async (key) => (key === 'language' ? opts.lang : ''),
    setArg: async () => {},
    show: async () => {},
    hide: async () => {},
    hud: { enable: async () => 'unsupported', disable: async () => {}, problem: () => null, background: () => {} },
    chat: createChatSwitch({ getArg: async () => '', setArg: async () => {}, currentChatId: async () => 'host-chat-1' }),
    download: async () => 0,
  };

  await openPanel(d, 'status');
  await settle();
  panel().querySelector<HTMLAnchorElement>('a[data-act="settings"]')!.click();
  await settle();
  panel().querySelector<HTMLButtonElement>('.groups button[data-group="chat"]')!.click();
  await settle();
  return { calls, setState: (next: CarryState) => { state = next; } };
}

describe("carry another chat's memory card in Settings -> This chat (PHASE-60 S6)", () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.replaceChildren();
  });

  it('hides the carry card completely when GET /carry answers 404 (older sidecar)', async () => {
    for (const lang of ['ko', 'en'] as const) {
      await openThisChat({ lang, carry: '404' });
      expect(carryCardOf(lang)).toBeNull();
      const page = panel().querySelector<HTMLElement>('[data-group="chat"]:not(button)')!;
      expect(page.querySelector('.maint-list')).not.toBeNull();
      document.body.replaceChildren();
    }
  });

  it('renders picker (excluding this chat), modes, cutoff, continue preview and links with expect', async () => {
    for (const lang of ['ko', 'en'] as const) {
      const { calls } = await openThisChat({ lang, carry: { in_force: null, removed: [] } });
      const card = carryCardOf(lang)!;
      expect(card).not.toBeNull();
      expect(card.closest('[data-group="chat"]')).not.toBeNull();

      // Picker excludes this chat
      const select = card.querySelector<HTMLSelectElement>('select')!;
      const optionValues = [...select.options].map((o) => o.value);
      expect(optionValues).toEqual([srcA, srcB]);
      expect(optionValues).not.toContain(cid);

      // Both radios + plain one-line descriptions
      const radios = [...card.querySelectorAll<HTMLInputElement>('input[type="radio"]')];
      expect(radios.map((r) => r.value)).toEqual(['continue', 'regression']);
      expect(radios[0]!.checked).toBe(true);
      expect(card.textContent).toContain(lang === 'ko' ? '이어가기' : 'Continue');
      expect(card.textContent).toContain(lang === 'ko' ? '회귀' : 'Regression');
      if (lang === 'ko') {
        expect(card.textContent).toContain('이 채팅이 그 채팅의 이야기를 이어갑니다');
        expect(card.textContent).toContain('이야기가 처음부터 다시 시작됐고, 고른 인물만 이전 타임라인을 기억합니다');
        expect(card.textContent).not.toMatch(/carry|fingerprint|regression/i);
      }

      // Preview with empty cutoff -> cutoff_turn: null
      const previewBtn = [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '미리 보기' : 'Preview'))!;
      previewBtn.click();
      await settle();

      const previewCall = calls.find(([m, p]) => m === 'POST' && p.endsWith('/carry/preview'))!;
      expect(previewCall[2]).toEqual({
        source_conversation_id: srcA,
        mode: 'continue',
        entity_names: [],
        cutoff_turn: null,
      });

      // Preview renders counts, first lines, source, cutoff, and plain caveats; nothing monospace
      const pv = card.querySelector<HTMLElement>('.preview')!;
      expect(pv).not.toBeNull();
      expect(pv.querySelector('.mono')).toBeNull();
      expect(pv.textContent).toContain('세라 · 항구');
      expect(pv.textContent).toContain(lang === 'ko' ? 't15까지' : 'through t15');
      expect(pv.textContent).toContain('14');
      expect(pv.textContent).toContain('세라가 등대 열쇠를 맡겼다');
      expect(pv.textContent).toContain(lang === 'ko' ? '한 번만 읽으며' : 'read once now');
      expect(pv.textContent).toContain(lang === 'ko' ? '비용이 들지 않습니다' : 'costs nothing');
      expect(pv.textContent).toContain(lang === 'ko' ? '연결 해제' : 'Unlink');

      // Cancel and re-preview with a typed cutoff turn (12)
      const cancelBtn = [...pv.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '취소' : 'Cancel'))!;
      cancelBtn.click();
      expect(card.querySelector('.preview')).toBeNull();

      const cutoffInput = card.querySelector<HTMLInputElement>('input[type="number"]')!;
      cutoffInput.value = '12';
      cutoffInput.dispatchEvent(new Event('input'));
      previewBtn.click();
      await settle();

      const secondPreview = calls.filter(([m, p]) => m === 'POST' && p.endsWith('/carry/preview')).at(-1)!;
      expect(secondPreview[2]).toEqual({
        source_conversation_id: srcA,
        mode: 'continue',
        entity_names: [],
        cutoff_turn: 12,
      });

      // Link sends the same body plus expect: fingerprint
      const linkBtn = [...card.querySelectorAll('.preview button')].find((b) => b.textContent === (lang === 'ko' ? '연결' : 'Link'))!;
      linkBtn.click();
      await settle();

      const linkCall = calls.find(([m, p]) => m === 'POST' && p.endsWith('/carry'))!;
      expect(linkCall[2]).toEqual({
        source_conversation_id: srcA,
        mode: 'continue',
        entity_names: [],
        cutoff_turn: 12,
        expect: 'fp-initial-1',
      });
      expect(card.querySelector('.msg')!.textContent).toBe(
        lang === 'ko' ? '이전 채팅의 기억을 연결했습니다.' : "Linked the earlier chat's memory.",
      );
      document.body.replaceChildren();
    }
  });

  it('handles regression mode: character checkboxes, disabled Link with 0 ticked, regression preview with ticked names, max 8 cap', async () => {
    const tenChars = ['세라', '카이토', '하나', '유나', '유준', '지호', '수진', '태현', '유현', '다인'];
    for (const lang of ['ko', 'en'] as const) {
      const { calls } = await openThisChat({
        lang,
        carry: { in_force: null, removed: [] },
        onPreview: (body) => {
          if (body.mode === 'continue') return makePreview({ characters: tenChars, fingerprint: 'fp-discover' });
          return makePreview({
            mode: 'regression',
            characters: tenChars,
            counts: { facts: 5, aliases: 0, threads: 1, story: false },
            first_lines: ['세라는 항구의 사건을 기억한다'],
            fingerprint: `fp-reg-${(body.entity_names as string[]).join(',')}`,
          });
        },
      });
      const card = carryCardOf(lang)!;
      const regRadio = card.querySelector<HTMLInputElement>('input[type="radio"][value="regression"]')!;
      regRadio.checked = true;
      regRadio.dispatchEvent(new Event('change'));

      const previewBtn = [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '미리 보기' : 'Preview'))!;
      previewBtn.click();
      await settle();

      // Discovery preview used continue mode to list characters
      const previewCalls = () => calls.filter(([m, p]) => m === 'POST' && p.endsWith('/carry/preview'));
      expect(previewCalls()).toHaveLength(1);
      expect(previewCalls()[0]![2]).toEqual({
        source_conversation_id: srcA,
        mode: 'continue',
        entity_names: [],
        cutoff_turn: null,
      });

      const pv = card.querySelector<HTMLElement>('.preview')!;
      const checkboxes = [...pv.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
      expect(checkboxes.map((c) => c.value)).toEqual(tenChars);
      const linkBtn = [...pv.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '연결' : 'Link')) as HTMLButtonElement;
      expect(linkBtn.disabled).toBe(true);

      // Tick 세라 -> regression preview refreshed with ['세라']
      checkboxes[0]!.checked = true;
      checkboxes[0]!.dispatchEvent(new Event('change'));
      await settle();

      expect(previewCalls()).toHaveLength(2);
      expect(previewCalls()[1]![2]).toEqual({
        source_conversation_id: srcA,
        mode: 'regression',
        entity_names: ['세라'],
        cutoff_turn: null,
      });
      expect(pv.textContent).toContain('세라는 항구의 사건을 기억한다');
      expect(linkBtn.disabled).toBe(false);

      // Tick up to 8 -> 9th and 10th checkboxes are disabled
      for (let i = 1; i < 8; i += 1) {
        checkboxes[i]!.checked = true;
        checkboxes[i]!.dispatchEvent(new Event('change'));
      }
      await settle();
      expect(checkboxes[8]!.disabled).toBe(true);
      expect(checkboxes[9]!.disabled).toBe(true);

      // Untick all -> Link disabled again
      for (let i = 0; i < 8; i += 1) {
        checkboxes[i]!.checked = false;
        checkboxes[i]!.dispatchEvent(new Event('change'));
      }
      await settle();
      expect(linkBtn.disabled).toBe(true);

      // Tick 세라 and 카이토, then Link
      checkboxes[0]!.checked = true;
      checkboxes[0]!.dispatchEvent(new Event('change'));
      checkboxes[1]!.checked = true;
      checkboxes[1]!.dispatchEvent(new Event('change'));
      await settle();

      expect(linkBtn.disabled).toBe(false);
      linkBtn.click();
      await settle();

      const linkCall = calls.find(([m, p]) => m === 'POST' && p.endsWith('/carry'))!;
      expect(linkCall[2]).toEqual({
        source_conversation_id: srcA,
        mode: 'regression',
        entity_names: ['세라', '카이토'],
        cutoff_turn: null,
        expect: 'fp-reg-세라,카이토',
      });
      document.body.replaceChildren();
    }
  });

  it('refreshes preview on 409 conflict with the changed sentence and sends the new fingerprint on retry', async () => {
    for (const lang of ['ko', 'en'] as const) {
      const { calls } = await openThisChat({
        lang,
        carry: { in_force: null, removed: [] },
        onPreview: (_body, n) => makePreview({
          fingerprint: n === 1 ? 'fp-v1' : 'fp-v2',
          counts: { facts: n === 1 ? 10 : 12, aliases: 1, threads: 1, story: true },
        }),
        onLink: (body, n) => {
          if (n === 1) throw new Error(`/v1/conversations/${cid}/carry -> HTTP 409: [object Object]`);
          return { link: makeLink({ id: linkId2 }), replaced: null };
        },
      });
      const card = carryCardOf(lang)!;
      [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '미리 보기' : 'Preview'))!.click();
      await settle();

      [...card.querySelectorAll('.preview button')].find((b) => b.textContent === (lang === 'ko' ? '연결' : 'Link'))!.click();
      await settle();

      // A second preview was requested and rendered with the changed notice (and no bare status code)
      const previews = calls.filter(([m, p]) => m === 'POST' && p.endsWith('/carry/preview'));
      expect(previews).toHaveLength(2);
      const pv = card.querySelector<HTMLElement>('.preview')!;
      expect(pv.textContent).toContain(lang === 'ko' ? '원본 채팅이 바뀌었습니다' : 'source chat changed');
      expect(pv.textContent).not.toMatch(/\b409\b|HTTP/);

      // Second Link uses the refreshed fingerprint
      [...pv.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '연결' : 'Link'))!.click();
      await settle();

      const links = calls.filter(([m, p]) => m === 'POST' && p.endsWith('/carry'));
      expect(links).toHaveLength(2);
      expect((links[0]![2] as Record<string, unknown>).expect).toBe('fp-v1');
      expect((links[1]![2] as Record<string, unknown>).expect).toBe('fp-v2');
      document.body.replaceChildren();
    }
  });

  it('shows plain sentences for size-limit 422 and other 422 errors with no status code', async () => {
    for (const lang of ['ko', 'en'] as const) {
      let errKind: 'size' | 'other' = 'size';
      await openThisChat({
        lang,
        carry: { in_force: null, removed: [] },
        onPreview: () => {
          if (errKind === 'size') {
            throw new Error(`/v1/conversations/${cid}/carry/preview -> HTTP 422: the reading holds 2345 rows; a link carries at most 2000`);
          }
          throw new Error(`/v1/conversations/${cid}/carry/preview -> HTTP 422: turn 999 is not on the source's current head`);
        },
      });
      const card = carryCardOf(lang)!;
      const previewBtn = [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '미리 보기' : 'Preview'))!;

      previewBtn.click();
      await settle();
      const sizeMsg = card.querySelector('.msg')!.textContent!;
      expect(sizeMsg).toBe(
        lang === 'ko'
          ? '이 채팅의 기억이 너무 많아 이어받을 수 없습니다 (2345줄, 최대 2000줄). 더 이른 턴에서 끊어 보세요.'
          : 'This chat has too much memory to carry (2345 lines, maximum 2000). Try cutting off at an earlier turn.',
      );
      expect(sizeMsg).not.toMatch(/\b422\b|HTTP/);

      errKind = 'other';
      previewBtn.click();
      await settle();
      const otherMsg = card.querySelector('.msg')!.textContent!;
      expect(otherMsg).toBe(
        lang === 'ko'
          ? "입력 오류: turn 999 is not on the source's current head"
          : "Invalid: turn 999 is not on the source's current head",
      );
      expect(otherMsg).not.toMatch(/\b422\b|HTTP/);
      document.body.replaceChildren();
    }
  });

  it('shows linked regression state (source, mode, names, cutoff, local time), Read again with link values, and two-tap Unlink', async () => {
    const link = makeLink({
      mode: 'regression',
      entity_names: ['세라', '카이토'],
      cutoff_turn: 24,
      created_at: '2026-09-15T08:45:00Z',
    });
    for (const lang of ['ko', 'en'] as const) {
      const { calls } = await openThisChat({
        lang,
        carry: { in_force: link, removed: [] },
        onPreview: () => makePreview({
          mode: 'regression',
          counts: { facts: 6, aliases: 0, threads: 1, story: false },
          replaces: link.id,
          fingerprint: 'fp-reread',
        }),
      });
      const card = carryCardOf(lang)!;
      expect(card.textContent).toContain('세라 · 항구');
      expect(card.textContent).toContain(lang === 'ko' ? '회귀' : 'Regression');
      expect(card.textContent).toContain(lang === 'ko' ? '세라, 카이토만 기억' : 'Only 세라, 카이토 remember');
      expect(card.textContent).toContain(lang === 'ko' ? 't24까지' : 'through t24');
      const expectedTime = localTime(link.created_at, lang)!.text;
      expect(card.textContent).toContain(expectedTime);

      // Read again sends the link's own values and shows the replaces notice
      const readAgain = [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '다시 읽기' : 'Read again'))!;
      readAgain.click();
      await settle();

      const previewCall = calls.find(([m, p]) => m === 'POST' && p.endsWith('/carry/preview'))!;
      expect(previewCall[2]).toEqual({
        source_conversation_id: link.source_conversation_id,
        mode: 'regression',
        entity_names: ['세라', '카이토'],
        cutoff_turn: 24,
      });
      const pv = card.querySelector<HTMLElement>('.preview')!;
      expect(pv.textContent).toContain(lang === 'ko' ? '현재 연결된 이전 채팅을 이 연결로 바꿉니다' : 'replaces the link currently in force');

      // Cancel preview, then test two-tap Unlink
      [...pv.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '취소' : 'Cancel'))!.click();
      const unlinkBtn = [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '연결 해제' : 'Unlink'))!;

      // First tap: arms in place, no DELETE yet
      unlinkBtn.click();
      await settle();
      expect(calls.some(([m]) => m === 'DELETE')).toBe(false);
      expect(unlinkBtn.textContent).toBe(lang === 'ko' ? '한 번 더 누르면 연결 해제' : 'Tap again to unlink');

      // Second tap: sends DELETE, reloads into unlinked state, says it is done
      unlinkBtn.click();
      await settle();
      expect(calls.some(([m, p]) => m === 'DELETE' && p === `/v1/conversations/${cid}/carry`)).toBe(true);
      expect(card.querySelector('.msg')!.textContent).toContain(lang === 'ko' ? '연결을 해제했습니다' : 'Unlinked');
      expect(card.querySelector('select')).not.toBeNull();
      document.body.replaceChildren();
    }
  });

  it('shows "끝까지" / "through the end" when a link has cutoff_turn null', async () => {
    for (const lang of ['ko', 'en'] as const) {
      await openThisChat({
        lang,
        carry: { in_force: makeLink({ cutoff_turn: null }), removed: [] },
      });
      const card = carryCardOf(lang)!;
      expect(card.textContent).toContain(lang === 'ko' ? '끝까지' : 'through the end');
      document.body.replaceChildren();
    }
  });

  it('replaces the link in force when confirming Read again', async () => {
    const link = makeLink({ mode: 'continue', cutoff_turn: 15 });
    for (const lang of ['ko', 'en'] as const) {
      const { calls } = await openThisChat({
        lang,
        carry: { in_force: link, removed: [] },
        onPreview: () => makePreview({ replaces: link.id, fingerprint: 'fp-replace-1' }),
      });
      const card = carryCardOf(lang)!;
      [...card.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '다시 읽기' : 'Read again'))!.click();
      await settle();

      const pv = card.querySelector<HTMLElement>('.preview')!;
      [...pv.querySelectorAll('button')].find((b) => b.textContent === (lang === 'ko' ? '연결' : 'Link'))!.click();
      await settle();

      const linkCall = calls.find(([m, p]) => m === 'POST' && p.endsWith('/carry'))!;
      expect(linkCall[2]).toEqual({
        source_conversation_id: link.source_conversation_id,
        mode: 'continue',
        entity_names: [],
        cutoff_turn: 15,
        expect: 'fp-replace-1',
      });
      expect(card.querySelector('.msg')!.textContent).toBe(
        lang === 'ko' ? '이전 채팅의 기억을 연결했습니다.' : "Linked the earlier chat's memory.",
      );
      document.body.replaceChildren();
    }
  });

  it('reuses hub meta knownChats without refetching, refuses negative cutoff locally, and handles no other chats', async () => {
    const { calls } = await openThisChat({
      lang: 'ko',
      carry: { in_force: null, removed: [] },
      metaChats: [{ id: cid, name: '유나 · 현재 채팅' }, { id: srcB, name: '카이토 · 방앗간' }],
    });
    // loadAll() fetches once for parser cards at open; showCarry reuses metaChats and does not fetch again.
    expect(calls.filter(([, p]) => p === '/v1/conversations?host=pocketrisu')).toHaveLength(1);
    const card = carryCardOf('ko')!;
    expect([...card.querySelectorAll<HTMLOptionElement>('select option')].map((o) => o.value)).toEqual([srcB]);

    const cutoffInput = card.querySelector<HTMLInputElement>('input[type="number"]')!;
    cutoffInput.value = '-5';
    cutoffInput.dispatchEvent(new Event('input'));
    [...card.querySelectorAll('button')].find((b) => b.textContent === '미리 보기')!.click();
    await settle();
    expect(calls.some(([m, p]) => m === 'POST' && p.endsWith('/carry/preview'))).toBe(false);
    expect(card.querySelector('.msg')!.textContent).toBe('턴 번호는 0 이상의 정수로 입력하거나 비워 두세요.');
    document.body.replaceChildren();

    await openThisChat({
      lang: 'en',
      carry: { in_force: null, removed: [] },
      chats: [{ id: cid, host_character_name: '유나', host_chat_name: '현재 채팅', messages: 4 }],
    });
    const emptyCard = carryCardOf('en')!;
    expect(emptyCard.textContent).toContain('No other recorded chats are available to carry from.');
    expect(emptyCard.querySelector('select')).toBeNull();
  });
});
