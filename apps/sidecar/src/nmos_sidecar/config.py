"""Sidecar settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("NMOS_DATABASE_URL", "postgresql://nmos:nmos@127.0.0.1:5436/nmos"))
    # Optional. Empty = no auth; set it only when the sidecar is reachable beyond loopback.
    auth_token: str = field(default_factory=lambda: os.environ.get("NMOS_AUTH_TOKEN", ""))
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
    # Per-message window hash, read only by generations compiled before turns (ADR 0008).
    extract_window: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_WINDOW", "6")))
    # Previous turns an extraction sees as context (ADR 0008); part of the extractor generation.
    extract_turns: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_TURNS", "3")))
    # Known entity names shown to extraction (ADR 0012); 0 turns hints off. Part of the extractor generation.
    extract_hints: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_HINTS", "40")))
    # Turns extracted when NMOS first sees a chat (ADR 0008: turns, not messages).
    extract_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EXTRACT_BACKFILL", "100")))
    # Embeddings are cheap (local models): cover far more history on first sight than LLM extraction.
    embed_backfill: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_BACKFILL", "2000")))
    worker_concurrency: int = field(default_factory=lambda: int(os.environ.get("NMOS_WORKER_CONCURRENCY", "2")))
    facts_limit: int = field(default_factory=lambda: int(os.environ.get("NMOS_FACTS_LIMIT", "8")))
    # `event` facts among them (PHASE-7 Q4): the newest events of a main character would take every slot.
    events_limit: int = field(default_factory=lambda: int(os.environ.get("NMOS_EVENTS_LIMIT", "3")))
    # Phase 3: embeddings (off unless NMOS_EMBED_URL is set).
    embed_url: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_URL", ""))
    embed_model: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_MODEL", ""))
    embed_api_key: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_API_KEY", ""))
    embed_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_EMBED_TIMEOUT_MS", "300")))
    # Budget for the lexical recall query; beyond it lexical abstains for that request (#12).
    lexical_timeout_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_LEXICAL_TIMEOUT_MS", "300")))
    vector_min_sim: float = field(default_factory=lambda: float(os.environ.get("NMOS_VECTOR_MIN_SIM", "0.42")))
    # Query-side instruction for instruction-tuned embedders. "auto": Qwen3-Embedding format when the
    # model name contains "qwen3-embedding", none otherwise. Documents are embedded without it.
    embed_query_instruction: str = field(default_factory=lambda: os.environ.get("NMOS_EMBED_QUERY_INSTRUCTION", "auto"))
    trace_retention_days: int = field(default_factory=lambda: int(os.environ.get("NMOS_TRACE_RETENTION_DAYS", "30")))
    parsers_file: str = field(default_factory=lambda: os.environ.get("NMOS_PARSERS_FILE", ""))
    # Test hook for the "sidecar slower than deadlineMs" acceptance check. Never set in production.
    debug_delay_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_DEBUG_DELAY_MS", "0")))
