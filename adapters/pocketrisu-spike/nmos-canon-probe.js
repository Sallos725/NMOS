//@name nmos_canon_probe
//@display-name NMOS Canon Probe
//@api 3.0
//@version 0.1.0

// Phase 14 step 2 host observation (docs/phases/PHASE-14.md, Q8). It never alters the prompt and never writes host
// data. At every request it reads the canon the V3 API exposes and logs, under [NMOS-CANON], only shapes: which calls
// exist and how long they take, field lengths and counts, content hashes, and which canon texts the outgoing prompt
// holds. Run it against synthetic data only.

(async () => {
  'use strict';

  const PREFIX = '[NMOS-CANON]';
  let seq = 0;

  async function sha(text) {
    const bytes = new TextEncoder().encode(text ?? '');
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest).slice(0, 6), (b) => b.toString(16).padStart(2, '0')).join('');
  }
  const len = (s) => (typeof s === 'string' ? s.length : null);
  const keys = (e) => `${e?.key ?? ''},${e?.secondkey ?? ''}`.split(/[,\n]/).map((k) => k.trim()).filter(Boolean);
  async function timed(name, fn, out) {
    const t = performance.now();
    try {
      const value = await fn();
      out.ms[name] = Math.round((performance.now() - t) * 10) / 10;
      return value;
    } catch (error) {
      out.errors[name] = String(error?.message ?? error).slice(0, 160);
      return undefined;
    }
  }

  console.log(PREFIX, 'loaded', {
    getCharacter: typeof risuai.getCharacter,
    getCurrentLorebookEntries: typeof risuai.getCurrentLorebookEntries,
    getChatFromIndex: typeof risuai.getChatFromIndex,
    getCurrentCharacterIndex: typeof risuai.getCurrentCharacterIndex,
    getCurrentChatIndex: typeof risuai.getCurrentChatIndex,
    getDatabase: typeof risuai.getDatabase,
  });

  await risuai.addRisuReplacer('beforeRequest', async (formated, mode) => {
    seq += 1;
    const out = { seq, mode, ms: {}, errors: {} };
    try {
      const prompt = (formated ?? []).map((m) => (typeof m?.content === 'string' ? m.content : '')).join('\n');
      const holds = (text) => (typeof text === 'string' && text.trim() ? prompt.includes(text.trim()) : null);
      const char = await timed('getCharacter', () => risuai.getCharacter(), out);
      const lore = await timed('getCurrentLorebookEntries', () => risuai.getCurrentLorebookEntries(), out);
      const ci = await timed('getCurrentCharacterIndex', () => risuai.getCurrentCharacterIndex(), out);
      const chi = await timed('getCurrentChatIndex', () => risuai.getCurrentChatIndex(), out);
      const chat = await timed('getChatFromIndex', () => risuai.getChatFromIndex(ci, chi), out);
      const db = await timed('getDatabase', () => risuai.getDatabase(['personas', 'selectedPersona', 'modules', 'enabledModules']), out);
      const greetings = [char?.firstMessage, ...(char?.alternateGreetings ?? [])];
      out.card = {
        name: len(char?.name), desc: len(char?.desc), descHash: await sha(char?.desc), personality: len(char?.personality),
        scenario: len(char?.scenario), firstMessage: len(char?.firstMessage), alternateGreetings: (char?.alternateGreetings ?? []).length,
        globalLore: (char?.globalLore ?? []).length, chats: (char?.chats ?? []).length, chatPage: char?.chatPage,
        chatsMessages: (char?.chats ?? []).reduce((n, c) => n + (c?.message?.length ?? 0), 0),
        snapshotChars: char ? JSON.stringify(char).length : null,
        inPrompt: { desc: holds(char?.desc), personality: holds(char?.personality), scenario: holds(char?.scenario),
          greeting: holds(greetings[chat?.fmIndex >= 0 ? chat.fmIndex + 1 : 0]) },
      };
      out.chat = {
        fields: chat ? Object.keys(chat).filter((k) => k !== 'message').sort() : null, messages: (chat?.message ?? []).length,
        note: len(chat?.note), noteInPrompt: holds(chat?.note), localLore: (chat?.localLore ?? []).length,
        bindedPersona: chat?.bindedPersona ? 'set' : 'none', fmIndex: chat?.fmIndex, id: chat?.id ? 'set' : 'none',
      };
      out.lore = await Promise.all((lore ?? []).map(async (e) => ({
        mode: e.mode, alwaysActive: !!e.alwaysActive, selective: !!e.selective, keys: keys(e).length,
        content: len(e.content), hash: await sha(e.content), id: e.id ? 'set' : 'none', folder: e.folder ? 'set' : 'none',
        inPrompt: holds(e.content),
      })));
      const personas = db?.personas ?? null;
      const bound = personas?.find((p) => p.id === chat?.bindedPersona) ?? personas?.[db?.selectedPersona ?? 0];
      out.persona = db === null ? 'permission denied' : {
        personas: personas?.length ?? null, promptLength: len(bound?.personaPrompt), promptInPrompt: holds(bound?.personaPrompt),
        modules: (db?.modules ?? []).length, enabledModules: (db?.enabledModules ?? []).length,
        moduleLore: (db?.modules ?? []).map((m) => (m.lorebook ?? []).length),
      };
      out.promptMessages = (formated ?? []).length;
      out.promptChars = prompt.length;
    } catch (error) {
      out.errors.probe = String(error?.message ?? error).slice(0, 160);
    }
    console.log(PREFIX, 'request', JSON.stringify(out));
    return formated;
  });
})();
