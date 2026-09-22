//@name nmos_host_observation_spike
//@display-name NMOS Host Observation Spike
//@api 3.0
//@version 0.2.0
//@arg collector_url string Optional local collector URL, e.g. http://127.0.0.1:8765/spike
//@arg scenario string Current evidence label, e.g. S1-before
//@arg include_raw_snapshot int Send raw chat snapshot to collector on manual dump (0/1)
//@arg skip_output_manifest int Do not attach a full chat manifest to output observations (0/1, default 0)

// Phase 0A throwaway observation spike. It never alters the prompt and never mutates host data.
// Message bodies are hashed, never logged; only `{{specialcomment::...}}` host markers are
// recorded verbatim because their exact format is Phase 0A question Q4.

(async () => {
  'use strict';

  const PREFIX = '[NMOS-SPIKE]';
  const SPIKE_VERSION = '0.2.0';
  const HASH_FORMAT_VERSION = 1;
  const actionCounts = new Map();
  const formatedCounts = new Map();
  let beforeRequestSeq = 0;
  let lastBeforeRequestAt = null;

  // ---------------------------------------------------------------------------
  // Hashing. crypto.subtle may be missing in the sandboxed iframe when PocketRisu is served
  // over plain HTTP from a non-localhost origin (not a secure context). The pure-JS SHA-256
  // fallback keeps manifests comparable in that case; `hashMethod` records which one ran.
  // ---------------------------------------------------------------------------

  const SHA256_K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  function sha256HexFallback(bytes) {
    const bitLength = bytes.length * 8;
    const paddedLength = (((bytes.length + 9) + 63) >> 6) << 6;
    const data = new Uint8Array(paddedLength);
    data.set(bytes);
    data[bytes.length] = 0x80;
    const view = new DataView(data.buffer);
    view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000));
    view.setUint32(paddedLength - 4, bitLength >>> 0);

    const h = new Uint32Array([
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]);
    const w = new Uint32Array(64);
    const rotr = (x, n) => (x >>> n) | (x << (32 - n));

    for (let offset = 0; offset < paddedLength; offset += 64) {
      for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(offset + i * 4);
      for (let i = 16; i < 64; i += 1) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i += 1) {
        const t1 = (hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g))
          + SHA256_K[i] + w[i]) >>> 0;
        const t2 = ((rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        hh = g; g = f; f = e; e = (d + t1) >>> 0;
        d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0; h[1] = (h[1] + b) >>> 0; h[2] = (h[2] + c) >>> 0;
      h[3] = (h[3] + d) >>> 0; h[4] = (h[4] + e) >>> 0; h[5] = (h[5] + f) >>> 0;
      h[6] = (h[6] + g) >>> 0; h[7] = (h[7] + hh) >>> 0;
    }
    return Array.from(h, (x) => x.toString(16).padStart(8, '0')).join('');
  }

  const subtleAvailable = Boolean(globalThis.crypto?.subtle?.digest);
  const hashMethod = subtleAvailable ? 'crypto.subtle' : 'js-fallback';

  async function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    if (subtleAvailable) {
      const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
      return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
    }
    return sha256HexFallback(bytes);
  }

  // ---------------------------------------------------------------------------
  // Canonicalization (Phase 0B revision-hash rules: NFC, CRLF→LF, sorted keys, no trimming).
  // ---------------------------------------------------------------------------

  function normalizeString(value) {
    return String(value ?? '').normalize('NFC').replace(/\r\n/g, '\n');
  }

  function canonicalize(value) {
    if (value === null || typeof value !== 'object') {
      return typeof value === 'string' ? normalizeString(value) : value;
    }
    if (Array.isArray(value)) return value.map(canonicalize);
    const out = {};
    for (const key of Object.keys(value).sort()) {
      const v = value[key];
      if (v !== undefined) out[key] = canonicalize(v);
    }
    return out;
  }

  function canonicalJson(value) {
    return JSON.stringify(canonicalize(value));
  }

  function selectedSwipe(message) {
    if (
      Array.isArray(message?.swipes)
      && Number.isInteger(message?.swipeId)
      && message.swipeId >= 0
      && message.swipeId < message.swipes.length
    ) {
      return message.swipes[message.swipeId];
    }
    return null;
  }

  function activeContent(message) {
    return selectedSwipe(message) ?? message?.data ?? '';
  }

  function messageHashPayload(message) {
    return {
      v: HASH_FORMAT_VERSION,
      chatId: message?.chatId ?? null,
      role: message?.role ?? null,
      saying: message?.saying ?? null,
      name: message?.name ?? null,
      otherUser: message?.otherUser ?? null,
      isComment: message?.isComment ?? null,
      disabled: message?.disabled ?? null,
      swipeId: message?.swipeId ?? null,
      selectedContent: activeContent(message),
      generationId: message?.generationInfo?.generationId ?? null,
    };
  }

  const SPECIAL_COMMENT = /\{\{specialcomment::[^]*?::\}\}/g;

  function specialComments(message) {
    const text = typeof message?.data === 'string' ? message.data : '';
    return text.match(SPECIAL_COMMENT) ?? [];
  }

  async function messageManifest(message, position) {
    const swipe = selectedSwipe(message);
    const data = typeof message?.data === 'string' ? message.data : '';
    const markers = specialComments(message);
    return {
      position,
      chatId: message?.chatId ?? null,
      role: message?.role ?? null,
      name: message?.name ?? null,
      saying: message?.saying ?? null,
      otherUser: message?.otherUser ?? null,
      isComment: message?.isComment ?? null,
      swipeId: message?.swipeId ?? null,
      swipeCount: Array.isArray(message?.swipes) ? message.swipes.length : 0,
      disabled: message?.disabled ?? null,
      generationId: message?.generationInfo?.generationId ?? null,
      time: message?.time ?? null,
      contentLength: normalizeString(activeContent(message)).length,
      contentHash: await sha256Hex(canonicalJson(messageHashPayload(message))),
      dataHash: await sha256Hex(normalizeString(data)),
      dataEqualsSelectedSwipe: swipe === null ? null : normalizeString(swipe) === normalizeString(data),
      ...(markers.length ? { specialComments: markers } : {}),
    };
  }

  async function buildManifest(chat) {
    const messages = Array.isArray(chat?.message) ? chat.message : [];
    const entries = [];
    for (let i = 0; i < messages.length; i += 1) {
      entries.push(await messageManifest(messages[i], i));
    }
    return {
      hashFormatVersion: HASH_FORMAT_VERSION,
      hashMethod,
      chatId: chat?.id ?? null,
      chatNameHash: await sha256Hex(normalizeString(chat?.name ?? '')),
      messageCount: messages.length,
      manifestHash: await sha256Hex(canonicalJson(entries.map((e) => [e.chatId, e.contentHash]))),
      messages: entries,
    };
  }

  // ---------------------------------------------------------------------------
  // Prompt statistics (no bodies).
  // ---------------------------------------------------------------------------

  function contentText(content) {
    if (typeof content === 'string') return content;
    if (content == null) return '';
    return JSON.stringify(content);
  }

  async function promptStats(formated) {
    const messages = Array.isArray(formated) ? formated : [];
    let chars = 0;
    const roles = {};
    const roleSequence = [];
    for (const message of messages) {
      const role = message?.role ?? 'unknown';
      roles[role] = (roles[role] ?? 0) + 1;
      roleSequence.push(role);
      chars += contentText(message?.content).length;
    }
    return {
      messageCount: messages.length,
      roles,
      roleSequence,
      chars,
      approximateTokens: Math.ceil(chars / 4),
      formatedHash: await sha256Hex(canonicalJson(messages.map((m) => [m?.role ?? null, contentText(m?.content)]))),
    };
  }

  function lastOf(items, predicate) {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      if (predicate(items[i])) return items[i];
    }
    return null;
  }

  // Does the outgoing prompt contain the host's latest user message? Exact match after
  // normalization, then substring match (prompt templates may wrap the message).
  function latestUserInputMatch(formated, hostMessages) {
    const hostLastUser = lastOf(hostMessages, (m) => m?.role === 'user');
    if (!hostLastUser) return { hostHasUserMessage: false };
    const needle = normalizeString(activeContent(hostLastUser)).trim();
    const prompt = Array.isArray(formated) ? formated : [];
    const lastUserIdx = prompt.map((m) => m?.role).lastIndexOf('user');
    const lastUserContent = lastUserIdx >= 0 ? normalizeString(contentText(prompt[lastUserIdx].content)).trim() : null;
    const anyIdx = needle ? prompt.findIndex((m) => normalizeString(contentText(m?.content)).includes(needle)) : -1;
    return {
      hostHasUserMessage: true,
      hostLastUserIsHostTail: hostMessages[hostMessages.length - 1] === hostLastUser,
      promptLastUserIndex: lastUserIdx,
      promptLastUserExactMatch: lastUserContent !== null && lastUserContent === needle,
      promptContainsHostLastUserAt: anyIdx,
      promptLength: prompt.length,
    };
  }

  // ---------------------------------------------------------------------------
  // Host access and collector.
  // ---------------------------------------------------------------------------

  async function stringArg(key) {
    const raw = await risuai.getArgument(key);
    return String(raw ?? '').trim();
  }

  async function collectorUrl() {
    return (await stringArg('collector_url')) || null;
  }

  async function scenarioLabel() {
    return (await stringArg('scenario')) || 'unlabeled';
  }

  // PocketRisu initialises int args to 0, so the opt-out form keeps manifests on by default.
  async function outputManifestEnabled() {
    return Number(await stringArg('skip_output_manifest')) !== 1;
  }

  function environment() {
    return {
      spikeVersion: SPIKE_VERSION,
      hashMethod,
      cryptoSubtleAvailable: subtleAvailable,
      isSecureContext: globalThis.isSecureContext ?? null,
      userAgent: globalThis.navigator?.userAgent ?? null,
    };
  }

  async function sendCollector(payload) {
    const url = await collectorUrl();
    if (!url) return;
    try {
      const response = await risuai.nativeFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, environment: environment() }),
      });
      if (response && response.ok === false) {
        console.warn(PREFIX, 'collector responded', response.status);
      }
    } catch (error) {
      console.warn(PREFIX, 'collector POST failed', error);
    }
  }

  async function currentChatSnapshot() {
    const characterIndex = await risuai.getCurrentCharacterIndex();
    const chatIndex = await risuai.getCurrentChatIndex();
    const started = performance.now();
    const chat = await risuai.getChatFromIndex(characterIndex, chatIndex);
    const elapsedMs = performance.now() - started;
    return { characterIndex, chatIndex, chat, elapsedMs };
  }

  // Groups replacer calls that belong to one user action: same chat, same host tail.
  async function actionKey(chat) {
    const messages = Array.isArray(chat?.message) ? chat.message : [];
    const last = messages[messages.length - 1];
    return sha256Hex(canonicalJson({
      chatId: chat?.id ?? null,
      lastMessageId: last?.chatId ?? null,
      lastRole: last?.role ?? null,
      lastContent: activeContent(last),
    }));
  }

  function bump(map, key) {
    const value = (map.get(key) ?? 0) + 1;
    map.set(key, value);
    return value;
  }

  // ---------------------------------------------------------------------------
  // Hooks.
  // ---------------------------------------------------------------------------

  await risuai.addRisuReplacer('beforeRequest', async (formated, mode) => {
    const enteredAt = performance.now();
    try {
      beforeRequestSeq += 1;
      const now = Date.now();
      const msSincePreviousCall = lastBeforeRequestAt === null ? null : now - lastBeforeRequestAt;
      lastBeforeRequestAt = now;

      const { characterIndex, chatIndex, chat, elapsedMs: getChatElapsedMs } = await currentChatSnapshot();
      const hostMessages = Array.isArray(chat?.message) ? chat.message : [];
      const lastHost = hostMessages[hostMessages.length - 1] ?? null;
      const lastFormatted = Array.isArray(formated) ? formated[formated.length - 1] : null;
      const stats = await promptStats(formated);
      const key = await actionKey(chat);

      const observation = {
        kind: 'beforeRequest',
        scenario: await scenarioLabel(),
        timestamp: new Date(now).toISOString(),
        seq: beforeRequestSeq,
        msSincePreviousCall,
        mode,
        modeType: typeof mode,
        callCountForActionKey: bump(actionCounts, key),
        callCountForFormatedHash: bump(formatedCounts, stats.formatedHash),
        actionKey: key,
        characterIndex,
        chatIndex,
        hostChatId: chat?.id ?? null,
        hostMessageCount: hostMessages.length,
        hostLastMessage: lastHost ? {
          chatId: lastHost.chatId ?? null,
          role: lastHost.role ?? null,
          generationId: lastHost.generationInfo?.generationId ?? null,
          swipeId: lastHost.swipeId ?? null,
          swipeCount: Array.isArray(lastHost.swipes) ? lastHost.swipes.length : 0,
        } : null,
        hostTailIsUser: lastHost?.role === 'user',
        latestUserInput: latestUserInputMatch(formated, hostMessages),
        prompt: stats,
        formattedLastRole: lastFormatted?.role ?? null,
        timings: {
          getChatElapsedMs,
          observationElapsedMs: performance.now() - enteredAt,
        },
      };

      console.log(PREFIX, 'beforeRequest', observation);
      void sendCollector(observation);
    } catch (error) {
      console.warn(PREFIX, 'beforeRequest observation failed', error);
    }

    // Phase 0A requirement: never alter the host prompt.
    return formated;
  });

  async function recordOutput({ chat, characterIndex, chatIndex, messageIndex }, scenario, receivedAt) {
    const messages = Array.isArray(chat?.message) ? chat.message : [];
    const message = messageIndex >= 0 ? messages[messageIndex] ?? null : null;
    const observation = {
      kind: 'output',
      scenario,
      timestamp: new Date(receivedAt).toISOString(),
      characterIndex,
      chatIndex,
      messageIndex,
      hostChatId: chat?.id ?? null,
      hostMessageCount: messages.length,
      messageIsTail: messageIndex === messages.length - 1,
      message: message ? await messageManifest(message, messageIndex) : null,
      ...(await outputManifestEnabled() ? { manifest: await buildManifest(chat) } : {}),
    };
    console.log(PREFIX, 'output', { ...observation, manifest: observation.manifest ? '[attached]' : undefined });
    await sendCollector(observation);
  }

  await risuai.addRisuChatListener('output', async (arg) => {
    // Output listeners are awaited sequentially by PocketRisu (H7): return immediately and do
    // all work in the background. `arg` is already a plain snapshot copy.
    const receivedAt = Date.now();
    try {
      void scenarioLabel()
        .then((scenario) => recordOutput(arg ?? {}, scenario, receivedAt))
        .catch((error) => console.warn(PREFIX, 'output observation failed', error));
    } catch (error) {
      console.warn(PREFIX, 'output observation failed', error);
    }
  });

  // ---------------------------------------------------------------------------
  // Manual actions.
  // ---------------------------------------------------------------------------

  async function dumpSnapshot() {
    const scenario = await scenarioLabel();
    const { characterIndex, chatIndex, chat, elapsedMs: getChatElapsedMs } = await currentChatSnapshot();

    if (!chat) {
      console.warn(PREFIX, 'Dump snapshot: no current chat');
      return;
    }

    const serializeStarted = performance.now();
    const serialized = JSON.stringify(chat);
    const serializeElapsedMs = performance.now() - serializeStarted;
    const serializedBytes = new TextEncoder().encode(serialized).byteLength;

    const hashStarted = performance.now();
    const manifest = await buildManifest(chat);
    const manifestHashElapsedMs = performance.now() - hashStarted;

    const includeRaw = Number(await stringArg('include_raw_snapshot')) === 1;

    const observation = {
      kind: 'snapshot',
      scenario,
      timestamp: new Date().toISOString(),
      characterIndex,
      chatIndex,
      hostChatId: chat?.id ?? null,
      metrics: {
        getChatElapsedMs,
        serializeElapsedMs,
        serializedBytes,
        messageCount: Array.isArray(chat.message) ? chat.message.length : 0,
        cryptoSubtleAvailable: subtleAvailable,
        hashMethod,
        manifestHashElapsedMs,
      },
      manifest,
      ...(includeRaw ? { rawSnapshot: chat } : {}),
    };

    console.log(PREFIX, 'snapshot summary', { scenario, ...observation.metrics, hostChatId: observation.hostChatId });
    console.log(PREFIX, 'snapshot manifest', manifest);

    const url = await collectorUrl();
    if (url) {
      await sendCollector(observation);
      console.log(PREFIX, 'snapshot sent to collector', { scenario, url });
    } else {
      console.log(PREFIX, 'collector_url is blank; snapshot was console-only');
    }
  }

  // Measures both hash paths on the same input so Q5 can compare them even when
  // crypto.subtle exists. Uses the current chat if it has messages.
  async function hashBenchmark() {
    const { chat } = await currentChatSnapshot();
    const messages = Array.isArray(chat?.message) ? chat.message : [];
    const payloads = messages.map((m) => new TextEncoder().encode(canonicalJson(messageHashPayload(m))));
    const result = {
      kind: 'hashBenchmark',
      scenario: await scenarioLabel(),
      timestamp: new Date().toISOString(),
      messageCount: payloads.length,
      payloadBytes: payloads.reduce((n, p) => n + p.byteLength, 0),
      subtleMs: null,
      fallbackMs: null,
      resultsAgree: null,
    };
    let subtleHashes = null;
    if (subtleAvailable) {
      const started = performance.now();
      subtleHashes = [];
      for (const p of payloads) {
        const digest = await globalThis.crypto.subtle.digest('SHA-256', p);
        subtleHashes.push(Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join(''));
      }
      result.subtleMs = performance.now() - started;
    }
    const started = performance.now();
    const fallbackHashes = payloads.map(sha256HexFallback);
    result.fallbackMs = performance.now() - started;
    if (subtleHashes) result.resultsAgree = subtleHashes.every((h, i) => h === fallbackHashes[i]);

    console.log(PREFIX, 'hash benchmark', result);
    await sendCollector(result);
  }

  await risuai.registerSetting('NMOS Spike: Dump snapshot', dumpSnapshot, '🧪', 'html', 'nmos-host-spike-dump');
  await risuai.registerSetting('NMOS Spike: Hash benchmark', hashBenchmark, '#', 'html', 'nmos-host-spike-hash');
  await risuai.registerSetting(
    'NMOS Spike: Reset request counters',
    async () => {
      actionCounts.clear();
      formatedCounts.clear();
      beforeRequestSeq = 0;
      lastBeforeRequestAt = null;
      console.log(PREFIX, 'request counters reset');
    },
    '↻',
    'html',
    'nmos-host-spike-reset',
  );

  // Headless-run hook for scripted scenario runs: the host page may post
  // `{ type: 'nmos-spike-action', action: 'dump' | 'hashBenchmark' }` to this plugin's iframe.
  // The sandbox CSP forbids eval, so this is the only way to trigger a dump without the menu.
  globalThis.addEventListener?.('message', (event) => {
    const data = event?.data;
    if (event.source !== globalThis.parent || data?.type !== 'nmos-spike-action') return;
    const action = data.action === 'hashBenchmark' ? hashBenchmark : data.action === 'dump' ? dumpSnapshot : null;
    if (action) void action().catch((error) => console.warn(PREFIX, 'scripted action failed', error));
  });

  console.log(PREFIX, 'loaded', { phase: '0A', modifiesPrompt: false, ...environment() });
  void sendCollector({ kind: 'loaded', scenario: await scenarioLabel(), timestamp: new Date().toISOString() });
})().catch((error) => {
  console.error('[NMOS-SPIKE] initialization failed', error);
});
