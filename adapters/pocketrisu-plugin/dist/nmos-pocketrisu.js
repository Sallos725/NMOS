//@name nmos_memory
//@display-name NMOS Narrative Memory
//@api 3.0
//@version 0.1.0-beta.1
//@link https://github.com/Sallos725/NMOS Documentation
//@update-url https://raw.githubusercontent.com/Sallos725/NMOS/main/adapters/pocketrisu-plugin/dist/nmos-pocketrisu.js
//@arg sidecar_url string NMOS sidecar URL (empty = http://127.0.0.1:8790)
//@arg auth_token string Optional; only if the sidecar sets NMOS_AUTH_TOKEN
//@arg disabled int 1 = pass every request through untouched
//@arg reserved_memory_tokens int Max packet tokens; lower the host max context by this much (0 = 600)
//@arg deadline_ms int Hard request-path deadline in ms (0 = 800)
//@arg inject_position string before_last_user (default) or end
//@arg route string auto (default) / direct / server — how to reach the sidecar
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
  async function buildManifest(chat, characterRef) {
    const messages = Array.isArray(chat.message) ? chat.message : [];
    const hashes = await Promise.all(messages.map((m) => sha256Hex(canonicalJson(hashPayload(m)))));
    const bodies = /* @__PURE__ */ new Map();
    const entries = messages.map((m, i) => {
      const meta = revisionMetadata(m);
      const revisionHash = hashes[i];
      const logicalId = String(m.chatId ?? "");
      bodies.set(bodyKey(logicalId, revisionHash), {
        host_logical_id: logicalId,
        revision_hash: revisionHash,
        content: normalizeText(selectedContent(m)),
        metadata: meta
      });
      return {
        host_logical_id: logicalId,
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
    });
    return {
      request: { host: "pocketrisu", chat_id: String(chat.id ?? ""), character_ref: characterRef, hash_version: 1, messages: entries },
      bodies
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
  function isMainGeneration(prompt, mode, hostMessages) {
    if (mode !== "model" || !Array.isArray(prompt)) return false;
    const hostIndex = latestUserIndex(hostMessages);
    if (hostIndex < 0) return false;
    let promptUser;
    for (let i = prompt.length - 1; i >= 0; i -= 1) {
      if (prompt[i]?.role === "user") {
        promptUser = prompt[i];
        break;
      }
    }
    if (!promptUser) return false;
    const expected = cleanText(selectedContent(hostMessages[hostIndex]));
    const sent = cleanText(contentText(promptUser.content));
    return expected.length > 0 && (sent === expected || sent.includes(anchorOf(expected, 64)));
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
  function injectPacket(prompt, packet, position = "before_last_user") {
    if (!packet || hasPacket(prompt)) return prompt;
    const message = { role: "system", content: packet };
    const out = prompt.slice();
    if (position === "end") {
      out.push(message);
      return out;
    }
    let index = out.length;
    for (let i = out.length - 1; i >= 0; i -= 1) {
      if (out[i]?.role === "user") {
        index = i;
        break;
      }
    }
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
  function createAdapter(host) {
    const cache = /* @__PURE__ */ new Map();
    let last = null;
    function remember(key, packet, ttl) {
      cache.set(key, { packet, expires: host.now() + ttl });
      while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
    }
    async function call(settings, path, body, deadline) {
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
        const request = body === void 0 ? host.get(url, headers, remaining, settings.route) : host.post(url, body, headers, remaining, settings.route);
        const res = await Promise.race([request, timeout]);
        if (res.status < 200 || res.status >= 300) throw new Error(`${path} -> HTTP ${res.status}`);
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
      try {
        if (mode !== "model" || hasPacket(prompt)) return prompt;
        settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl) return prompt;
        const deadline = started + settings.deadlineMs;
        const chat = await host.currentChat();
        const messages = Array.isArray(chat?.message) ? chat.message : [];
        if (!chat?.id || !isMainGeneration(prompt, mode, messages)) return prompt;
        const t0 = host.now();
        const { request, bodies } = await buildManifest(chat, firstSaying(messages));
        const manifestMs = host.now() - t0;
        key = await sha256Hex(canonicalJson([
          chat.id,
          mode,
          prompt.length,
          request.messages.map((m) => [m.host_logical_id, m.revision_hash])
        ]));
        const cached = cache.get(key);
        if (cached && cached.expires > host.now()) return injectPacket(prompt, cached.packet, settings.injectPosition);
        const t1 = host.now();
        const synced = await sync(settings, request, bodies, deadline);
        const syncMs = host.now() - t1;
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
        last = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: packet.length,
          outcome: packet ? "injected" : "nothing-relevant"
        };
        return injectPacket(prompt, packet, settings.injectPosition);
      } catch (error) {
        if (key) remember(key, "", FAILURE_TTL_MS);
        last = {
          at: Date.now(),
          ms: Math.round(host.now() - started),
          packetChars: 0,
          outcome: "failed",
          error: error instanceof Error ? error.message : String(error)
        };
        host.warn("[NMOS] memory skipped for this request (fail open):", error instanceof Error ? error.message : error);
        return prompt;
      }
    }
    function onOutput(arg2) {
      void (async () => {
        const settings = await host.settings();
        if (!settings.enabled || !settings.sidecarUrl || !arg2?.chat?.id) return;
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
    async function statusText() {
      const settings = await host.settings();
      const lines = [];
      if (!settings.enabled) lines.push("NMOS: \uAEBC\uC9D0 (disabled = 1) / disabled");
      try {
        const res = await call(
          settings,
          "/v1/health",
          void 0,
          host.now() + 3e3
        );
        const f = res.features ?? {};
        const on = (b) => b ? "on" : "off";
        lines.push(`NMOS ${res.version} \uC5F0\uACB0\uB428 / connected \u2014 ${settings.sidecarUrl}`);
        lines.push(`\uC0C1\uD0DC\uCC3D state ${on(f.state)} \xB7 \uC0AC\uC2E4 facts ${on(f.extraction)} \xB7 \uC758\uBBF8\uAC80\uC0C9 vectors ${on(f.vectors)}`);
      } catch (error) {
        lines.push(`\uC0AC\uC774\uB4DC\uCE74\uC5D0 \uC5F0\uACB0\uD560 \uC218 \uC5C6\uC74C / cannot reach sidecar: ${settings.sidecarUrl}`);
        lines.push(`(${error instanceof Error ? error.message : String(error)})`);
        lines.push("\uD655\uC778: docker compose up -d \xB7 NMOS_CORS_ORIGINS\uC5D0 \uC774 \uC8FC\uC18C \uD3EC\uD568 \xB7 localhost/HTTPS\uB85C \uC811\uC18D");
      }
      if (last) {
        const ago = Math.round((Date.now() - last.at) / 1e3);
        const what = last.outcome === "injected" ? `\uAE30\uC5B5 \uC8FC\uC785 ${last.packetChars}\uC790 / injected` : last.outcome === "nothing-relevant" ? "\uAD00\uB828 \uAE30\uC5B5 \uC5C6\uC74C / nothing relevant" : `\uC2E4\uD328 / failed: ${last.error}`;
        lines.push(`\uB9C8\uC9C0\uB9C9 \uC694\uCCAD / last request: ${ago}s \uC804 \xB7 ${what} \xB7 ${last.ms}ms`);
      } else {
        lines.push("\uC544\uC9C1 \uC694\uCCAD \uC5C6\uC74C \u2014 \uBA54\uC2DC\uC9C0\uB97C \uBCF4\uB0B4 \uBCF4\uC138\uC694 / no request yet");
      }
      return lines.join("\n");
    }
    return { beforeRequest, onOutput, statusText };
  }
  function firstSaying(messages) {
    for (const m of messages) if (m.role === "char" && m.saying) return m.saying;
    return null;
  }

  // src/host.ts
  var DEFAULT_SIDECAR_URL = "http://127.0.0.1:8790";
  var DEFAULT_RESERVED_TOKENS = 600;
  var DEFAULT_DEADLINE_MS = 800;
  async function arg(key) {
    return String(await risuai.getArgument(key) ?? "").trim();
  }
  function routeFor(url, setting) {
    if (setting === "direct" || setting === "server") return setting;
    try {
      const host = new URL(url).hostname.replace(/^\[|\]$/g, "");
      return ["localhost", "127.0.0.1", "::1"].includes(host) ? "direct" : "server";
    } catch {
      return "direct";
    }
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
        injectPosition: position === "end" ? "end" : "before_last_user"
      };
    },
    async currentChat() {
      const characterIndex = await risuai.getCurrentCharacterIndex();
      const chatIndex = await risuai.getCurrentChatIndex();
      return risuai.getChatFromIndex(characterIndex, chatIndex);
    },
    async post(url, body, headers, timeoutMs, route) {
      const res = await risuai.nativeFetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
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
    async get(url, headers, timeoutMs, route) {
      const res = await risuai.nativeFetch(url, {
        method: "GET",
        headers,
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
  async function registerHooks(beforeRequest, onOutput, status) {
    await risuai.addRisuReplacer("beforeRequest", beforeRequest);
    await risuai.addRisuChatListener("output", onOutput);
    await risuai.registerSetting("NMOS \uC0C1\uD0DC / Status", async () => {
      await risuai.alert(await status());
    }, "\u{1F9E0}", "html", "nmos-status");
  }

  // src/entry.ts
  (async () => {
    const adapter = createAdapter(risuHost);
    await registerHooks(
      async (prompt, mode) => {
        try {
          return await adapter.beforeRequest(prompt, mode);
        } catch {
          return prompt;
        }
      },
      (arg2) => adapter.onOutput(arg2),
      () => adapter.statusText()
    );
    console.log("[NMOS] adapter loaded", { version: "0.1.0-beta.1" });
  })().catch((error) => console.error("[NMOS] adapter failed to load", error));
})();
