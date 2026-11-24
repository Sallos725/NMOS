"""Sidecar settings from environment variables."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

from . import rerank

RERANK_TIMEOUT_MS = (50, 5000)  # PHASE-60 S5: the reranker's own wait, in milliseconds, inclusive
# PHASE-62 S1: the cap on each message the extraction model is shown, in normalized characters, inclusive. The lower
# bound is the default (`extraction.TARGET_CHARS`, `summaries.MESSAGE_CHARS`): what every earlier release read.
TARGET_CHARS = (6000, 36000)

# PHASE-61 S1 (ADR 0088 item 1): the extra request body merged into every chat-completions body of the extraction model.
EXTRA_BODY_MAX_BYTES = 2048  # as canonical JSON (`canonical_body`), UTF-8
EXTRA_BODY_MAX_DEPTH = 16  # nesting of objects and lists; deeper is refused before anything recurses into it
# From here on a float's shortest text has an exponent (`1e+16`), which JSONB stores and returns as an integer.
FLOAT_EXPONENT_FROM = 1e16
# The request's own fields: JSON mode owns `response_format`, `llm_no_temperature` owns `temperature` (S1b).
RESERVED_BODY_KEYS = frozenset({"model", "messages", "stream", "response_format", "temperature", "n", "tools",
                                "tool_choice", "functions", "function_call"})
# A key name is plain ASCII: letters, digits, `_`, `-` and `.` (provider parameters are), so no look-alike letter or
# compatibility form can hide a credential's name. Such a name is credential-like when, lower-cased with everything
# but letters and digits removed, it contains one of CREDENTIAL_PARTS, is one of CREDENTIAL_NAMES, or ends with
# `token` (`token`, `access_token`, `oauth_token`; `max_tokens` and `tokenizer` are legitimate).
PLAIN_KEY = re.compile(r"[A-Za-z0-9_.\-]*")
CREDENTIAL_PARTS = ("apikey", "authorization", "secret", "password", "passwd", "bearer", "credential", "privatekey",
                    "accesskey", "subscriptionkey", "cookie")
CREDENTIAL_NAMES = frozenset({"auth", "key"})


def canonical_body(body: Any) -> str:
    """The body as canonical JSON: sorted keys, no spaces, non-ASCII kept (the size limit is counted on it)."""
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def plain_key(key: str) -> bool:
    return PLAIN_KEY.fullmatch(key) is not None


def credential_like(key: str) -> bool:
    name = re.sub(r"[^a-z0-9]", "", key.lower())
    return (any(part in name for part in CREDENTIAL_PARTS) or name in CREDENTIAL_NAMES
            or name.endswith("token"))


def _unstorable(text: str) -> bool:
    """A NUL or a lone surrogate: PostgreSQL's JSONB refuses both, and neither belongs in a request."""
    return "\x00" in text or any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def extra_body_error(body: Any) -> str | None:
    """Why `body` may not be the extra request body (PHASE-61 S1), or None when it may. One check for the panel's save,
    the settings test, a saved value read back and the environment. The reason names a key path, never a value."""
    if not isinstance(body, dict):
        return "must be a JSON object"
    for key in body:
        if key in RESERVED_BODY_KEYS:
            return f"may not set {key!r}: the request sets it itself"
    stack: list[tuple[Any, str, int]] = [(body, "", 1)]
    while stack:  # iterative: a deeply nested value is refused, never a RecursionError
        value, path, depth = stack.pop()
        if isinstance(value, (dict, list)) and depth > EXTRA_BODY_MAX_DEPTH:
            return f"is nested deeper than {EXTRA_BODY_MAX_DEPTH} levels"
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    return f"has a key that is not text{f' in {path}' if path else ''}"
                if _unstorable(key):
                    return f"has a key with a NUL or an unpaired surrogate{f' in {path}' if path else ''}"
                where = f"{path}.{key}" if path else key
                if not plain_key(key):
                    return (f"has a key that is not plain ASCII ({ascii(where)}): key names are plain ASCII letters,"
                            " digits, '_', '-' and '.'")
                if credential_like(key):
                    return (f"may not hold a credential-like key ({where}): an API key belongs in the key field, which"
                            " is never shown or archived")
                stack.append((item, where, depth + 1))
        elif isinstance(value, list):
            stack.extend((item, f"{path}[{i}]", depth + 1) for i, item in enumerate(value))
        elif isinstance(value, float):
            if not math.isfinite(value):
                return f"holds a number JSON cannot carry at {path}"
            # PostgreSQL's JSONB writes a number back without an exponent or a signed zero: such a float would come
            # back in another form (1e300 as a 301-digit integer), so the stored body would not be the one checked.
            if abs(value) >= FLOAT_EXPONENT_FROM or (value == 0 and math.copysign(1.0, value) < 0):
                return (f"holds a number at {path} the database would store in another form (a decimal or exponent"
                        " number of 1e16 or more, or -0.0): write it as an integer")
        elif isinstance(value, str):
            if _unstorable(value):
                return f"holds text with a NUL or an unpaired surrogate at {path}"
        elif not (value is None or isinstance(value, (bool, int))):
            return f"holds a value that is not JSON at {path}"
    if len(canonical_body(body).encode("utf-8")) > EXTRA_BODY_MAX_BYTES:
        return f"must be at most {EXTRA_BODY_MAX_BYTES} bytes as compact JSON"
    return None


