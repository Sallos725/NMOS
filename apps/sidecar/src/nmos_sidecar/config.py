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
    parsers_file: str = field(default_factory=lambda: os.environ.get("NMOS_PARSERS_FILE", ""))
    # Test hook for the "sidecar slower than deadlineMs" acceptance check. Never set in production.
    debug_delay_ms: int = field(default_factory=lambda: int(os.environ.get("NMOS_DEBUG_DELAY_MS", "0")))
