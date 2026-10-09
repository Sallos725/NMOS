"""Sidecar settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


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
    # Previous turns an extraction sees as context (ADR 0008); part of the extractor generation.
    extract_turns: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_TURNS", "3")))
    # Known entity names shown to extraction (ADR 0012); 0 turns hints off. Part of the extractor generation.
    extract_hints: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_HINTS", "40")))
    # The extractor (PHASE-28 Q3): empty is `extraction.DEFAULT_COMPILER` (extract-v16 since 2026-10-04: it lists the roles
    # in force and ends one as listed); "extract-v15" selects the earlier extractor. Part of the extractor generation: a change re-extracts every chat once.
    extract_compiler: str = field(default_factory=lambda: os.environ.get("NMOS_EXTRACT_COMPILER", ""))
    # Scene summaries and the story so far (PHASE-12, ADR 0042, 0043), written by the extraction model; "0" or the
    # plugin's switch turns them off. Needs NMOS_LLM_URL.
    summaries: bool = field(default_factory=lambda: os.environ.get("NMOS_SUMMARIES", "1") != "0")
    # Canon facts (PHASE-14 Q3, ADR 0047): the extraction model reads the card, the persona, the author's note and each
    # lorebook entry a prompt held; "0" or the plugin's switch turns it off. Needs NMOS_LLM_URL.
    canon_facts: bool = field(default_factory=lambda: os.environ.get("NMOS_CANON_FACTS", "1") != "0")
    # Turns extracted when NMOS first sees a chat (ADR 0008: turns, not messages).
    extract_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_BACKFILL", "100")))
    # Embeddings are cheap (local models): cover far more history on first sight than LLM extraction.
    embed_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_BACKFILL", "2000")))
    # Chunks of 700 normalized characters embedded per message, from its start (ADR 0062; K13): 8 is 5,600 characters,
    # the cap since #13, which the owner's long chats stay within once normalized (measured on the M0 copy: 5,481 at
    # most). Part of the projection key: a change re-embeds every chat once (K18); the default does not.
    embed_max_chunks: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_MAX_CHUNKS", "8")))
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
    # Budget for the lexical recall query; beyond it lexical abstains for that request (#12).
    lexical_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_LEXICAL_TIMEOUT_MS", "300")))
    # packet-v14: placements in a row before an unused supportive line rests (PHASE-34 Q2)
    rest_after: int = field(default_factory=lambda: int(os.environ.get("NMOS_REST_AFTER", "2")))
    vector_min_sim: float = field(default_factory=lambda: float(os.environ.get("NMOS_VECTOR_MIN_SIM", "0.42")))
    # Query-side instruction for instruction-tuned embedders. "auto": Qwen3-Embedding format when the
    # model name contains "qwen3-embedding", none otherwise. Documents are embedded without it.
    embed_query_instruction: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_QUERY_INSTRUCTION", "auto"))
    trace_retention_days: int = field(default_factory=lambda: int(os.environ.get("NMOS_TRACE_RETENTION_DAYS", "30")))
    # Packet compiler (ADR 0027, 0032, 0034, 0036, 0038, 0040, 0041, 0043, 0049, 0053, 0063, 0066, 0067, 0068). Empty or
    # unknown: `packet.DEFAULT_POLICY` (packet-v18: explicit persona questions and bounded Korean particle recall;
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
        if self.extract_compiler not in ("", "extract-v15", "extract-v16"):
            raise ValueError(f"NMOS_EXTRACT_COMPILER must be empty, extract-v15 or extract-v16, not {self.extract_compiler!r}")
        # A cap under one would embed nothing and mark every embed job done (ADR 0062): refused at startup.
        if self.embed_max_chunks < 1:
            raise ValueError(f"NMOS_EMBED_MAX_CHUNKS must be at least 1, not {self.embed_max_chunks}")