def secret_path(body: Any, secrets: list[str]) -> str | None:
    """Where a string of an accepted `body` holds one of `secrets` (review F2): the path of that value, or for a key name
    the object that holds it, so the answer never repeats the string; None when no string does."""
    stack: list[tuple[Any, str]] = [(body, "")]
    while stack:
        value, path = stack.pop()
        if isinstance(value, str) and any(s in value for s in secrets):
            return path or "the top level"
        if isinstance(value, dict):
            for key, item in value.items():
                if any(s in key for s in secrets):
                    return path or "the top level"
                stack.append((item, f"{path}.{key}" if path else key))
        elif isinstance(value, list):
            stack.extend((item, f"{path}[{i}]") for i, item in enumerate(value))
    return None


def _env_extra_body() -> Any:
    """`NMOS_LLM_EXTRA_BODY` as JSON text; unset or empty (as the compose files pass an unset variable) is `{}`."""
    text = os.environ.get("NMOS_LLM_EXTRA_BODY", "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        raise ValueError("NMOS_LLM_EXTRA_BODY must be a JSON object: it is not valid JSON") from None


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("NMOS_DATABASE_URL", "postgresql://nmos:nmos@127.0.0.1:5436/nmos"))
    # Optional. Empty = no auth; set it only when the sidecar is reachable beyond loopback.
    auth_token: str = field(default_factory=lambda: os.environ.get("NMOS_AUTH_TOKEN", ""))
    # Without a token, the sidecar answers only to IP addresses, `localhost`, single-label names (`nmos`)
    # and these names (`*.example.com` covers subdomains; `*` turns the check off). ADR 0030.
    allowed_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(h.strip().lower() for h in os.environ.get("NMOS_ALLOWED_HOSTS", "").split(",") if h.strip())
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in os.environ.get("NMOS_CORS_ORIGINS", "").split(",") if o.strip())
    )
    recall_top_k: int = field(default_factory=lambda: int(os.environ.get("NMOS_RECALL_TOP_K", "5")))
    recall_threshold: float = field(default_factory=lambda: float(os.environ.get("NMOS_RECALL_THRESHOLD", "0.4")))
    large_divergence_ratio: float = field(default_factory=lambda: float(os.environ.get("NMOS_LARGE_DIVERGENCE_RATIO", "0.5")))
    # Verified append fast path (Track A, A1). "0" forces the full reconciliation path for every sync.
    append_fast_path: bool = field(default_factory=lambda: os.environ.get("NMOS_APPEND_FAST_PATH", "1") != "0")
    # Phase 2: LLM extraction (off unless NMOS_LLM_URL is set). OpenAI-compatible base URL, e.g.
    # http://host.docker.internal:11434/v1 for Ollama.
    llm_url: str = field(default_factory=lambda: os.environ.get("NMOS_LLM_URL", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("NMOS_LLM_MODEL", ""))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("NMOS_LLM_API_KEY", ""))
    llm_json_mode: bool = field(default_factory=lambda: os.environ.get("NMOS_LLM_JSON_MODE", "1") != "0")
    llm_timeout_s: float = field(default_factory=lambda: float(os.environ.get("NMOS_LLM_TIMEOUT_S", "120")))
    # PHASE-61 S1 (ADR 0088): a JSON object merged at the top level into every request to the extraction model (a
    # reasoning effort, a provider preference); `{}` sends nothing more. Part of those generations only when not empty.
    llm_extra_body: dict[str, Any] = field(default_factory=_env_extra_body, hash=False)
    # PHASE-61 S1b: send no `temperature` (for a model that refuses one); off sends `temperature: 0` as before. Off when
    # unset, empty or "0". Part of those generations (`temperature: null`) only when on.
    llm_no_temperature: bool = field(
        default_factory=lambda: os.environ.get("NMOS_LLM_NO_TEMPERATURE", "0") not in ("", "0"))
    # Previous turns an extraction sees as context (ADR 0008); part of the extractor generation.
    extract_turns: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_TURNS", "3")))
    # Known entity names shown to extraction (ADR 0012); 0 turns hints off. Part of the extractor generation.
    extract_hints: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_HINTS", "40")))
    # The extractor (PHASE-28 Q3): empty is `extraction.DEFAULT_COMPILER` (extract-v16 since 2026-10-04: it lists the roles
    # in force and ends one as listed); "extract-v15" selects the earlier extractor. Part of the extractor generation: a change re-extracts every chat once,
    # but a switch among extract-v16, extract-v18, extract-v19 and extract-v20 (PHASE-58 S3, PHASE-60 S7, PHASE-64) re-extracts nothing.
    extract_compiler: str = field(default_factory=lambda: os.environ.get("NMOS_EXTRACT_COMPILER", ""))
    # Scene summaries and the story so far (PHASE-12, ADR 0042, 0043), written by the extraction model; "0" or the
    # plugin's switch turns them off. Needs NMOS_LLM_URL.
    summaries: bool = field(default_factory=lambda: os.environ.get("NMOS_SUMMARIES", "1") != "0")
    # Canon facts (PHASE-14 Q3, ADR 0047): the extraction model reads the card, the persona, the author's note and each
    # lorebook entry a prompt held; "0" or the plugin's switch turns it off. Needs NMOS_LLM_URL.
    canon_facts: bool = field(default_factory=lambda: os.environ.get("NMOS_CANON_FACTS", "1") != "0")
    # PHASE-60 S8 (ADR 0087 item 3): `@name` in the user's message pins that character for the request. Off when unset,
    # empty (as the compose files pass an unset variable) or "0"; the plugin's switch sets it too.
    pin_at_mentions: bool = field(default_factory=lambda: os.environ.get("NMOS_PIN_AT_MENTIONS", "0") not in ("", "0"))
    # Turns extracted when NMOS first sees a chat (ADR 0008: turns, not messages).
    extract_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_BACKFILL", "100")))
    # Embeddings are cheap (local models): cover far more history on first sight than LLM extraction.
    embed_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_BACKFILL", "2000")))
    # Chunks of 700 normalized characters embedded per message, from its start (ADR 0062; K13): 8 is 5,600 characters,
    # the cap since #13, which the owner's long chats stay within once normalized (measured on the M0 copy: 5,481 at
    # most). Part of the projection key: a change re-embeds every chat once (K18); the default does not.
    embed_max_chunks: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_MAX_CHUNKS", "8")))
    # Normalized characters of each message the extraction model is shown: a TARGET-turn message of an extraction or a
    # reveal check, a message of a scene summary (PHASE-62, ADR 0090; K13). 6,000 is the cap it always was, and at it
    # every generation key is unchanged; another value is another extract, reveal and summarize generation, whose
    # activation queues nothing (`generations.classify`: `reads`). Empty reads as the default (compose files pass an
    # unset variable as empty).
    extract_target_chars: int = field(
        default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_TARGET_CHARS") or TARGET_CHARS[0]))
    worker_concurrency: int = field(default_factory=lambda: int(os.environ.get("NMOS_WORKER_CONCURRENCY", "2")))
    facts_limit: int = field(default_factory=lambda: int(os.environ.get("NMOS_FACTS_LIMIT", "8")))
    # `event` facts among them (PHASE-7 Q4): the newest events of a main character would take every slot.
    events_limit: int = field(default_factory=lambda: int(os.environ.get("NMOS_EVENTS_LIMIT", "3")))
    # Open promises in the packet (PHASE-7 Q5); 0 turns the section off.
    threads_limit: int = field(default_factory=lambda: int(os.environ.get("NMOS_THREADS_LIMIT", "3")))
    # Phase 3: embeddings (off unless NMOS_EMBED_URL is set).
    embed_url: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_URL", ""))
    embed_model: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_MODEL", ""))
    embed_api_key: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_API_KEY", ""))
    embed_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_TIMEOUT_MS", "300")))
    # PHASE-60 S5 (ADR 0084): an optional reranker, off unless both a URL and a model are set. When on, the request's
    # candidate text is sent to this endpoint, as the embedder's is. The key is a credential like the other two. An
    # empty timeout or format (as the compose files pass an unset variable) is the default.
    rerank_url: str = field(default_factory=lambda: os.environ.get("NMOS_RERANK_URL", ""))
    rerank_model: str = field(default_factory=lambda: os.environ.get("NMOS_RERANK_MODEL", ""))
    rerank_api_key: str = field(default_factory=lambda: os.environ.get("NMOS_RERANK_API_KEY", ""))
    rerank_timeout_ms: int = field(
        default_factory=lambda: int(os.environ.get("NMOS_RERANK_TIMEOUT_MS") or rerank.DEFAULT_TIMEOUT_MS))
    rerank_format: str = field(default_factory=lambda: os.environ.get("NMOS_RERANK_FORMAT") or "standard")
    # Budget for the lexical recall query; beyond it lexical abstains for that request (#12).
    lexical_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_LEXICAL_TIMEOUT_MS", "300")))
    # packet-v14: placements in a row before an unused supportive line rests (PHASE-34 Q2)
    rest_after: int = field(default_factory=lambda: int(os.environ.get("NMOS_REST_AFTER", "2")))
    vector_min_sim: float = field(default_factory=lambda: float(os.environ.get("NMOS_VECTOR_MIN_SIM", "0.42")))
    # Query-side instruction for instruction-tuned embedders. "auto": Qwen3-Embedding format when the
    # model name contains "qwen3-embedding", none otherwise. Documents are embedded without it.
    embed_query_instruction: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_QUERY_INSTRUCTION", "auto"))
    trace_retention_days: int = field(default_factory=lambda: int(os.environ.get("NMOS_TRACE_RETENTION_DAYS", "30")))
    # Packet compiler (ADR 0027, 0032, 0034, 0036, 0038, 0040, 0041, 0043, 0049, 0053, 0063, 0066, 0067, 0068, 0082).
    # Empty or unknown: `packet.DEFAULT_POLICY` (packet-v19: small talk keeps the configured fact limits; packet-v20 is
    # selectable, not the default — PHASE-60; packet-v18: explicit
    # persona questions and bounded Korean particle recall;
    # packet-v17: status history; packet-v16: named facts by words; packet-v15: content anchors;
    # packet-v14: packet-v13 that knows what each line is for — labels, and supportive memory that rests after
    # `rest_after` placements no reply used; packet-v13: packet-v12 with the quote route for
    # what was said and room for the turns extraction has not reached; packet-v12: packet-v11 that knows what changed —
    # an older excerpt of a replaced value and an ended role are left out of a question about now, an excerpt's anchor
    # breaks a tie on the question's one-character words; packet-v11: packet-v10 whose excerpt lands on the answer — a
    # word hit with a qualifying vector excerpts within its chunk, a why or contents question grows to 320 characters,
    # the question's keywords anchor the excerpt; packet-v10: packet-v9, whose excerpts grow from the sentence holding
    # most keywords by up to four sentences; packet-v9: packet-v8, whose excerpts and facts grow with the budget;
    # packet-v8: room kept for the best excerpt, Korean estimate 1.2, a <Private> section, no line that says an earlier
    # line again, what standing facts replaced, stated causes, excerpts and state numbered by turn, and summaries in
    # <Story> and each scene character's state in <Cast>); v7 … v0 are earlier. The compose files pass it empty, so a
    # pinned value cannot outlive a new default.
    packet_policy: str = field(default_factory=lambda: os.environ.get("NMOS_PACKET_POLICY", ""))
    parsers_file: str = field(default_factory=lambda: os.environ.get("NMOS_PARSERS_FILE", ""))
    # PHASE-38 Q3: the largest archive the panel may upload for a restore.
    restore_max_mb: int = field(default_factory=lambda: int(os.environ.get("NMOS_RESTORE_MAX_MB", "2048")))
    # How NMOS was installed, as the portable launcher says (`bundle`); empty for Docker and a source checkout. The
    # panel picks addresses by it: a bundle reaches the PC's own Ollama at 127.0.0.1, not host.docker.internal.
    install: str = field(default_factory=lambda: os.environ.get("NMOS_INSTALL", "").strip().lower())
    # Test hook for the "sidecar slower than deadlineMs" acceptance check. Never set in production.
    debug_delay_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_DEBUG_DELAY_MS", "0")))

    def __post_init__(self) -> None:
        # A misspelt extractor would be a generation of its own (a full re-extraction): refused at startup.
        if self.extract_compiler not in ("", "extract-v15", "extract-v16", "extract-v17", "extract-v18", "extract-v19",
                                         "extract-v20"):
            raise ValueError("NMOS_EXTRACT_COMPILER must be empty, extract-v15, extract-v16, extract-v17, extract-v18,"
                             f" extract-v19 or extract-v20, not {self.extract_compiler!r}")
        # Under 6,000 it would read less than every release did; 36,000 is past the longest reply measured, and a
        # scene summary reads 8 turns of them in one call (PHASE-62 S1b): another value is refused at startup.
        if (isinstance(self.extract_target_chars, bool) or not isinstance(self.extract_target_chars, int)
                or not TARGET_CHARS[0] <= self.extract_target_chars <= TARGET_CHARS[1]):
            raise ValueError(f"NMOS_EXTRACT_TARGET_CHARS must be a whole number from {TARGET_CHARS[0]} to"
                             f" {TARGET_CHARS[1]}, not {self.extract_target_chars!r}")
        # A cap under one would embed nothing and mark every embed job done (ADR 0062): refused at startup.
        if self.embed_max_chunks < 1:
            raise ValueError(f"NMOS_EMBED_MAX_CHUNKS must be at least 1, not {self.embed_max_chunks}")
        # A format NMOS does not speak, or a wait no reranker answers in (or one that holds the request too long).
        if self.rerank_format not in rerank.FORMATS:
            raise ValueError(f"NMOS_RERANK_FORMAT must be {' or '.join(rerank.FORMATS)}, not {self.rerank_format!r}")
        if not RERANK_TIMEOUT_MS[0] <= self.rerank_timeout_ms <= RERANK_TIMEOUT_MS[1]:
            raise ValueError(f"NMOS_RERANK_TIMEOUT_MS must be between {RERANK_TIMEOUT_MS[0]} and {RERANK_TIMEOUT_MS[1]},"
                             f" not {self.rerank_timeout_ms}")
        # A body the panel would refuse (PHASE-61 S3): the message names the setting and the reason, never the value.
        if (reason := extra_body_error(self.llm_extra_body)) is not None:
            raise ValueError(f"NMOS_LLM_EXTRA_BODY {reason}")
        if not isinstance(self.llm_no_temperature, bool):
            raise ValueError("NMOS_LLM_NO_TEMPERATURE must be a boolean")
