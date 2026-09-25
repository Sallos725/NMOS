//@name nmos_memory
//@display-name NMOS Narrative Memory
//@api 3.0
//@version 0.1.0-beta.18
//@link https://github.com/Sallos725/NMOS Documentation
//@update-url https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js
//@arg sidecar_url string NMOS sidecar URL (empty = http://127.0.0.1:8790)
//@arg auth_token string Optional; only if the sidecar sets NMOS_AUTH_TOKEN
//@arg disabled int 1 = pass every request through untouched
//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 600)
//@arg deadline_ms int Hard request-path deadline in ms (0 = 3000)
//@arg inject_position string before_last_user (default) or end
//@arg route string auto (default) / direct / server — how to reach the sidecar
//@arg language string Panel language: ko (default) or en
//@arg hud int 1 = progress display on the chat screen (turn it on from the NMOS panel)
"use strict";
(() => {
  // src/canonical.ts
  function normalizeText(value) {
    return String(value ?? "").normalize("NFC").replace(/\r\n/g, "\n");
  }
  function canonicalize(value) {
    if (value === null || typeof value !== "object") {
      return typeof value === "string" ? normalizeText(value) : value;
    }
    if (Array.isArray(value)) return value.map(canonicalize);
    const out = {};
    for (const key of Object.keys(value).sort()) {
      const v = value[key];
      if (v !== void 0) out[key] = canonicalize(v);
    }
    return out;
  }
  function canonicalJson(value) {
    return JSON.stringify(canonicalize(value));
  }

  // src/hash.ts
  async function sha256Hex(text) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // src/manifest.ts
  var HASH_FORMAT_VERSION = 1;
  var SPECIAL_COMMENT = /\{\{specialcomment::[^]*?::\}\}/g;
  function selectedContent(message) {
    const swipes = message?.swipes;
    const id = message?.swipeId;
    if (Array.isArray(swipes) && Number.isInteger(id) && id >= 0 && id < swipes.length) {
      return swipes[id] ?? "";
    }
    return message?.data ?? "";
  }
  function revisionMetadata(message) {
    const data = typeof message.data === "string" ? message.data : "";
    return {
      chatId: message.chatId ?? null,
      role: message.role ?? null,
      saying: message.saying ?? null,
      name: message.name ?? null,
      otherUser: message.otherUser ?? null,
      isComment: message.isComment ?? null,
      disabled: message.disabled ?? null,
      swipeId: message.swipeId ?? null,
      generationId: message.generationInfo?.generationId ?? null,
      swipeCount: Array.isArray(message.swipes) ? message.swipes.length : 0,
      specialComments: data.match(SPECIAL_COMMENT) ?? []
    };
  }
  function hashPayload(message) {
    const meta = revisionMetadata(message);
    return {
      v: HASH_FORMAT_VERSION,
      chatId: meta.chatId,
      role: meta.role,
      saying: meta.saying,
      name: meta.name,
      otherUser: meta.otherUser,
      isComment: meta.isComment,
      disabled: meta.disabled,
      swipeId: meta.swipeId,
      selectedContent: selectedContent(message),
      generationId: meta.generationId
    };
  }
  var bodyKey = (logicalId, revisionHash) => `${logicalId}
${revisionHash}`;
  var LABEL_MAX = 200;
  function labelOf(value) {
    const text = typeof value === "string" ? value.trim() : "";
    return text ? text.slice(0, LABEL_MAX) : void 0;
  }
  function manifestEntry(m, revisionHash) {
    const meta = revisionMetadata(m);
    return {
      host_logical_id: String(m.chatId ?? ""),
      revision_hash: revisionHash,
      role: m.role,
      name: m.name ?? null,
      disabled: m.disabled ?? null,
      is_comment: m.isComment ?? null,
      swipe_id: m.swipeId ?? null,
      swipe_count: meta.swipeCount,
      generation_id: meta.generationId ?? null,
      special_comments: meta.specialComments
    };
  }
  function snapshotOf(m) {
    const content = selectedContent(m);
    const data = typeof m.data === "string" ? m.data : "";
    const out = [
      m.role,
      m.saying,
      m.name,
      m.otherUser,
      m.isComment,
      m.disabled,
      m.swipeId,
      m.generationInfo?.generationId,
      Array.isArray(m.swipes) ? m.swipes.length : 0,
      content,
      data === content ? null : data
    ];
    return out.every((v) => v === null || v === void 0 || typeof v !== "object" && typeof v !== "function") ? out : void 0;
  }
  function sameSnapshot(a, b) {
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }
  function finish(chat, messages, entries, characterRef, labels, hashed) {
    const index = /* @__PURE__ */ new Map();
    entries.forEach((e, i) => index.set(bodyKey(e.host_logical_id, e.revision_hash), i));
    const bodies = {
      get(key) {
        const i = index.get(key);
        if (i === void 0) return void 0;
        const m = messages[i];
        const e = entries[i];
        return {
          host_logical_id: e.host_logical_id,
          revision_hash: e.revision_hash,
          content: normalizeText(selectedContent(m)),
          metadata: revisionMetadata(m)
        };
      }
    };
    return {
      request: {
        host: "pocketrisu",
        chat_id: String(chat.id ?? ""),
        character_ref: characterRef,
        character_name: labelOf(labels.characterName),
        chat_name: labelOf(chat.name),
        persona_name: labelOf(labels.personaName),
        hash_version: 1,
        messages: entries
      },
      bodies,
      hashed
    };
  }
  var CACHED_CHATS = 2;
  function createManifestBuilder() {
    const chats = /* @__PURE__ */ new Map();
    return async function build(chat, characterRef, labels = {}) {
      const messages = Array.isArray(chat.message) ? chat.message : [];
      const chatKey = String(chat.id ?? "");
      const previous = chats.get(chatKey) ?? /* @__PURE__ */ new Map();
      chats.delete(chatKey);
      const next = /* @__PURE__ */ new Map();
      const entries = new Array(messages.length);
      const snapshots = new Array(messages.length);
      const missing = [];
      const seen = /* @__PURE__ */ new Set();
      messages.forEach((m, i) => {
        const id = m.chatId;
        const snapshot = typeof id === "string" && id !== "" && !seen.has(id) ? snapshotOf(m) : void 0;
        if (typeof id === "string") seen.add(id);
        snapshots[i] = snapshot;
        const hit = snapshot ? previous.get(id) : void 0;
        if (hit && sameSnapshot(hit.snapshot, snapshot)) {
          entries[i] = hit.entry;
          next.set(id, hit);
        } else {
          missing.push(i);
        }
      });
      const hashes = await Promise.all(missing.map((i) => sha256Hex(canonicalJson(hashPayload(messages[i])))));
      missing.forEach((i, j) => {
        const m = messages[i];
        const entry = manifestEntry(m, hashes[j]);
        entries[i] = entry;
        const snapshot = snapshots[i];
        if (snapshot) next.set(m.chatId, { snapshot, entry });
      });
      chats.set(chatKey, next);
      while (chats.size > CACHED_CHATS) chats.delete(chats.keys().next().value);
      return finish(chat, messages, entries, characterRef, labels, missing.length);
    };
  }

  // src/prompt.ts
  var PACKET_TAG = '<NarrativeMemory version="0" source="nmos">';
  function contentText(content) {
    if (typeof content === "string") return content;
    if (content == null) return "";
    return JSON.stringify(content);
  }
  function isActive(message) {
    return message.disabled !== true && !message.isComment;
  }
  function latestUserIndex(messages) {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m.role === "user" && isActive(m)) return i;
    }
    return -1;
  }
  function userTurnIndex(prompt, hostMessages) {
    if (!Array.isArray(prompt)) return -1;
    const hostIndex = latestUserIndex(hostMessages);
    if (hostIndex < 0) return -1;
    const expected = cleanText(selectedContent(hostMessages[hostIndex]));
    if (!expected) return -1;
    const anchor = anchorOf(expected, 64);
    for (let i = prompt.length - 1; i >= 0; i -= 1) {
      if (prompt[i]?.role === "assistant") continue;
      const sent = cleanText(contentText(prompt[i]?.content));
      if (sent === expected || sent.includes(anchor)) return i;
    }
    return -1;
  }
  function hasPacket(prompt) {
    return Array.isArray(prompt) && prompt.some((m) => contentText(m?.content).includes(PACKET_TAG));
  }
  function cleanText(value) {
    return normalizeText(value).replace(/<(style|script)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, " ").replace(/<[^>\n]{1,500}>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
  }
  function anchorOf(text, size = 48) {
    if (text.length <= size) return text;
    const start = Math.floor((text.length - size) / 2);
    return text.slice(start, start + size);
  }
  function inContextIds(prompt, hostMessages, minAnchor = 16, maxMisses = 3) {
    const texts = prompt.map((m) => cleanText(contentText(m?.content)));
    let pointer = texts.length - 1;
    let boundary = hostMessages.length;
    let misses = 0;
    for (let i = hostMessages.length - 1; i >= 0 && pointer >= 0; i -= 1) {
      const m = hostMessages[i];
      if (!isActive(m)) continue;
      const text = cleanText(selectedContent(m));
      if (text.length < minAnchor) continue;
      const anchor = anchorOf(text);
      let found = -1;
      for (let k = pointer; k >= 0; k -= 1) {
        if (texts[k].includes(anchor)) {
          found = k;
          break;
        }
      }
      if (found >= 0) {
        boundary = i;
        pointer = found - 1;
        misses = 0;
      } else if (++misses >= maxMisses) {
        break;
      }
    }
    return hostMessages.slice(boundary).map((m) => String(m.chatId ?? "")).filter(Boolean);
  }
  function injectPacket(prompt, packet, position = "before_last_user", turn = -1) {
    if (!packet || hasPacket(prompt)) return prompt;
    const message = { role: "system", content: packet };
    const out = prompt.slice();
    if (position === "end") {
      out.push(message);
      return out;
    }
    let index = turn >= 0 && turn < out.length && out[turn]?.role !== "assistant" ? turn : out.length;
    for (let i = out.length - 1; index === out.length && i >= 0; i -= 1) {
      if (out[i]?.role === "user") index = i;
    }
    while (index > 0 && out[index]?.role === "user" && out[index - 1]?.role === "user") index -= 1;
    out.splice(index, 0, message);
    return out;
  }
  function queryTexts(hostMessages) {
    const userIndex = latestUserIndex(hostMessages);
    const query = userIndex >= 0 ? normalizeText(selectedContent(hostMessages[userIndex])) : "";
    let previousAi = "";
    for (let i = userIndex - 1; i >= 0; i -= 1) {
      const m = hostMessages[i];
      if (m.role === "char" && isActive(m)) {
        previousAi = normalizeText(selectedContent(m));
        break;
      }
    }
    return { query, previousAi };
  }

  // src/core.ts
  var DeadlineError = class extends Error {
  };
  var SUCCESS_TTL_MS = 10 * 6e4;
  var FAILURE_TTL_MS = 3e4;
  var CACHE_LIMIT = 64;
  var BODY_CHUNK = 250;
  var NAME_TTL_MS = 10 * 6e4;
  var PERSONA_TTL_MS = 3e4;
  function personaOf(chat, host) {
    const list = Array.isArray(host.personas) ? host.personas : [];
    const bound = chat.bindedPersona ? list.find((p) => p?.id === chat.bindedPersona) : void 0;
    const name = (bound ?? list[host.selected])?.name;
    return typeof name === "string" && name.trim() ? name.trim() : null;
  }
  function createAdapter(host, onActivity) {
    const cache = /* @__PURE__ */ new Map();
    const conversations = /* @__PURE__ */ new Map();
    const names = /* @__PURE__ */ new Map();
    let personas = null;
    const buildManifest = createManifestBuilder();
    let last = null;
    function emit(event) {
      try {
        onActivity?.(event);
      } catch {
      }
    }
    function characterName(chatId) {
      const hit = names.get(chatId);
      if (host.characterName && (!hit || host.now() - hit.at > NAME_TTL_MS)) {
        names.set(chatId, { name: hit?.name ?? null, at: host.now() });
        host.characterName(chatId).then((name) => {
          if (name) names.set(chatId, { name, at: host.now() });
        }).catch(() => {
        });
      }
      return hit?.name ?? null;
    }
    function warmPersonas() {
      if (!host.personas) return;
      personas = { value: personas?.value ?? null, at: host.now() };
      host.personas().then((value) => {
        personas = { value, at: host.now() };
      }).catch(() => {
        personas = { value: null, at: host.now() };
      });
    }
    function personaName(chat) {
      if (!personas || host.now() - personas.at > PERSONA_TTL_MS) warmPersonas();
      return personas?.value ? personaOf(chat, personas.value) : null;
    }
    function remember(key, packet, ttl, failed = false) {
      cache.set(key, { packet, expires: host.now() + ttl, failed });
      while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
    }
    async function call(settings, path, body, deadline, method) {
      const remaining = deadline - host.now();
      if (remaining <= 0) throw new DeadlineError(`deadline before ${path}`);
      const url = settings.sidecarUrl.replace(/\/+$/, "") + path;
      const headers = { "Content-Type": "application/json" };
      if (settings.authToken) headers.Authorization = `Bearer ${settings.authToken}`;
      let timer;
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => reject(new DeadlineError(`deadline during ${path}`)), remaining);
      });
      try {
        const verb = method ?? (body === void 0 ? "GET" : "POST");
        const res = await Promise.race([host.request(verb, url, body, headers, remaining, settings.route), timeout]);
        if (res.status < 200 || res.status >= 300) {
          const detail = res.json?.detail;
          throw new Error(`${path} -> HTTP ${res.status}${detail ? `: ${Array.isArray(detail) ? detail.join("; ") : String(detail)}` : ""}`);
        }
        return res.json;
      } finally {
        clearTimeout(timer);
      }
    }
    async function sync(settings, request, bodies, deadline) {
      let result = await call(settings, "/v1/sync/reconcile", request, deadline);
      if (result.status === "needs_bodies") {
        const needed = (result.needed_bodies ?? []).map((n) => bodies.get(bodyKey(n.host_logical_id, n.revision_hash)));
        if (needed.some((b) => !b)) throw new Error("sidecar asked for an unknown body");
        for (let i = 0; i < needed.length; i += BODY_CHUNK) {
          const last2 = i + BODY_CHUNK >= needed.length;
          const out = await call(settings, "/v1/sync/bodies", {
            host: "pocketrisu",
            chat_id: request.chat_id,
            bodies: needed.slice(i, i + BODY_CHUNK),
            then_reconcile: last2 ? request : null
          }, deadline);
          if (!out.ok) throw new Error("sidecar rejected bodies");
          if (last2) {
            if (!out.reconcile) throw new Error("sidecar did not reconcile");
            result = out.reconcile;
          }
        }
      }
      if (result.status === "needs_bodies") throw new Error("sidecar still needs bodies");
      return result;
    }
    async function beforeRequest(prompt, mode) {
      const started = host.now();
      let settings = null;
      let key = null;
      let chatId = null;
      let announced = false;
      try {
        if (mode !== "model" || hasPacket(prompt)) return prompt;
        settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl) return prompt;
        const deadline = started + settings.deadlineMs;
        emit({ type: "request-start" });
        announced = true;
        const chat = await host.currentChat();
        const messages = Array.isArray(chat?.message) ? chat.message : [];
        const turn = userTurnIndex(prompt, messages);
        if (!chat?.id || turn < 0) {
          emit({ type: "request-abandon" });
          return prompt;
        }
        chatId = chat.id;
        const t0 = host.now();
        const { request, bodies } = await buildManifest(
          chat,
          firstSaying(messages),
          { characterName: characterName(chat.id), personaName: personaName(chat) }
        );
        const manifestMs = host.now() - t0;
        key = await sha256Hex(JSON.stringify([
          chat.id,
          mode,
          prompt.length,
          request.messages.map((m) => [m.host_logical_id, m.revision_hash])
        ]));
        const cached = cache.get(key);
        if (cached && cached.expires > host.now()) {
          const outcome2 = cached.packet ? "injected" : "nothing-relevant";
          if (!cached.failed) last = {
            at: Date.now(),
            ms: Math.round(host.now() - started),
            packetChars: cached.packet.length,
            packet: cached.packet,
            outcome: outcome2
          };
          emit({
            type: "request-end",
            outcome: outcome2,
            chars: cached.packet.length,
            conversationId: conversations.get(chat.id) ?? null
          });
          return injectPacket(prompt, cached.packet, settings.injectPosition, turn);
        }
        const t1 = host.now();
        const synced = await sync(settings, request, bodies, deadline);
        const syncMs = host.now() - t1;
        if (synced.conversation_id) {
          conversations.delete(chat.id);
          conversations.set(chat.id, synced.conversation_id);
          while (conversations.size > CACHE_LIMIT) conversations.delete(conversations.keys().next().value);
        }
        const { query, previousAi } = queryTexts(messages);
        const t2 = host.now();
        const retrieved = await call(settings, "/v1/retrieve", {
          host: "pocketrisu",
          chat_id: chat.id,
          active_commit: synced.active_commit,
          manifest_hash: synced.manifest_hash,
          query,
          previous_ai: previousAi,
          in_context_ids: inContextIds(prompt, messages),
          budget_tokens: settings.reservedMemoryTokens,
          client_timings_ms: { manifest: manifestMs, sync: syncMs, before_retrieve: t2 - started }
        }, deadline);
        const packet = retrieved.freshness === "fresh" ? retrieved.packet.text : "";
        remember(key, packet, SUCCESS_TTL_MS);
        host.debug("[NMOS] request done", {
          ms: Math.round(host.now() - started),
          manifestMs: Math.round(manifestMs),
          syncMs: Math.round(syncMs),
          retrieveMs: Math.round(host.now() - t2),
          packetChars: packet.length
        });
        const outcome = packet ? "injected" : "nothing-relevant";
        last = { at: Date.now(), ms: Math.round(host.now() - started), packetChars: packet.length, packet, outcome };
        emit({ type: "request-end", outcome, chars: packet.length, conversationId: synced.conversation_id ?? null });
        return injectPacket(prompt, packet, settings.injectPosition, turn);
      } catch (error) {
        if (key) remember(key, "", FAILURE_TTL_MS, true);
        last = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: 0,
          packet: "",
          outcome: "failed",
          error: error instanceof Error ? error.message : String(error)
        };
        if (announced) emit({
          type: "request-end",
          outcome: "failed",
          chars: 0,
          error: last.error,
          conversationId: chatId && conversations.get(chatId) || null
        });
        host.warn("[NMOS] memory skipped for this request (fail open):", error instanceof Error ? error.message : error);
        return prompt;
      }
    }
    function onOutput(arg2) {
      void (async () => {
        const settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl || !arg2?.chat?.id) return;
        emit({ type: "background", conversationId: conversations.get(arg2.chat.id) ?? null });
        const index = arg2.messageIndex ?? -1;
        const message = index >= 0 ? arg2.chat.message?.[index] : void 0;
        await call(settings, "/v1/output", {
          host: "pocketrisu",
          chat_id: arg2.chat.id,
          host_logical_id: message?.chatId ?? null,
          generation_id: message?.generationInfo?.generationId ?? null,
          revision_hash: message ? await sha256Hex(canonicalJson(hashPayload(message))) : null,
          message_index: index
        }, host.now() + settings.deadlineMs);
      })().catch((error) => host.debug("[NMOS] output notification failed:", error instanceof Error ? error.message : error));
    }
    async function status() {
      const settings = await host.settings();
      const info = {
        enabled: settings.enabled,
        sidecarUrl: settings.sidecarUrl,
        language: settings.language,
        connected: false,
        last
      };
      try {
        const res = await call(
          settings,
          "/v1/health",
          void 0,
          host.now() + 3e3
        );
        Object.assign(info, { connected: true, version: res.version, features: res.features ?? {} });
      } catch (error) {
        info.error = error instanceof Error ? error.message : String(error);
      }
      return info;
    }
    async function api(method, path, body, timeoutMs = 9e4) {
      const settings = await host.settings();
      const out = await call(settings, path, body, host.now() + timeoutMs, method);
      if (method !== "GET") cache.clear();
      return out;
    }
    return { beforeRequest, onOutput, status, api, warmPersonas };
  }
  function firstSaying(messages) {
    for (const m of messages) if (m.role === "char" && m.saying) return m.saying;
    return null;
  }

  // src/i18n.ts
  function langOf(value) {
    return value === "en" ? "en" : "ko";
  }
  var STRINGS = {
    // menus (registered once at load, in the language chosen then)
    "menu.panel": ["NMOS \uAE30\uC5B5", "NMOS memory"],
    // frame
    "title": ["NMOS \uAE30\uC5B5", "NMOS memory"],
    "tab.status": ["\uC0C1\uD0DC", "Status"],
    "tab.inspector": ["\uC778\uC2A4\uD399\uD130", "Inspector"],
    "tab.settings": ["\uC124\uC815", "Settings"],
    "close": ["\uB2EB\uAE30", "Close"],
    "refresh": ["\uC0C8\uB85C \uACE0\uCE68", "Refresh"],
    "language": ["\uC5B8\uC5B4", "Language"],
    // status view
    "status.sidecar": ["\uC0AC\uC774\uB4DC\uCE74", "Sidecar"],
    "status.checking": ["\uC0AC\uC774\uB4DC\uCE74 \uD655\uC778 \uC911\u2026", "Checking the sidecar\u2026"],
    "status.connected": ["\uC5F0\uACB0\uB428", "Connected"],
    "status.unreachable": ["\uC5F0\uACB0\uD560 \uC218 \uC5C6\uC74C", "Cannot reach"],
    "status.fix": [
      "\uD655\uC778: docker compose up -d \xB7 \uC8FC\uC18C \xB7 NMOS_CORS_ORIGINS\uC5D0 \uC774 PocketRisu \uC8FC\uC18C \uD3EC\uD568 \xB7 localhost \uB610\uB294 HTTPS\uB85C \uC811\uC18D",
      "Check: docker compose up -d \xB7 the address \xB7 NMOS_CORS_ORIGINS includes this PocketRisu address \xB7 open via localhost or HTTPS"
    ],
    "status.memory_off": ["\uAE30\uC5B5 \uB123\uAE30\uAC00 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED\uC5D0\uC11C \uCF24 \uC218 \uC788\uC2B5\uB2C8\uB2E4.", "Memory is switched off. Turn it on in Settings."],
    "status.features": ["\uAE30\uB2A5", "Features"],
    "feature.state": ["\uC0C1\uD0DC\uCC3D", "Status window"],
    "feature.extraction": ["\uC0AC\uC2E4 \uCD94\uCD9C", "Fact extraction"],
    "feature.vectors": ["\uC758\uBBF8 \uAC80\uC0C9", "Semantic recall"],
    "on": ["\uCF1C\uC9D0", "on"],
    "off": ["\uAEBC\uC9D0", "off"],
    "status.last": ["\uB9C8\uC9C0\uB9C9 \uC694\uCCAD", "Last request"],
    "status.none": ["\uC544\uC9C1 \uC694\uCCAD\uC774 \uC5C6\uC2B5\uB2C8\uB2E4. \uCC44\uD305\uC5D0\uC11C \uBA54\uC2DC\uC9C0\uB97C \uBCF4\uB0B4 \uBCF4\uC138\uC694.", "No request yet. Send a message in a chat."],
    "status.ago": ["{n}\uCD08 \uC804", "{n}s ago"],
    "status.packet": ["\uB123\uC740 \uAE30\uC5B5 \uBCF4\uAE30", "Show the injected memory"],
    "status.deadline_hint": [
      "\uC81C\uD55C \uC2DC\uAC04\uC744 \uB118\uACA8 \uC774\uBC88 \uC694\uCCAD\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C8\uC2B5\uB2C8\uB2E4. \uAE34 \uCC44\uD305\uC774\uB77C\uBA74 \uC124\uC815 \uD0ED\uC758 \uC81C\uD55C \uC2DC\uAC04(ms)\uC744 \uB298\uB9AC\uC138\uC694.",
      "This request ran out of time and went without memory. For a long chat, raise Deadline (ms) in the Settings tab."
    ],
    "outcome.injected": ["\uAE30\uC5B5 {n}\uC790\uB97C \uB123\uC5C8\uC2B5\uB2C8\uB2E4", "Injected {n} characters of memory"],
    "outcome.nothing": ["\uAD00\uB828\uB41C \uAE30\uC5B5\uC774 \uC5C6\uC5C8\uC2B5\uB2C8\uB2E4", "Nothing relevant to inject"],
    "outcome.failed": ["\uAC74\uB108\uB700 (\uC6D0\uB798 \uC694\uCCAD\uC740 \uADF8\uB300\uB85C \uBCF4\uB0C4)", "Skipped (the request went out unchanged)"],
    // inspector view
    "insp.loading": ["\uC778\uC2A4\uD399\uD130\uB97C \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading the inspector\u2026"],
    "insp.back": ["\u2190 \uB4A4\uB85C", "\u2190 Back"],
    "insp.browser": ["\uBE0C\uB77C\uC6B0\uC800\uC5D0\uC11C \uC9C1\uC811 \uC5F4 \uC218\uB3C4 \uC788\uC2B5\uB2C8\uB2E4: {url}", "Also available in a browser: {url}"],
    "act.history": ["\uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C", "Extract all history"],
    "act.rebuild": ["\uAE30\uC5B5 \uC7AC\uAD6C\uCD95", "Rebuild memory"],
    "act.rebuild_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC7AC\uAD6C\uCD95\uD569\uB2C8\uB2E4", "Click again to rebuild"],
    "act.delete": ["\uB300\uD654 \uC0AD\uC81C", "Delete conversation"],
    "act.delete_confirm": ["\uD55C \uBC88 \uB354 \uB204\uB974\uBA74 \uC601\uAD6C \uC0AD\uC81C\uD569\uB2C8\uB2E4", "Click again to delete for good"],
    "act.sub": [
      "\uACFC\uAC70 \uC804\uCCB4 \uCD94\uCD9C: \uCC98\uC74C \uC5F0\uACB0\uD560 \uB54C \uAC74\uB108\uB6F4 \uC774 \uCC44\uD305\uC758 \uC774\uC804 \uD134\uAE4C\uC9C0 \uC0AC\uC2E4\uC744 \uCD94\uCD9C\uD558\uACE0 \uC784\uBCA0\uB529\uD569\uB2C8\uB2E4. \uAE30\uC5B5 \uC7AC\uAD6C\uCD95: \uC774 \uCC44\uD305\uC758 \uC0AC\uC2E4\uC744 \uBC84\uB9AC\uACE0 \uBAA8\uB4E0 \uD134\uC744 \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4(\uC6D0\uBB38\uC740 \uADF8\uB300\uB85C). \uC720\uB8CC API\uB294 \uD134\uB9C8\uB2E4 \uBE44\uC6A9\uC774 \uB4ED\uB2C8\uB2E4. \uB300\uD654 \uC0AD\uC81C: NMOS\uC5D0 \uC800\uC7A5\uB41C \uC774 \uCC44\uD305\uC758 \uBAA8\uB4E0 \uAE30\uB85D(\uC6D0\uBB38 \uD3EC\uD568)\uC744 \uC9C0\uC6C1\uB2C8\uB2E4. \uB418\uB3CC\uB9B4 \uC218 \uC5C6\uC2B5\uB2C8\uB2E4. PocketRisu\uC758 \uCC44\uD305\uC740 \uADF8\uB300\uB85C\uC774\uACE0, \uADF8 \uCC44\uD305\uC5D0\uC11C \uB2E4\uC2DC \uC0DD\uC131\uD558\uBA74 \uC0C8 \uB300\uD654\uB85C \uCC98\uC74C\uBD80\uD130 \uAE30\uB85D\uB429\uB2C8\uB2E4.",
      "Extract all history: extract facts and embeddings for the older turns of this chat that the first sync skipped. Rebuild memory: discard this chat's facts and extract every turn again (raw messages stay). Paid APIs cost money per turn. Delete conversation: delete everything NMOS stored for this chat, raw messages included. This cannot be undone. The chat in PocketRisu stays; generating in it again records it as a new conversation from scratch."
    ],
    "act.help": ["\uC774 \uBC84\uD2BC\uB4E4\uC740?", "What do these do?"],
    "act.working": ["\uC694\uCCAD \uC911\u2026", "Requesting\u2026"],
    "act.history_done": ["\uD134 {t}\uAC1C \uCD94\uCD9C\uACFC \uBA54\uC2DC\uC9C0 {m}\uAC1C \uC784\uBCA0\uB529\uC744 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0 \uB123\uC5C8\uC2B5\uB2C8\uB2E4.", "Queued {t} turns for extraction and {m} messages for embedding."],
    "act.history_none": ["\uC774\uBBF8 \uC804\uBD80 \uCC98\uB9AC\uB418\uC5C8\uAC70\uB098 \uCC98\uB9AC \uC911\uC785\uB2C8\uB2E4.", "Everything is already processed or queued."],
    "act.rebuild_done": [
      "\uCD94\uCD9C {d}\uAC74\uC744 \uBC84\uB9AC\uACE0 \uD134 {t}\uAC1C\uB97C \uB2E4\uC2DC \uCD94\uCD9C\uD569\uB2C8\uB2E4. \uB05D\uB0A0 \uB54C\uAE4C\uC9C0 \uC774 \uCC44\uD305\uC758 \uC0AC\uC2E4\uC774 \uBE44\uC5B4 \uC788\uC744 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "Discarded {d} extractions; {t} turns are extracted again. Facts of this chat may be missing until then."
    ],
    "act.delete_done": ["\uB300\uD654\uB97C \uC0AD\uC81C\uD588\uC2B5\uB2C8\uB2E4 (\uBA54\uC2DC\uC9C0 {m}\uAC1C\uC758 \uAE30\uB85D).", "Conversation deleted (records of {m} messages)."],
    "link.title": ["\uAC19\uC740 \uB300\uC0C1\uC73C\uB85C \uD569\uCE58\uAE30", "Same as another entity"],
    "link.sub": [
      "\uC774\uC57C\uAE30\uAC00 \uC2A4\uC2A4\uB85C \uC787\uC9C0 \uBABB\uD55C \uC774\uB984\uC744 \uC9C1\uC811 \uD569\uCE69\uB2C8\uB2E4(\uC608: \uC774\uB984 \uC5C6\uC774 \uBA3C\uC800 \uB098\uC628 \uC778\uBB3C\uACFC \uB098\uC911\uC5D0 \uC774\uB984\uC774 \uBC1D\uD600\uC9C4 \uC778\uBB3C). \uAE30\uC5B5 \uC7AC\uAD6C\uCD95\uC744 \uD574\uB3C4 \uC720\uC9C0\uB418\uACE0, \uC5B8\uC81C\uB4E0 \uD574\uC81C\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "Join names the story did not link on its own (e.g. someone shown without a name and named later). Kept across rebuilds; you can undo it at any time."
    ],
    "link.pick": ["\uAC19\uC740 \uB300\uC0C1", "Same as"],
    "link.join": ["\uD569\uCE58\uAE30", "Join"],
    "link.remove": ["\uD574\uC81C", "Undo"],
    "link.none": ["\uD569\uCE60 \uC218 \uC788\uB294 \uAC19\uC740 \uC885\uB958\uC758 \uB300\uC0C1\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No other entity of this type."],
    "link.done": ['"{a}"\uC640(\uACFC) "{b}"\uB97C \uD569\uCCE4\uC2B5\uB2C8\uB2E4.', 'Joined "{a}" and "{b}".'],
    "link.removed": ["\uC5F0\uACB0\uC744 \uD574\uC81C\uD588\uC2B5\uB2C8\uB2E4.", "Link undone."],
    "act.off": ["\uC0AC\uC2E4 \uCD94\uCD9C(\uB610\uB294 \uC784\uBCA0\uB529)\uC774 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uC124\uC815 \uD0ED\uC5D0\uC11C \uCF1C\uC138\uC694.", "Fact extraction (or embeddings) is off. Turn it on in Settings."],
    // settings: connection
    "conn.title": ["\uC5F0\uACB0", "Connection"],
    "conn.sub": [
      "\uC774 \uBE0C\uB77C\uC6B0\uC800\uC758 PocketRisu \uD50C\uB7EC\uADF8\uC778 \uC124\uC815\uC785\uB2C8\uB2E4. \uC0AC\uC774\uB4DC\uCE74\uAC00 \uB2E4\uB978 \uAE30\uAE30\uC5D0 \uC788\uC73C\uBA74 route=server\uAC00 \uC790\uB3D9\uC73C\uB85C \uC4F0\uC785\uB2C8\uB2E4.",
      "This browser's PocketRisu plugin settings. If the sidecar runs on another device, route=server is used automatically."
    ],
    "conn.url": ["\uC0AC\uC774\uB4DC\uCE74 \uC8FC\uC18C", "Sidecar URL"],
    "conn.route": ["\uACBD\uB85C", "Route"],
    "conn.budget": ["\uAE30\uC5B5 \uC608\uC0B0(\uD1A0\uD070)", "Memory budget (tokens)"],
    "conn.deadline": ["\uC81C\uD55C \uC2DC\uAC04(ms)", "Deadline (ms)"],
    "conn.enabled": ["\uAE30\uC5B5 \uB123\uAE30 \uCF1C\uAE30", "Memory on"],
    "conn.hint": ["PocketRisu\uC758 \uCD5C\uB300 \uCEE8\uD14D\uC2A4\uD2B8\uB97C \uAE30\uC5B5 \uC608\uC0B0\uB9CC\uD07C \uC904\uC5EC \uB450\uC138\uC694.", "Lower PocketRisu's max context by the memory budget."],
    "conn.deadline_hint": [
      "\uC81C\uD55C \uC2DC\uAC04 \uC548\uC5D0 \uAE30\uC5B5\uC744 \uC900\uBE44\uD558\uC9C0 \uBABB\uD558\uBA74 \uADF8 \uC694\uCCAD\uC740 \uAE30\uC5B5 \uC5C6\uC774 \uBCF4\uB0C5\uB2C8\uB2E4. \uAE30\uBCF8 3000ms. \uC544\uC8FC \uAE34 \uCC44\uD305(1\uB9CC \uAC1C \uC774\uC0C1)\uC5D0\uC11C \uAE30\uC5B5\uC774 \uC790\uC8FC \uBE60\uC9C0\uBA74 \uB298\uB9AC\uC138\uC694. \uB298\uB9B0 \uB9CC\uD07C \uB2F5\uC7A5 \uC2DC\uC791\uC774 \uB2A6\uC5B4\uC9C8 \uC218 \uC788\uC2B5\uB2C8\uB2E4.",
      "If memory is not ready within the deadline, that request goes without memory. Default 3000 ms. Raise it if very long chats (10,000+ messages) often miss memory; replies may start that much later."
    ],
    // settings: models
    "llm.title": ["\uC0AC\uC2E4 \uCD94\uCD9C LLM", "Fact extraction LLM"],
    "llm.sub": [
      "\uD655\uC815\uB41C \uD134(\uC785\uB825\uACFC \uC751\uB2F5)\uB9C8\uB2E4 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0\uC11C \uD55C \uBC88 \uD638\uCD9C\uD574 \uC778\uBB3C\xB7\uC7A5\uC18C\xB7\uC57D\uC18D\xB7\uAD00\uACC4\uB97C \uAE30\uB85D\uD569\uB2C8\uB2E4. \uC720\uB8CC API\uB294 \uBE44\uC6A9\uC774 \uB4ED\uB2C8\uB2E4.",
      "Called once per settled turn (input and reply) in the background to record people, places, promises and relationships. Paid APIs cost money."
    ],
    "emb.title": ["\uC758\uBBF8 \uAC80\uC0C9 \uC784\uBCA0\uB529", "Semantic recall embeddings"],
    "emb.sub": [
      "\uB2E4\uB978 \uB9D0\uB85C \uBB3C\uC5B4\uB3C4 \uC608\uC804 \uC7A5\uBA74\uC744 \uCC3E\uC2B5\uB2C8\uB2E4. Ollama\uC758 qwen3-embedding:0.6b\uB97C \uCD94\uCC9C\uD569\uB2C8\uB2E4.",
      "Finds earlier scenes even when asked in other words. Ollama qwen3-embedding:0.6b is recommended."
    ],
    "preset.off": ["\uC0AC\uC6A9 \uC548 \uD568", "Off"],
    "preset.ollama": ["Ollama (\uC774 PC)", "Ollama (this PC)"],
    "preset.custom": ["\uC9C1\uC811 \uC785\uB825 (OpenAI \uD638\uD658)", "Custom (OpenAI-compatible)"],
    "model.provider": ["\uC81C\uACF5\uC790", "Provider"],
    "model.endpoint": ["\uC8FC\uC18C (OpenAI \uD638\uD658 /v1)", "Endpoint (OpenAI-compatible /v1)"],
    "model.model": ["\uBAA8\uB378", "Model"],
    "model.llm_placeholder": ["\uBAA8\uB378 \uC774\uB984", "model name"],
    "model.emb_placeholder": ["\uC784\uBCA0\uB529 \uBAA8\uB378", "embedding model"],
    "model.key": ["API \uD0A4", "API key"],
    "model.key_placeholder": ["\uD544\uC694\uD560 \uB54C\uB9CC \uC785\uB825", "only if needed"],
    "model.key_saved": ["\uC800\uC7A5\uB428 \u2014 \uBC14\uAFC0 \uB54C\uB9CC \uC785\uB825", "saved \u2014 type only to change"],
    "model.vertex_hint": [
      "\uC11C\uBE44\uC2A4 \uACC4\uC815 JSON \uD0A4 \uD30C\uC77C \uB0B4\uC6A9\uC744 API \uD0A4 \uCE78\uC5D0 \uD1B5\uC9F8\uB85C \uBD99\uC5EC \uB123\uC73C\uC138\uC694. \uC8FC\uC18C\uC758 \uD504\uB85C\uC81D\uD2B8\uB294 \uD0A4\uC5D0\uC11C \uCC44\uC6CC\uC9C0\uACE0, \uD1A0\uD070\uC740 \uC0AC\uC774\uB4DC\uCE74\uAC00 1\uC2DC\uAC04\uB9C8\uB2E4 \uAC31\uC2E0\uD569\uB2C8\uB2E4. Vertex AI User \uC5ED\uD560\uB9CC \uC900 \uC804\uC6A9 \uC11C\uBE44\uC2A4 \uACC4\uC815\uC744 \uC4F0\uC138\uC694.",
      "Paste the whole service-account JSON key file into the API key field. The project in the endpoint is filled from the key, and the sidecar renews the token every hour. Use a dedicated service account with only the Vertex AI User role."
    ],
    "model.load": ["\uBAA8\uB378 \uBAA9\uB85D", "Load models"],
    "model.test": ["\uC5F0\uACB0 \uD14C\uC2A4\uD2B8", "Test"],
    "model.loading": ["\uBD88\uB7EC\uC624\uB294 \uC911\u2026", "Loading\u2026"],
    "model.list_failed": ["\uBAA9\uB85D\uC744 \uAC00\uC838\uC624\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "Could not list models: {e}"],
    "model.pick": ["\u2014 \uBAA8\uB378 {n}\uAC1C \uC911 \uC120\uD0DD \u2014", "\u2014 pick one of {n} models \u2014"],
    "model.found": ["\uBAA8\uB378 {n}\uAC1C\uB97C \uCC3E\uC558\uC2B5\uB2C8\uB2E4.", "Found {n} models."],
    "model.testing": ["\uC2E4\uC81C \uD638\uCD9C\uB85C \uD655\uC778 \uC911\u2026", "Calling the model\u2026"],
    "model.test_ok": ["\uC131\uACF5 {ms}ms", "OK {ms}ms"],
    "model.dims": [" \xB7 {n}\uCC28\uC6D0", " \xB7 {n} dimensions"],
    "model.test_failed": ["\uC2E4\uD328: {e}", "Failed: {e}"],
    // settings: tuning
    "tune.title": ["\uAC80\uC0C9 \uC870\uC815", "Recall tuning"],
    "tune.sub": [
      "\uC5C9\uB6B1\uD55C \uBC1C\uCDCC\uAC00 \uB4E4\uC5B4\uAC00\uBA74 \uAE30\uC900\uAC12\uC744 \uC62C\uB9AC\uACE0, \uAE30\uC5B5\uC774 \uB108\uBB34 \uC548 \uB4E4\uC5B4\uAC00\uBA74 \uB0B4\uB9AC\uC138\uC694.",
      "Raise the thresholds if unrelated excerpts get in; lower them if too little memory is injected."
    ],
    "tune.threshold": ["\uAE00\uC790 \uC77C\uCE58 \uAE30\uC900", "Lexical threshold"],
    "tune.min_sim": ["\uC758\uBBF8 \uC720\uC0AC\uB3C4 \uAE30\uC900", "Vector min similarity"],
    "tune.top_k": ["\uBC1C\uCDCC \uC218", "Excerpts"],
    "tune.facts": ["\uC0AC\uC2E4 \uC218", "Facts"],
    "tune.backfill": ["\uCC98\uC74C \uC5F0\uACB0 \uC2DC \uCD94\uCD9C\uD560 \uD134 \uC218", "Turns extracted on first sync"],
    // settings: parser rules
    "rules.title": ["\uC0C1\uD0DC\uCC3D \uADDC\uCE59", "Status-window rules"],
    "rules.sub": [
      'block: \uC2DC\uC791~\uB05D \uC0AC\uC774\uC758 "\uD0A4: \uAC12" \uC904\uC744 \uC77D\uC2B5\uB2C8\uB2E4. entity_line\uC73C\uB85C [\uC778\uBB3C] \uC904\uB9C8\uB2E4 \uC778\uBB3C\uBCC4\uB85C \uB098\uB215\uB2C8\uB2E4 (\uC2DC\uBBAC\uBD07). regex: key/value \uC774\uB984 \uADF8\uB8F9.',
      'block: reads "key: value" lines between start and end; entity_line splits them per [character] line (sim bots). regex: named groups key/value.'
    ],
    "rules.example": ["\uC608\uC2DC \uB123\uAE30", "Insert example"],
    "rules.none": ['\uADDC\uCE59 \uC5C6\uC74C \u2014 "\uC608\uC2DC \uB123\uAE30"\uB85C \uC2DC\uC791\uD558\uC138\uC694', 'No rules \u2014 start with "Insert example"'],
    "rules.from_file": ["\uD30C\uC77C\uC5D0\uC11C \uADDC\uCE59 {n}\uAC1C\uB97C \uC77D\uB294 \uC911 (\uC5EC\uAE30\uC5D0 \uC800\uC7A5\uD558\uBA74 \uB300\uCCB4\uB429\uB2C8\uB2E4)", "Reading {n} rules from a file (saving here replaces them)"],
    // save bar
    "save": ["\uC800\uC7A5", "Save"],
    "revert": ["\uB418\uB3CC\uB9AC\uAE30", "Revert"],
    "saving": ["\uC800\uC7A5 \uC911\u2026", "Saving\u2026"],
    "saved": ["\uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4.", "Saved."],
    "saved_queued": ["\uC800\uC7A5\uD588\uC2B5\uB2C8\uB2E4. \uAE30\uC874 \uCC44\uD305 {n}\uAC74\uC744 \uBC31\uADF8\uB77C\uC6B4\uB4DC\uC5D0\uC11C \uCC98\uB9AC\uD569\uB2C8\uB2E4.", "Saved. {n} existing items are processed in the background."],
    "saved_rules": ["\uADDC\uCE59 {n}\uAC1C\uB97C \uC801\uC6A9\uD558\uACE0 \uAE30\uC874 \uBA54\uC2DC\uC9C0\uB97C \uB2E4\uC2DC \uC77D\uC5C8\uC2B5\uB2C8\uB2E4.", "{n} rules applied; existing messages were re-read."],
    "no_changes": ["\uBC14\uB010 \uB0B4\uC6A9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4.", "No changes."],
    "unsaved": ["\uC800\uC7A5\uD558\uC9C0 \uC54A\uC740 \uBCC0\uACBD: {s}", "Unsaved changes: {s}"],
    "close_unsaved": ["\uC800\uC7A5\uD558\uC9C0 \uC54A\uC740 \uBCC0\uACBD\uC774 \uC788\uC2B5\uB2C8\uB2E4.", "You have unsaved changes."],
    "save_and_close": ["\uC800\uC7A5\uD558\uACE0 \uB2EB\uAE30", "Save and close"],
    "discard_and_close": ["\uBC84\uB9AC\uACE0 \uB2EB\uAE30", "Discard and close"],
    "cancel": ["\uCDE8\uC18C", "Cancel"],
    "lang_unsaved": ["\uC5B8\uC5B4\uB97C \uBC14\uAFB8\uAE30 \uC804\uC5D0 \uBCC0\uACBD\uC744 \uC800\uC7A5\uD558\uAC70\uB098 \uB418\uB3CC\uB9AC\uC138\uC694.", "Save or revert your changes before switching the language."],
    "conn_saved_server_failed": ["\uC5F0\uACB0 \uC124\uC815\uC740 \uC800\uC7A5\uD588\uC9C0\uB9CC \uC11C\uBC84 \uC124\uC815\uC740 \uC800\uC7A5\uD558\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4: {e}", "Connection saved, but the server settings were not: {e}"],
    // progress display (HUD) on the chat screen
    "hud.recalling": ["\u{1F9E0} \uAE30\uC5B5 \uBD88\uB7EC\uC624\uB294 \uC911\u2026", "\u{1F9E0} Recalling memory\u2026"],
    "hud.injected": ["\u2713 \uAE30\uC5B5 \uC8FC\uC785 ({n}\uC790)", "\u2713 Memory injected ({n} chars)"],
    "hud.nothing": ["\u2013 \uAD00\uB828 \uAE30\uC5B5 \uC5C6\uC74C", "\u2013 Nothing relevant"],
    "hud.skipped": ["\u26A0 \uAC74\uB108\uB700: {r}", "\u26A0 Skipped: {r}"],
    "hud.reason.deadline": ["\uC81C\uD55C \uC2DC\uAC04 \uCD08\uACFC", "deadline"],
    "hud.reason.error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958", "sidecar error"],
    "hud.extract": ["\uCD94\uCD9C {d}/{n}", "Facts {d}/{n}"],
    "hud.embed": ["\uC784\uBCA0\uB529 {d}/{n}", "Embeddings {d}/{n}"],
    "hud.failed": ["\u26A0 \uC2E4\uD328 {n}", "\u26A0 {n} failed"],
    "hud.done": ["\u2713 \uCC98\uB9AC \uC644\uB8CC", "\u2713 Processing done"],
    // progress display: panel
    "hud.title": ["\uC9C4\uD589 \uD45C\uC2DC", "Progress display"],
    "hud.sub": [
      '\uCC44\uD305 \uD654\uBA74 \uC624\uB978\uCABD \uC704\uC5D0 \uAE30\uC5B5\uC774 \uB4E4\uC5B4\uAC14\uB294\uC9C0\uC640 \uBC31\uADF8\uB77C\uC6B4\uB4DC \uCC98\uB9AC \uC9C4\uD589\uC744 \uC791\uAC8C \uB744\uC6C1\uB2C8\uB2E4. \uCF1C\uBA74 PocketRisu\uAC00 "\uBA54\uC778 Document \uC811\uADFC" \uAD8C\uD55C\uC744 \uBB3B\uC2B5\uB2C8\uB2E4. NMOS\uB294 \uC774 \uAD8C\uD55C\uC73C\uB85C \uD45C\uC2DC \uD558\uB098\uB9CC \uADF8\uB9AC\uACE0 \uD654\uBA74 \uB0B4\uC6A9\uC740 \uC77D\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4. \uB204\uB974\uBA74 \uC774 \uD328\uB110\uC774 \uC5F4\uB9BD\uB2C8\uB2E4.',
      'Shows a small pill at the top right of the chat screen: whether memory went in, and background processing progress. Turning it on makes PocketRisu ask for "main Document" access. NMOS only draws the pill with it and reads nothing on the page. Tap the pill to open this panel.'
    ],
    "hud.toggle": ["\uCC44\uD305 \uD654\uBA74\uC5D0 \uC9C4\uD589 \uD45C\uC2DC \uB744\uC6B0\uAE30", "Show the progress display on the chat screen"],
    "hud.enable": ["\uC9C4\uD589 \uD45C\uC2DC \uCF1C\uAE30", "Turn on progress display"],
    "hud.hint": [
      "\uC9C4\uD589 \uD45C\uC2DC\uAC00 \uAEBC\uC838 \uC788\uC2B5\uB2C8\uB2E4. \uCF1C\uBA74 \uAE30\uC5B5\uC774 \uB4E4\uC5B4\uAC14\uB294\uC9C0 \uCC44\uD305 \uD654\uBA74\uC5D0\uC11C \uBC14\uB85C \uBCF4\uC785\uB2C8\uB2E4.",
      "The progress display is off. Turn it on to see on the chat screen whether memory went in."
    ],
    "hud.on": ["\uCF30\uC2B5\uB2C8\uB2E4. \uB2E4\uC74C \uBA54\uC2DC\uC9C0\uBD80\uD130 \uD45C\uC2DC\uB429\uB2C8\uB2E4.", "On. It shows from the next message."],
    "hud.off": ["\uAED0\uC2B5\uB2C8\uB2E4.", "Off."],
    "hud.denied": [
      '\uAD8C\uD55C\uC774 \uAC70\uBD80\uB418\uC5B4 \uCF1C\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4. PocketRisu\uB294 \uAC70\uBD80\uB97C \uAE30\uC5B5\uD569\uB2C8\uB2E4. \uC124\uC815 \u2192 \uD50C\uB7EC\uADF8\uC778 \u2192 NMOS \uC904\uC758 \uBA54\uB274 \u2192 "\uAD8C\uD55C \uC751\uB2F5 \uCD08\uAE30\uD654" \uD6C4 \uB2E4\uC2DC \uCF1C\uC138\uC694.',
      "Permission was denied, so it stays off. PocketRisu remembers a denial: Settings \u2192 Plugin \u2192 the NMOS row menu \u2192 reset permission responses, then turn it on again."
    ],
    "hud.unsupported": [
      "\uC774 PocketRisu \uBC84\uC804\uC740 \uD50C\uB7EC\uADF8\uC778\uC774 \uCC44\uD305 \uD654\uBA74\uC5D0 \uD45C\uC2DC\uB97C \uADF8\uB9AC\uB294 \uAE30\uB2A5\uC744 \uC9C0\uC6D0\uD558\uC9C0 \uC54A\uC2B5\uB2C8\uB2E4.",
      "This PocketRisu version does not let plugins draw on the chat screen."
    ],
    "hud.broken": ["\uC9C4\uD589 \uD45C\uC2DC\uB97C \uADF8\uB9AC\uC9C0 \uBABB\uD574 \uC774\uBC88 \uC138\uC158\uC5D0\uC11C\uB294 \uBA48\uCDC4\uC2B5\uB2C8\uB2E4: {e}", "The progress display stopped for this session: {e}"],
    "invalid": ["\uC785\uB825 \uC624\uB958: ", "Invalid: "],
    "sidecar_error": ["\uC0AC\uC774\uB4DC\uCE74 \uC624\uB958: ", "Sidecar error: "]
  };
  function t(lang, key, vars = {}) {
    const text = STRINGS[key][lang === "en" ? 1 : 0];
    return text.replace(/\{(\w+)\}/g, (m, name) => name in vars ? String(vars[name]) : m);
  }
  var STRING_KEYS = Object.keys(STRINGS);

  // src/form.ts
  var DEFAULT_DEADLINE_MS = 3e3;
  var MAX_DEADLINE_MS = 3e4;
  var SECTIONS = ["conn", "llm", "emb", "tune", "rules"];
  var VERTEX_URL = "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi";
  function serviceAccountProject(key) {
    const text = key.trim();
    if (!text.startsWith("{")) return null;
    try {
      const info = JSON.parse(text);
      return info.type === "service_account" && typeof info.project_id === "string" && info.project_id ? info.project_id : null;
    } catch {
      return null;
    }
  }
  function fillProject(url, key) {
    const project = serviceAccountProject(key);
    return project && url.includes("{project}") ? url.replace("{project}", encodeURIComponent(project)) : url;
  }
  function presetMatches(presetUrl, url) {
    if (!presetUrl.includes("{project}")) return presetUrl === url;
    const [head, tail] = presetUrl.split("{project}");
    return url.startsWith(head) && url.endsWith(tail) && url.length > head.length + tail.length && !url.slice(head.length, url.length - tail.length).includes("/");
  }
  function dirtySections(baseline, current2) {
    return SECTIONS.filter((s) => JSON.stringify(baseline[s]) !== JSON.stringify(current2[s]));
  }
  function num(value) {
    const n = Number(value.trim());
    return value.trim() !== "" && Number.isFinite(n) ? n : value;
  }
  function configBody(dirty, v) {
    const body = {};
    for (const [section, prefix] of [["llm", "llm"], ["emb", "embed"]]) {
      if (!dirty.includes(section)) continue;
      body[`${prefix}_url`] = v[section].url.trim();
      body[`${prefix}_model`] = v[section].model.trim();
      if (v[section].key.trim()) body[`${prefix}_api_key`] = v[section].key.trim();
    }
    if (dirty.includes("tune")) {
      Object.assign(body, {
        recall_threshold: num(v.tune.threshold),
        vector_min_sim: num(v.tune.minSim),
        recall_top_k: num(v.tune.topK),
        facts_limit: num(v.tune.facts),
        extract_backfill: num(v.tune.backfill)
      });
    }
    if (dirty.includes("rules")) body.parsers = v.rules.trim() ? v.rules : null;
    return body;
  }
  function connArgs(v) {
    return {
      sidecar_url: v.url.trim(),
      route: v.route,
      disabled: v.enabled ? 0 : 1,
      reserved_memory_tokens: Number(v.reserved) || 600,
      deadline_ms: Math.min(MAX_DEADLINE_MS, Math.max(200, Math.floor(Number(v.deadline)) || DEFAULT_DEADLINE_MS))
    };
  }

  // src/hud.ts
  var OUTCOME_MS = 4e3;
  var DONE_MS = 3e3;
  var EMPTY = { request: null, progress: null };
  function pending(c) {
    return (c.extract?.pending ?? 0) + (c.embed?.pending ?? 0);
  }
  function reduce(state, event, now) {
    switch (event.type) {
      case "request-start":
        return { ...state, request: { phase: "running" } };
      case "request-abandon":
        return state.request?.phase === "running" ? { ...state, request: null } : state;
      case "request-end":
        return { ...state, request: {
          phase: "done",
          outcome: event.outcome,
          chars: event.chars,
          error: event.error,
          until: now + OUTCOME_MS
        } };
      case "coverage":
        if (pending(event.coverage) > 0) return { ...state, progress: { coverage: event.coverage } };
        return state.progress && "coverage" in state.progress ? { ...state, progress: { finishedUntil: now + DONE_MS } } : state;
      case "reset":
        return EMPTY;
      case "background":
        return state;
    }
  }
  function view(state, now, lang) {
    const r = state.request;
    if (r?.phase === "running") return { kind: "busy", text: t(lang, "hud.recalling"), fraction: null };
    if (r?.phase === "done" && now < r.until) {
      if (r.outcome === "injected") return { kind: "ok", text: t(lang, "hud.injected", { n: r.chars }), fraction: null };
      if (r.outcome === "nothing-relevant") return { kind: "muted", text: t(lang, "hud.nothing"), fraction: null };
      const reason = t(lang, r.error?.startsWith("deadline") ? "hud.reason.deadline" : "hud.reason.error");
      return { kind: "warn", text: t(lang, "hud.skipped", { r: reason }), fraction: null };
    }
    const p = state.progress;
    if (p && "coverage" in p) return progressView(p.coverage, lang);
    if (p && now < p.finishedUntil) return { kind: "ok", text: t(lang, "hud.done"), fraction: 1 };
    return null;
  }
  function progressView(c, lang) {
    const parts = [];
    let done = 0;
    let total = 0;
    let failed = 0;
    for (const [key, counts] of [["hud.extract", c.extract], ["hud.embed", c.embed]]) {
      if (!counts || counts.total === 0) continue;
      parts.push(t(lang, key, { d: counts.done, n: counts.total }));
      done += counts.done;
      total += counts.total;
      failed += counts.failed;
    }
    if (failed) parts.push(t(lang, "hud.failed", { n: failed }));
    return { kind: "busy", text: parts.join(" \xB7 "), fraction: total ? done / total : null };
  }
  function nextChange(state, now) {
    const times = [
      state.request?.phase === "done" ? state.request.until : null,
      state.progress && "finishedUntil" in state.progress ? state.progress.finishedUntil : null
    ].filter((x) => x !== null && x > now);
    return times.length ? Math.min(...times) : null;
  }
  function parseCoverage(json) {
    const body = json ?? {};
    const counts = (section, doneKey) => section?.generation && typeof section.eligible === "number" ? {
      done: Number(section[doneKey]) || 0,
      total: section.eligible,
      pending: Number(section.pending) || 0,
      failed: Number(section.failed) || 0
    } : null;
    return { extract: counts(body.extraction, "compiled"), embed: counts(body.embeddings, "embedded") };
  }

  // src/hud-host.ts
  var POLL_MS = 3e3;
  var MAX_POLL_ERRORS = 5;
  var MIN_POLL_GAP_MS = 1e3;
  var CLASS = "nmos-hud";
  var ROOT_STYLE = 'position:fixed;top:calc(8px + env(safe-area-inset-top));right:calc(8px + env(safe-area-inset-right));z-index:900;min-width:140px;max-width:min(320px,calc(100vw - 72px));background:#1d1e24;border:1px solid #30323b;border-radius:12px;padding:6px 12px;font:13px/1.4 system-ui,-apple-system,"Noto Sans KR",sans-serif;box-shadow:0 2px 10px rgba(0,0,0,.35);cursor:pointer;user-select:none';
  var TEXT_STYLE = "display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#e8e8ec";
  var TRACK_STYLE = "display:none;height:3px;margin-top:4px;background:#30323b;border-radius:2px;overflow:hidden";
  var FILL_STYLE = "height:3px;width:0;background:#4c6ef5;border-radius:2px;transition:width .3s";
  var COLORS = { busy: "#e8e8ec", ok: "#8ce99a", muted: "#9a9ca8", warn: "#ffd43b" };
  function createHud(deps) {
    let state = EMPTY;
    let problem = null;
    let drawn = null;
    let conversation = null;
    let where = null;
    let pollTimer = null;
    let expiryTimer = null;
    let pollErrors = 0;
    let lastPoll = -Infinity;
    let queue = Promise.resolve();
    function run(task) {
      queue = queue.then(task).catch(fail);
    }
    async function fail(error) {
      problem = error instanceof Error ? error.message : String(error);
      deps.debug("[NMOS] progress display stopped for this session:", problem);
      stopPolling();
      await erase().catch(() => {
      });
    }
    async function active() {
      if (!problem && await deps.enabled()) return true;
      stopPolling();
      await erase();
      return false;
    }
    async function erase() {
      if (expiryTimer !== null) deps.clearTimer(expiryTimer);
      expiryTimer = null;
      const d = drawn;
      drawn = null;
      if (!d) return;
      await d.root.removeEventListener("click", d.listener);
      await d.root.remove();
    }
    async function draw() {
      const doc = await deps.rootDocument();
      if (!doc) throw new Error("no access to the PocketRisu page (mainDom permission)");
      await (await doc.querySelector(`.${CLASS}`))?.remove();
      const body = await doc.querySelector("body");
      if (!body) throw new Error("the PocketRisu page has no body");
      const root = await doc.createElement("div");
      await root.addClass(CLASS);
      await root.setStyleAttribute(ROOT_STYLE);
      const text = await doc.createElement("span");
      await text.setStyleAttribute(TEXT_STYLE);
      const track = await doc.createElement("div");
      await track.setStyleAttribute(TRACK_STYLE);
      const fill = await doc.createElement("div");
      await fill.setStyleAttribute(FILL_STYLE);
      await track.appendChild(fill);
      await root.appendChild(text);
      await root.appendChild(track);
      await body.appendChild(root);
      const listener = await root.addEventListener("click", (event) => {
        void hit(event);
      });
      return { root, text, track, fill, listener, last: "" };
    }
    async function hit(event) {
      try {
        const d = drawn;
        if (!d) return;
        const r = await d.root.getBoundingClientRect();
        if (event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom) {
          deps.openPanel();
        }
      } catch (error) {
        deps.debug("[NMOS] progress display click failed:", error instanceof Error ? error.message : error);
      }
    }
    async function render2() {
      if (expiryTimer !== null) deps.clearTimer(expiryTimer);
      expiryTimer = null;
      const now = deps.now();
      const v = view(state, now, await deps.lang());
      if (!v) return erase();
      drawn ??= await draw();
      const d = drawn;
      const key = JSON.stringify(v);
      if (d.last !== key) {
        d.last = key;
        await d.text.setTextContent(v.text);
        await d.text.setStyle("color", COLORS[v.kind]);
        await d.track.setStyle("display", v.fraction === null ? "none" : "block");
        if (v.fraction !== null) await d.fill.setStyle("width", `${Math.round(v.fraction * 100)}%`);
      }
      const next = nextChange(state, now);
      if (next !== null) expiryTimer = deps.setTimer(() => {
        expiryTimer = null;
        run(render2);
      }, next - now);
    }
    async function follow(conversationId) {
      if (!conversationId) return;
      where = await deps.position();
      if (conversationId === conversation) return;
      conversation = conversationId;
      state = { ...state, progress: null };
      stopPolling();
    }
    function startPolling() {
      if (pollTimer !== null || !conversation) return;
      pollErrors = 0;
      pollTimer = deps.setTimer(() => run(poll), Math.max(0, lastPoll + MIN_POLL_GAP_MS - deps.now()));
    }
    function stopPolling() {
      if (pollTimer !== null) deps.clearTimer(pollTimer);
      pollTimer = null;
    }
    async function poll() {
      pollTimer = null;
      if (!await active() || !conversation) return;
      if (where !== null && await deps.position() !== where) {
        conversation = null;
        state = { ...state, progress: null };
        return render2();
      }
      let again = false;
      lastPoll = deps.now();
      try {
        const coverage = parseCoverage(await deps.coverage(conversation));
        pollErrors = 0;
        state = reduce(state, { type: "coverage", coverage }, deps.now());
        again = pending(coverage) > 0;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        deps.debug("[NMOS] coverage poll failed:", message);
        again = !/HTTP 404/.test(message) && ++pollErrors < MAX_POLL_ERRORS;
      }
      await render2();
      if (again) pollTimer = deps.setTimer(() => run(poll), POLL_MS);
    }
    return {
      /** Request-path activity from core.ts. */
      event(event) {
        run(async () => {
          if (!await active()) return;
          if (event.type === "request-end" || event.type === "background") await follow(event.conversationId);
          state = reduce(state, event, deps.now());
          await render2();
          if (event.type === "request-end" || event.type === "background") startPolling();
        });
      },
      /** A panel action queued background work: follow that conversation, or the last one seen. */
      background(conversationId) {
        run(async () => {
          if (!await active()) return;
          if (conversationId) await follow(conversationId);
          startPolling();
        });
      },
      /** The toggle changed: off erases at once; on clears an earlier failure. */
      refresh() {
        run(async () => {
          if (await deps.enabled()) {
            problem = null;
            return;
          }
          stopPolling();
          state = EMPTY;
          await erase();
        });
      },
      /** Why the display stopped for this session, if it did. */
      problem: () => problem,
      /** Resolves when queued work has run (tests). */
      settled: () => queue
    };
  }

  // src/route.ts
  function routeFor(url, setting) {
    if (setting === "direct" || setting === "server") return setting;
    try {
      const host = new URL(url).hostname.replace(/^\[|\]$/g, "");
      return ["localhost", "127.0.0.1", "::1"].includes(host) ? "direct" : "server";
    } catch {
      return "direct";
    }
  }

  // src/inspector.ts
  var TAGS = /* @__PURE__ */ new Set([
    "DIV",
    "P",
    "H1",
    "H2",
    "SPAN",
    "B",
    "BR",
    "A",
    "TABLE",
    "THEAD",
    "TBODY",
    "TR",
    "TH",
    "TD",
    "DETAILS",
    "SUMMARY"
  ]);
  var UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
  var SECTION = /^s-[a-z]{1,20}$/;
  function inspectorApiPath(href) {
    const m = new RegExp(`^/inspector(/c/${UUID}(?:/e/${UUID})?)?(?:[?#]|$)`, "i").exec(href ?? "");
    return m ? `/v1/inspector${m[1] ?? ""}` : null;
  }
  function inspectorConversation(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})(?:/e/${UUID})?$`, "i").exec(path);
    return m ? m[1] : null;
  }
  function inspectorEntity(path) {
    const m = new RegExp(`^/v1/inspector/c/(${UUID})/e/(${UUID})$`, "i").exec(path);
    return m ? { conversation: m[1], entity: m[2] } : null;
  }
  function linkChoices(entities, id) {
    const self = entities.find((e) => e.id === id);
    if (!self || !Array.isArray(self.links)) return null;
    const others = entities.filter((e) => e.id !== id && e.type === self.type).sort((a, b) => b.mentions - a.mentions);
    return { self, others };
  }
  function entityNamed(entities, type, name) {
    return entities.find((e) => e.type === type && e.names.includes(name)) ?? null;
  }
  function sectionTarget(href) {
    const id = href?.startsWith("#") ? href.slice(1) : "";
    return SECTION.test(id) ? id : null;
  }
  function keepAttribute(name, value) {
    switch (name) {
      case "class":
      case "title":
      case "open":
        return true;
      case "id":
        return SECTION.test(value);
      case "href":
        return inspectorApiPath(value) !== null || sectionTarget(value) !== null;
      default:
        return false;
    }
  }
  function safeFragment(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    const clean = (parent) => {
      for (const node of Array.from(parent.childNodes)) {
        if (node.nodeType === Node.TEXT_NODE) continue;
        if (node.nodeType !== Node.ELEMENT_NODE || !TAGS.has(node.nodeName)) {
          node.remove();
          continue;
        }
        const element = node;
        for (const { name, value } of Array.from(element.attributes)) {
          if (!keepAttribute(name, value)) element.removeAttribute(name);
        }
        clean(element);
      }
    };
    clean(template.content);
    return template.content;
  }
  function localTime(iso, lang, now = /* @__PURE__ */ new Date()) {
    const then = new Date(iso);
    if (Number.isNaN(then.getTime())) return null;
    const locale = lang === "en" ? "en" : "ko";
    const title = then.toLocaleString(locale);
    const seconds = Math.round((then.getTime() - now.getTime()) / 1e3);
    const ago = Math.abs(seconds);
    if (seconds > 60 || ago >= 7 * 86400) {
      const date = then.toLocaleDateString(locale, { year: "numeric", month: "2-digit", day: "2-digit" });
      const time = then.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
      return { text: `${date} ${time}`, title };
    }
    const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
    const [value, unit] = ago < 45 ? [0, "second"] : ago < 2700 ? [Math.round(seconds / 60), "minute"] : ago < 79200 ? [Math.round(seconds / 3600), "hour"] : [Math.round(seconds / 86400), "day"];
    return { text: rtf.format(value, unit), title };
  }

  // src/ui.ts
  var LLM_PRESETS = [
    { label: "preset.off", url: "" },
    { label: "preset.ollama", url: "http://host.docker.internal:11434/v1" },
    { label: "OpenRouter", url: "https://openrouter.ai/api/v1" },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
    { label: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash" },
    { label: "Google Vertex AI", url: VERTEX_URL, model: "google/gemini-2.5-flash" },
    { label: "preset.custom", url: "custom" }
  ];
  var EMBED_PRESETS = [
    { label: "preset.off", url: "" },
    { label: "preset.ollama", url: "http://host.docker.internal:11434/v1", model: "qwen3-embedding:0.6b" },
    { label: "OpenAI", url: "https://api.openai.com/v1", model: "text-embedding-3-small" },
    { label: "preset.custom", url: "custom" }
  ];
  var PARSER_EXAMPLE = {
    rules: [
      { id: "roster", kind: "block", role: "char", start: "<status>", end: "</status>", entity_line: "\\[(?P<entity>[^\\]]+)\\]" },
      { id: "hp", kind: "regex", pattern: "HP\\s*[:\uFF1A]\\s*(?P<value>\\d+\\s*/\\s*\\d+)", key: "HP" }
    ]
  };
  var SECTION_TITLE = {
    conn: "conn.title",
    llm: "llm.title",
    emb: "emb.title",
    tune: "tune.title",
    rules: "rules.title"
  };
  var CSS = `
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
.nmos .insp details>summary h2::before{content:"\u25B8 ";color:#6b6d78}.nmos .insp details[open]>summary h2::before{content:"\u25BE "}
.nmos .insp .n{color:#9a9ca8;font-weight:400;font-size:12px}
.nmos .insp .toc{font-size:13px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:#ffd43b}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:12px;margin-top:2px}.nmos .insp details.meta p{margin:4px 0}
.nmos .bar{position:sticky;bottom:0;background:#15161b;border-top:1px solid #30323b;padding:10px max(14px,calc((100% - 760px) / 2 + 14px));display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.nmos .bar .text{flex:1;min-width:160px;font-size:13px}
`;
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === void 0 || v === false) continue;
      if (k === "class") node.className = String(v);
      else if (k === "text") node.textContent = String(v);
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const child of children) node.append(child);
    return node;
  }
  function say(target, text, kind = "muted") {
    target.className = `${target.classList.contains("text") ? "text" : "msg"} ${kind}`;
    target.textContent = text;
  }
  function field(labelText, input) {
    return el("div", {}, el("label", { text: labelText }), input);
  }
  function presetIndex(presets, url) {
    if (!url) return 0;
    const i = presets.findIndex((p) => presetMatches(p.url, url));
    return i >= 0 ? i : presets.length - 1;
  }
  function errorText(lang, error) {
    const text = error instanceof Error ? error.message : String(error);
    return text.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, "invalid")).replace(/^\/v1\/\S+ -> /, t(lang, "sidecar_error"));
  }
  var current = null;
  async function openPanel(deps, tab) {
    if (current && document.body.contains(current.root)) {
      current.select(tab);
      await deps.show();
      return;
    }
    if (!document.getElementById("nmos-style")) document.head.append(el("style", { id: "nmos-style", text: CSS }));
    const lang = langOf(await deps.getArg("language"));
    current = await render(deps, lang, tab);
    await deps.show();
  }
  async function render(deps, lang, tab) {
    const L = (key, vars) => t(lang, key, vars);
    const root = el("div", { class: "nmos", id: "nmos-panel" });
    const wrap = el("div", { class: "wrap" });
    root.append(wrap);
    const language = el(
      "select",
      { "aria-label": L("language") },
      el("option", { value: "ko", text: "\uD55C\uAD6D\uC5B4" }),
      el("option", { value: "en", text: "English" })
    );
    language.value = lang;
    const close = el("button", { text: L("close") });
    const tabStatus = el("button", { text: L("tab.status") });
    const tabInspector = el("button", { text: L("tab.inspector") });
    const tabSettings = el("button", { text: L("tab.settings") });
    wrap.append(
      el("header", {}, el("h1", { text: L("title") }), language, close),
      el("nav", { class: "tabs" }, tabStatus, tabInspector, tabSettings)
    );
    const statusView = el("div");
    const inspectorView = el("div");
    const settingsView = el("div");
    wrap.append(statusView, inspectorView, settingsView);
    let shown = tab;
    async function refreshStatus() {
      statusView.replaceChildren(el("div", { class: "card muted", text: L("status.checking") }));
      const s = await deps.status();
      const base = s.sidecarUrl.replace(/\/+$/, "");
      const conn = el("div", { class: "card" }, el("h2", { text: L("status.sidecar") }));
      if (s.connected) {
        conn.append(
          el(
            "div",
            { class: "line" },
            el("span", { class: "dot ok" }),
            el("span", { text: `${L("status.connected")} \xB7 NMOS ${s.version ?? ""}` })
          ),
          el("div", { class: "mono muted", text: base })
        );
      } else {
        conn.append(
          el(
            "div",
            { class: "line" },
            el("span", { class: "dot err" }),
            el("span", { class: "err", text: `${L("status.unreachable")}: ${base}` })
          ),
          el("div", { class: "muted", text: s.error ?? "" }),
          el("p", { class: "sub", text: L("status.fix") })
        );
      }
      if (!s.enabled) conn.append(el(
        "div",
        { class: "line warn" },
        el("span", { class: "dot warn" }),
        el("span", { text: L("status.memory_off") })
      ));
      const features = el("div", { class: "card" }, el("h2", { text: L("status.features") }));
      const pills = el("div", { class: "pills" });
      for (const [key, name] of [["state", "feature.state"], ["extraction", "feature.extraction"], ["vectors", "feature.vectors"]]) {
        const on = Boolean(s.features?.[key]);
        pills.append(el("span", { class: on ? "pill on" : "pill", text: `${L(name)} ${on ? L("on") : L("off")}` }));
      }
      features.append(s.connected ? pills : el("div", { class: "muted", text: "\u2014" }));
      const lastCard = el("div", { class: "card" }, el("h2", { text: L("status.last") }));
      if (s.last) {
        const kind = s.last.outcome === "injected" ? "ok" : s.last.outcome === "failed" ? "err" : "muted";
        const what = s.last.outcome === "injected" ? L("outcome.injected", { n: s.last.packetChars }) : s.last.outcome === "nothing-relevant" ? L("outcome.nothing") : L("outcome.failed");
        lastCard.append(
          el("div", { class: "line" }, el("span", { class: `dot ${kind}` }), el("span", { text: what })),
          el("div", { class: "muted", text: `${L("status.ago", { n: Math.round((Date.now() - s.last.at) / 1e3) })} \xB7 ${s.last.ms}ms` })
        );
        if (s.last.packet) lastCard.append(el(
          "details",
          { class: "help" },
          el("summary", { text: L("status.packet") }),
          el("pre", { class: "packet", text: s.last.packet })
        ));
        if (s.last.error) lastCard.append(el("div", { class: "mono muted", text: s.last.error }));
        if (s.last.outcome === "failed" && s.last.error?.startsWith("deadline")) {
          lastCard.append(el("p", { class: "sub", text: L("status.deadline_hint") }));
        }
      } else {
        lastCard.append(el("div", { class: "muted", text: L("status.none") }));
      }
      const cards = [conn, features, lastCard];
      const problem = deps.hud.problem();
      if (Number(await deps.getArg("hud")) !== 1) {
        const turnOn = el("button", { text: L("hud.enable") });
        const msg = el("div", { class: "msg" });
        turnOn.addEventListener("click", async () => {
          turnOn.disabled = true;
          const result = await deps.hud.enable();
          if (result === "on") return void refreshStatus();
          turnOn.disabled = false;
          say(msg, L(result === "denied" ? "hud.denied" : "hud.unsupported"), "warn");
        });
        cards.push(el(
          "div",
          { class: "card" },
          el("h2", { text: L("hud.title") }),
          el("div", { class: "muted", text: L("hud.hint") }),
          el("div", { class: "btns" }, turnOn),
          msg
        ));
      } else if (problem) {
        cards.push(el(
          "div",
          { class: "card" },
          el("h2", { text: L("hud.title") }),
          el("div", { class: "warn", text: L("hud.broken", { e: problem }) })
        ));
      }
      const refresh = el("button", { text: L("refresh") });
      refresh.addEventListener("click", () => void refreshStatus());
      statusView.replaceChildren(...cards, el("div", { class: "btns" }, refresh));
    }
    let inspectorPath = "/v1/inspector";
    let shownPath = null;
    let loads = 0;
    const visited = [];
    const inspectorBody = el("div", { class: "insp" });
    const inspectorBack = el("button", { text: L("insp.back") });
    const inspectorRefresh = el("button", { text: L("refresh") });
    const inspectorAddress = el("p", { class: "sub mono" });
    const historyButton = el("button", { text: L("act.history") });
    const rebuildButton = el("button", { text: L("act.rebuild") });
    const deleteButton = el("button", { text: L("act.delete") });
    const actionMsg = el("div", { class: "msg" });
    const actions = el(
      "div",
      {},
      el("div", { class: "btns" }, historyButton, rebuildButton, deleteButton),
      el("details", { class: "sub help" }, el("summary", { text: L("act.help") }), el("p", { text: L("act.sub") }))
    );
    const linkCard = el("div", { class: "card", style: "display:none" });
    inspectorView.append(
      el("div", { class: "btns inspbar" }, inspectorBack, inspectorRefresh),
      actions,
      actionMsg,
      linkCard,
      inspectorBody,
      inspectorAddress
    );
    let actionConversation = null;
    function place() {
      const open = Array.from(inspectorBody.querySelectorAll("details[id]")).filter((d) => d.open);
      return { path: inspectorPath, scroll: root.scrollTop, open: open.map((d) => d.id) };
    }
    function restore(at) {
      for (const d of Array.from(inspectorBody.querySelectorAll("details[id]"))) d.open = at.open.includes(d.id);
      root.scrollTop = at.scroll;
    }
    function enhance(page) {
      for (const span of Array.from(page.querySelectorAll("span.ts[title]"))) {
        const shown2 = localTime(span.getAttribute("title") ?? "", lang);
        if (!shown2) continue;
        span.textContent = shown2.text;
        span.setAttribute("title", shown2.title);
      }
      const who = page.querySelector("p.who");
      if (!who) return;
      const name = who.querySelector("span")?.textContent ?? "";
      const picker = el("select", { "aria-label": name });
      for (const choice of Array.from(who.querySelectorAll("a, b"))) {
        const path = choice.tagName === "B" ? inspectorPath : inspectorApiPath(choice.getAttribute("href"));
        if (path) picker.append(el("option", { value: path, text: choice.textContent ?? "", selected: choice.tagName === "B" }));
      }
      picker.addEventListener("change", () => go(picker.value));
      who.replaceChildren(el("span", { class: "muted", text: name }), picker);
    }
    function go(path) {
      if (path === inspectorPath) return void showInspector();
      if (shownPath) visited.push(place());
      if (visited.length > 30) visited.shift();
      void showInspector(path);
    }
    async function showInspector(path = inspectorPath, at) {
      const load = ++loads;
      const again = path === shownPath;
      const keep = at ?? (again ? place() : void 0);
      inspectorPath = path;
      inspectorBack.style.display = visited.length ? "" : "none";
      const conversation = inspectorConversation(path);
      if (conversation !== actionConversation) {
        actionConversation = conversation;
        say(actionMsg, "");
        disarm();
      }
      actions.style.display = conversation ? "" : "none";
      const shownEntity = inspectorEntity(path);
      if (!shownEntity) linkCard.style.display = "none";
      if (again) {
        inspectorBody.classList.add("busy");
      } else {
        shownPath = null;
        inspectorBody.replaceChildren(el("div", { class: "card muted", text: L("insp.loading") }));
      }
      const base = (await deps.getArg("sidecar_url") || "http://127.0.0.1:8790").replace(/\/+$/, "");
      const direct = routeFor(base, await deps.getArg("route")) === "direct";
      inspectorAddress.textContent = direct ? L("insp.browser", { url: `${base}/inspector${lang === "en" ? "?lang=en" : ""}` }) : "";
      try {
        const r = await deps.api("GET", `${path}${lang === "en" ? "?lang=en" : ""}`, void 0, 15e3);
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
        inspectorBody.replaceChildren(el("div", { class: "card err", text: errorText(lang, error) }));
      } finally {
        if (load === loads) inspectorBody.classList.remove("busy");
      }
    }
    async function showLinks(conversation, entity, load) {
      let entities;
      try {
        entities = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
      } catch {
        entities = [];
      }
      if (load !== loads) return;
      const choices = linkChoices(entities, entity);
      if (!choices) {
        linkCard.style.display = "none";
        return;
      }
      const { self, others } = choices;
      const msg = el("div", { class: "msg" });
      const rows = [];
      for (const link of self.links ?? []) {
        const undo = el("button", { text: L("link.remove") });
        undo.addEventListener("click", async () => {
          undo.disabled = true;
          try {
            await deps.api("POST", `/v1/conversations/${conversation}/entity-links/${link.id}/remove`, {}, 15e3);
            const now = await deps.api("GET", `/v1/conversations/${conversation}/entities`, void 0, 15e3);
            const next = entityNamed(now, self.type, self.name);
            say(actionMsg, L("link.removed"), "ok");
            if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
            else await showInspector();
          } catch (error) {
            say(msg, errorText(lang, error), "err");
            undo.disabled = false;
          }
        });
        rows.push(el("div", { class: "btns" }, el("span", { text: `${link.name} = ${link.same_as}` }), undo));
      }
      const card = [el("h2", { text: L("link.title") }), el("p", { class: "sub", text: L("link.sub") }), ...rows];
      if (others.length) {
        const pick = el(
          "select",
          { "aria-label": L("link.pick") },
          ...others.map((e) => el("option", { value: e.name, text: `${e.name} (${e.mentions})` }))
        );
        const join = el("button", { text: L("link.join") });
        join.addEventListener("click", async () => {
          join.disabled = true;
          try {
            const r = await deps.api(
              "POST",
              `/v1/conversations/${conversation}/entity-links`,
              { entity_type: self.type, name: self.name, same_as: pick.value },
              15e3
            );
            say(actionMsg, L("link.done", { a: self.name, b: pick.value }), "ok");
            if (r.entity && r.entity.id !== entity) go(`/v1/inspector/c/${conversation}/e/${r.entity.id}`);
            else await showInspector();
          } catch (error) {
            say(msg, errorText(lang, error), "err");
            join.disabled = false;
          }
        });
        card.push(el("div", { class: "row" }, field(L("link.pick"), pick), el("div", { class: "btns" }, join)));
      } else {
        card.push(el("div", { class: "muted", text: L("link.none") }));
      }
      linkCard.replaceChildren(...card, msg);
      linkCard.style.display = "";
    }
    inspectorBody.addEventListener("click", (event) => {
      const link = event.target instanceof Element ? event.target.closest("a") : null;
      if (!link) return;
      event.preventDefault();
      const href = link.getAttribute("href");
      const section = sectionTarget(href);
      const target = section ? inspectorBody.querySelector(`#${section}`) : null;
      if (target) {
        if (target instanceof HTMLDetailsElement) target.open = true;
        target.scrollIntoView({ block: "start", behavior: "smooth" });
        return;
      }
      const path = inspectorApiPath(href);
      if (path) go(path);
    });
    inspectorBack.addEventListener("click", () => {
      const at = visited.pop();
      if (at) void showInspector(at.path, at);
    });
    inspectorRefresh.addEventListener("click", () => void showInspector());
    const confirmable = [
      [rebuildButton, "act.rebuild", "primary"],
      [deleteButton, "act.delete", "danger"]
    ];
    let armed = null;
    let armTimer = 0;
    function disarm() {
      window.clearTimeout(armTimer);
      armed = null;
      for (const [button, label] of confirmable) {
        button.textContent = L(label);
        button.className = "";
      }
    }
    function confirmed(button, confirm, cls) {
      if (armed === button) {
        disarm();
        return true;
      }
      disarm();
      armed = button;
      button.textContent = L(confirm);
      button.className = cls;
      armTimer = window.setTimeout(disarm, 6e3);
      return false;
    }
    function actionError(error) {
      return /HTTP 409/.test(error instanceof Error ? error.message : String(error)) ? L("act.off") : errorText(lang, error);
    }
    historyButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation) return;
      disarm();
      historyButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/extract-history`, {}, 3e4);
        const n = (r.queued.extract ?? 0) + (r.queued.embed ?? 0);
        say(actionMsg, n ? L("act.history_done", { t: r.queued.extract ?? 0, m: r.queued.embed ?? 0 }) : L("act.history_none"), "ok");
        if (n) deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      } finally {
        historyButton.disabled = false;
      }
    });
    rebuildButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation || !confirmed(rebuildButton, "act.rebuild_confirm", "primary")) return;
      rebuildButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/rebuild`, {}, 3e4);
        say(actionMsg, L("act.rebuild_done", { d: r.discarded ?? 0, t: r.queued.extract ?? 0 }), "ok");
        deps.hud.background(conversation);
        await showInspector();
      } catch (error) {
        say(actionMsg, actionError(error), "err");
      } finally {
        rebuildButton.disabled = false;
      }
    });
    deleteButton.addEventListener("click", async () => {
      const conversation = actionConversation;
      if (!conversation || !confirmed(deleteButton, "act.delete_confirm", "danger")) return;
      deleteButton.disabled = true;
      say(actionMsg, L("act.working"));
      try {
        const r = await deps.api("POST", `/v1/conversations/${conversation}/delete`, {}, 6e4);
        visited.length = 0;
        await showInspector("/v1/inspector");
        say(actionMsg, L("act.delete_done", { m: r.deleted.messages ?? 0 }), "ok");
      } catch (error) {
        say(actionMsg, errorText(lang, error), "err");
      } finally {
        deleteButton.disabled = false;
      }
    });
    const hudBox = el("input", { type: "checkbox" });
    const hudMsg = el("div", { class: "msg" });
    hudBox.addEventListener("change", async () => {
      hudBox.disabled = true;
      try {
        if (!hudBox.checked) {
          await deps.hud.disable();
          return say(hudMsg, L("hud.off"), "muted");
        }
        const result = await deps.hud.enable();
        hudBox.checked = result === "on";
        if (result === "on") say(hudMsg, L("hud.on"), "ok");
        else say(hudMsg, L(result === "denied" ? "hud.denied" : "hud.unsupported"), "warn");
      } catch (error) {
        say(hudMsg, errorText(lang, error), "err");
      } finally {
        hudBox.disabled = false;
      }
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("hud.title") }),
      el("p", { class: "sub", text: L("hud.sub") }),
      el("div", { class: "check" }, hudBox, el("span", { text: L("hud.toggle") })),
      hudMsg
    ));
    const url = el("input", { spellcheck: "false" });
    const route = el("select", {}, ...["auto", "direct", "server"].map((v) => el("option", { value: v, text: v })));
    const enabled = el("input", { type: "checkbox" });
    const reserved = el("input", { type: "number", min: 100, max: 8e3 });
    const deadline = el("input", { type: "number", min: 200, max: MAX_DEADLINE_MS, step: 100 });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("conn.title") }),
      el("p", { class: "sub", text: L("conn.sub") }),
      field(L("conn.url"), url),
      el("div", { class: "row" }, field(L("conn.route"), route), field(L("conn.budget"), reserved), field(L("conn.deadline"), deadline)),
      el("div", { class: "check" }, enabled, el("span", { text: L("conn.enabled") })),
      el("p", { class: "sub", text: L("conn.hint") }),
      el("p", { class: "sub", text: L("conn.deadline_hint") })
    ));
    function modelSection(kind, title, sub, presets) {
      const preset = el("select", {}, ...presets.map((p, i) => el("option", {
        value: String(i),
        text: p.label.includes(".") ? L(p.label) : p.label
      })));
      const endpoint = el("input", { placeholder: "https://\u2026/v1", spellcheck: "false" });
      const model = el("input", { placeholder: L(kind === "llm" ? "model.llm_placeholder" : "model.emb_placeholder"), spellcheck: "false" });
      const list = el("select", { style: "display:none" });
      const key = el("input", { type: "password", placeholder: L("model.key_placeholder"), autocomplete: "off" });
      const msg = el("div", { class: "msg" });
      const load = el("button", { text: L("model.load") });
      const test = el("button", { text: L("model.test") });
      preset.addEventListener("change", () => {
        const p = presets[Number(preset.value)];
        if (p.url !== "custom") endpoint.value = fillProject(p.url, key.value);
        if (p.model) model.value = p.model;
        if (!p.url) model.value = "";
        say(msg, p.url.includes("{project}") ? L("model.vertex_hint") : "");
        update();
      });
      key.addEventListener("input", () => {
        endpoint.value = fillProject(endpoint.value, key.value);
      });
      list.addEventListener("change", () => {
        model.value = list.value;
        update();
      });
      load.addEventListener("click", async () => {
        say(msg, L("model.loading"));
        try {
          const r = await deps.api(
            "POST",
            "/v1/config/models",
            { kind, url: endpoint.value.trim(), api_key: key.value.trim() || void 0 }
          );
          if (!r.ok) return say(msg, L("model.list_failed", { e: r.error ?? "" }), "err");
          list.replaceChildren(
            el("option", { value: "", text: L("model.pick", { n: r.models.length }) }),
            ...r.models.map((m) => el("option", { value: m, text: m }))
          );
          list.style.display = "";
          say(msg, L("model.found", { n: r.models.length }), "ok");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        }
      });
      test.addEventListener("click", async () => {
        test.disabled = true;
        say(msg, L("model.testing"));
        try {
          const r = await deps.api(
            "POST",
            "/v1/config/test",
            { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || void 0 }
          );
          say(msg, r.ok ? L("model.test_ok", { ms: r.ms }) + (r.dimensions ? L("model.dims", { n: r.dimensions }) : "") : L("model.test_failed", { e: r.error ?? "" }), r.ok ? "ok" : "err");
        } catch (error) {
          say(msg, errorText(lang, error), "err");
        } finally {
          test.disabled = false;
        }
      });
      settingsView.append(el(
        "div",
        { class: "card" },
        el("h2", { text: L(title) }),
        el("p", { class: "sub", text: L(sub) }),
        field(L("model.provider"), preset),
        field(L("model.endpoint"), endpoint),
        field(L("model.model"), model),
        list,
        field(L("model.key"), key),
        el("div", { class: "btns" }, load, test),
        msg
      ));
      return {
        values: () => ({ url: endpoint.value, model: model.value, key: key.value }),
        fill(cfg) {
          preset.value = String(presetIndex(presets, cfg.url));
          endpoint.value = cfg.url;
          model.value = cfg.model;
          key.value = "";
          key.placeholder = L(cfg.api_key_set ? "model.key_saved" : "model.key_placeholder");
        }
      };
    }
    const llm = modelSection("llm", "llm.title", "llm.sub", LLM_PRESETS);
    const emb = modelSection("embeddings", "emb.title", "emb.sub", EMBED_PRESETS);
    const threshold = el("input", { type: "number", step: 0.05, min: 0.05, max: 1 });
    const minSim = el("input", { type: "number", step: 0.01, min: 0, max: 1 });
    const topK = el("input", { type: "number", min: 0, max: 20 });
    const factsLimit = el("input", { type: "number", min: 0, max: 30 });
    const backfill = el("input", { type: "number", min: 0, max: 5e3 });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("tune.title") }),
      el("p", { class: "sub", text: L("tune.sub") }),
      el("div", { class: "row" }, field(L("tune.threshold"), threshold), field(L("tune.min_sim"), minSim)),
      el("div", { class: "row" }, field(L("tune.top_k"), topK), field(L("tune.facts"), factsLimit), field(L("tune.backfill"), backfill))
    ));
    const rules = el("textarea", { spellcheck: "false" });
    const example = el("button", { text: L("rules.example") });
    example.addEventListener("click", () => {
      rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2);
      update();
    });
    settingsView.append(el(
      "div",
      { class: "card" },
      el("h2", { text: L("rules.title") }),
      el("p", { class: "sub", text: L("rules.sub") }),
      rules,
      el("div", { class: "btns" }, example)
    ));
    const barText = el("span", { class: "text muted" });
    const revert = el("button", { text: L("revert") });
    const save = el("button", { class: "primary", text: L("save") });
    const bar = el("div", { class: "bar" }, barText, revert, save);
    root.append(bar);
    function values() {
      return {
        conn: { url: url.value, route: route.value, enabled: enabled.checked, reserved: reserved.value, deadline: deadline.value },
        llm: llm.values(),
        emb: emb.values(),
        tune: { threshold: threshold.value, minSim: minSim.value, topK: topK.value, facts: factsLimit.value, backfill: backfill.value },
        rules: rules.value
      };
    }
    let baseline = values();
    let closing = false;
    const dirty = () => dirtySections(baseline, values());
    function update(message) {
      const d = dirty();
      save.disabled = d.length === 0;
      revert.disabled = d.length === 0;
      if (message) say(barText, message.text, message.kind);
      else if (d.length) say(barText, L("unsaved", { s: d.map((s) => L(SECTION_TITLE[s])).join(", ") }), "warn");
      else say(barText, "", "muted");
    }
    settingsView.addEventListener("input", () => update());
    settingsView.addEventListener("change", () => update());
    async function loadConn() {
      url.value = await deps.getArg("sidecar_url") || "http://127.0.0.1:8790";
      route.value = await deps.getArg("route") || "auto";
      enabled.checked = Number(await deps.getArg("disabled")) !== 1;
      reserved.value = String(Number(await deps.getArg("reserved_memory_tokens")) || 600);
      deadline.value = String(Number(await deps.getArg("deadline_ms")) || DEFAULT_DEADLINE_MS);
      hudBox.checked = Number(await deps.getArg("hud")) === 1;
    }
    function fillServer(cfg) {
      llm.fill(cfg.llm);
      emb.fill(cfg.embeddings);
      threshold.value = String(cfg.recall.threshold);
      minSim.value = String(cfg.recall.vector_min_sim);
      topK.value = String(cfg.recall.top_k);
      factsLimit.value = String(cfg.recall.facts_limit);
      backfill.value = String(cfg.extraction.backfill);
      rules.value = cfg.parsers.source === "ui" ? JSON.stringify(cfg.parsers.rules, null, 2) : "";
      rules.placeholder = cfg.parsers.source === "file" ? L("rules.from_file", { n: cfg.parsers.active_rules }) : L("rules.none");
    }
    async function loadAll() {
      await loadConn();
      try {
        fillServer(await deps.api("GET", "/v1/config", void 0, 5e3));
      } catch {
      }
      baseline = values();
      update();
    }
    async function saveAll() {
      const d = dirty();
      if (!d.length) {
        update({ text: L("no_changes"), kind: "muted" });
        return true;
      }
      save.disabled = true;
      say(barText, L("saving"));
      const v = values();
      if (d.includes("conn")) {
        for (const [k, value] of Object.entries(connArgs(v.conn))) await deps.setArg(k, value);
        baseline = { ...baseline, conn: v.conn };
      }
      const body = configBody(d, v);
      if (!Object.keys(body).length) {
        update({ text: L("saved"), kind: "ok" });
        return true;
      }
      try {
        const r = await deps.api("PUT", "/v1/config", body);
        fillServer(r);
        baseline = values();
        const parts = [r.queued_jobs ? L("saved_queued", { n: r.queued_jobs }) : L("saved")];
        if (r.queued_jobs) deps.hud.background();
        if (d.includes("rules") && r.parsers.active_rules) parts.push(L("saved_rules", { n: r.parsers.active_rules }));
        update({ text: parts.join(" "), kind: "ok" });
        return true;
      } catch (error) {
        const text = errorText(lang, error);
        update({ text: d.includes("conn") ? L("conn_saved_server_failed", { e: text }) : text, kind: "err" });
        return false;
      }
    }
    save.addEventListener("click", () => void saveAll());
    revert.addEventListener("click", () => void loadAll());
    function shut() {
      root.remove();
      current = null;
      void deps.hide();
    }
    close.addEventListener("click", () => {
      if (!dirty().length || closing) return shut();
      closing = true;
      const saveClose = el("button", { class: "primary", text: L("save_and_close") });
      const discard = el("button", { text: L("discard_and_close") });
      const cancel = el("button", { text: L("cancel") });
      const restore2 = () => {
        closing = false;
        bar.replaceChildren(barText, revert, save);
        update();
      };
      saveClose.addEventListener("click", async () => {
        if (await saveAll()) shut();
        else restore2();
      });
      discard.addEventListener("click", shut);
      cancel.addEventListener("click", restore2);
      select("settings");
      bar.replaceChildren(el("span", { class: "text warn", text: L("close_unsaved") }), cancel, discard, saveClose);
    });
    language.addEventListener("change", async () => {
      if (dirty().length) {
        language.value = lang;
        select("settings");
        update({ text: L("lang_unsaved"), kind: "warn" });
        return;
      }
      const next = langOf(language.value);
      await deps.setArg("language", next);
      root.remove();
      current = await render(deps, next, shown);
    });
    function select(next) {
      shown = next;
      const views = [
        ["status", statusView, tabStatus],
        ["inspector", inspectorView, tabInspector],
        ["settings", settingsView, tabSettings]
      ];
      for (const [name, view2, button] of views) {
        view2.style.display = name === next ? "" : "none";
        button.className = name === next ? "on" : "";
      }
      bar.style.display = next === "settings" ? "" : "none";
      root.classList.toggle("wide", next === "inspector");
      if (next === "status") void refreshStatus();
      if (next === "inspector") void showInspector();
    }
    tabStatus.addEventListener("click", () => select("status"));
    tabInspector.addEventListener("click", () => select("inspector"));
    tabSettings.addEventListener("click", () => select("settings"));
    document.body.append(root);
    select(tab);
    await loadAll();
    return { root, select };
  }

  // src/host.ts
  var DEFAULT_SIDECAR_URL = "http://127.0.0.1:8790";
  var DEFAULT_RESERVED_TOKENS = 600;
  async function arg(key) {
    return String(await risuai.getArgument(key) ?? "").trim();
  }
  function fetchOptions(route) {
    return route === "server" ? { networkRoute: "local_network" } : {};
  }
  function positiveInt(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
  }
  var risuHost = {
    async settings() {
      const position = await arg("inject_position");
      const sidecarUrl = await arg("sidecar_url") || DEFAULT_SIDECAR_URL;
      return {
        sidecarUrl,
        route: routeFor(sidecarUrl, await arg("route")),
        authToken: await arg("auth_token"),
        enabled: Number(await arg("disabled")) !== 1,
        reservedMemoryTokens: positiveInt(await arg("reserved_memory_tokens"), DEFAULT_RESERVED_TOKENS),
        deadlineMs: positiveInt(await arg("deadline_ms"), DEFAULT_DEADLINE_MS),
        injectPosition: position === "end" ? "end" : "before_last_user",
        language: langOf(await arg("language"))
      };
    },
    async currentChat() {
      const characterIndex = await risuai.getCurrentCharacterIndex();
      const chatIndex = await risuai.getCurrentChatIndex();
      return risuai.getChatFromIndex(characterIndex, chatIndex);
    },
    async characterName(chatId) {
      const character = await risuai.getCharacterFromIndex(await risuai.getCurrentCharacterIndex());
      if (!character?.chats?.some((c) => c?.id === chatId)) return null;
      return typeof character.name === "string" && character.name.trim() ? character.name.trim() : null;
    },
    async personas() {
      if (typeof risuai.getDatabase !== "function") return null;
      const db = await risuai.getDatabase(["personas", "selectedPersona"]);
      if (!db || !Array.isArray(db.personas)) return null;
      const personas = db.personas.map((p) => {
        const { id, name } = p ?? {};
        return { id: typeof id === "string" ? id : void 0, name: typeof name === "string" ? name : void 0 };
      });
      return { personas, selected: Number.isInteger(db.selectedPersona) ? Number(db.selectedPersona) : 0 };
    },
    async request(method, url, body, headers, timeoutMs, route) {
      const res = await risuai.nativeFetch(url, {
        method,
        headers,
        ...body === void 0 ? {} : { body: JSON.stringify(body) },
        requestTimeoutMs: Math.max(1, Math.floor(timeoutMs)),
        ...fetchOptions(route)
      });
      let json = null;
      try {
        json = await res.json();
      } catch {
        json = null;
      }
      return { status: res.status, json };
    },
    warn: (...args) => console.warn(...args),
    debug: (...args) => console.debug(...args),
    now: () => performance.now()
  };
  function createRisuHud(link) {
    const hud = createHud({
      enabled: async () => Number(await arg("hud")) === 1,
      lang: async () => langOf(await arg("language")),
      rootDocument: async () => typeof risuai.getRootDocument === "function" ? risuai.getRootDocument() : null,
      position: async () => `${await risuai.getCurrentCharacterIndex()}:${await risuai.getCurrentChatIndex()}`,
      coverage: (conversationId) => link.coverage(conversationId),
      openPanel: () => link.openPanel(),
      now: () => performance.now(),
      debug: (...args) => console.debug(...args),
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (handle) => clearTimeout(handle)
    });
    const control = {
      event: hud.event,
      async enable() {
        if (typeof risuai.requestPluginPermission !== "function" || typeof risuai.getRootDocument !== "function") {
          return "unsupported";
        }
        await risuai.hideContainer();
        let granted = false;
        try {
          granted = await risuai.requestPluginPermission("mainDom") === true;
        } finally {
          await risuai.showContainer("fullscreen");
        }
        await risuai.setArgument("hud", granted ? 1 : 0);
        hud.refresh();
        return granted ? "on" : "denied";
      },
      async disable() {
        await risuai.setArgument("hud", 0);
        hud.refresh();
      },
      problem: hud.problem,
      background: hud.background
    };
    return control;
  }
  async function registerHooks(beforeRequest, onOutput, status, api, hud) {
    await risuai.addRisuReplacer("beforeRequest", beforeRequest);
    await risuai.addRisuChatListener("output", onOutput);
    const deps = {
      api,
      status,
      getArg: arg,
      setArg: (key, value) => risuai.setArgument(key, value),
      show: () => risuai.showContainer("fullscreen"),
      hide: () => risuai.hideContainer(),
      hud
    };
    const open = (tab) => openPanel(deps, tab);
    const lang = langOf(await arg("language"));
    await risuai.registerSetting(t(lang, "menu.panel"), () => open("status"), "\u{1F9E0}", "html", "nmos-panel");
    await risuai.registerButton(
      { name: t(lang, "menu.panel"), icon: "\u{1F9E0}", iconType: "html", location: "chat", id: "nmos-chat" },
      () => open("status")
    );
    return () => void open("status");
  }

  // src/entry.ts
  (async () => {
    let openStatus = () => {
    };
    const hud = createRisuHud({
      coverage: (conversationId) => adapter.api("GET", `/v1/conversations/${conversationId}/coverage`, void 0, 5e3),
      openPanel: () => openStatus()
    });
    const adapter = createAdapter(risuHost, (event) => hud.event(event));
    openStatus = await registerHooks(
      async (prompt, mode) => {
        try {
          return await adapter.beforeRequest(prompt, mode);
        } catch {
          return prompt;
        }
      },
      (arg2) => adapter.onOutput(arg2),
      () => adapter.status(),
      (method, path, body, timeoutMs) => adapter.api(method, path, body, timeoutMs),
      hud
    );
    adapter.warmPersonas();
    console.log("[NMOS] adapter loaded", { version: "0.1.0-beta.18" });
  })().catch((error) => console.error("[NMOS] adapter failed to load", error));
})();
