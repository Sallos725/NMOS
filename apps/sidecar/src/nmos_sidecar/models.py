"""HTTP API models."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, PlainValidator

from .canonical import storable

Hex64 = Field(pattern=r"^[0-9a-f]{64}$")

# Pydantic refuses a str holding a lone surrogate, which a browser sends for half an emoji (ADR 0029).
# Free text the sidecar stores or queries with has them replaced before validation.
Text = Annotated[str, BeforeValidator(storable)]
MAX_BODY_CHARS = 2_000_000


def _body_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("must be a string")
    if len(value) > MAX_BODY_CHARS:
        raise ValueError(f"must have at most {MAX_BODY_CHARS} characters")
    return value


# A message body as sent: its hash is verified on this text, then `ledger.store_bodies` makes it storable.
BodyText = Annotated[str, PlainValidator(_body_text)]


class ManifestMessage(BaseModel):
    host_logical_id: str = Field(min_length=1, max_length=200)
    revision_hash: str = Hex64
    role: Literal["user", "char"]
    name: Text | None = None
    disabled: bool | Literal["allBefore"] | None = None
    is_comment: bool | None = None
    swipe_id: int | None = None
    swipe_count: int = 0
    generation_id: str | None = None
    special_comments: list[Text] = Field(default_factory=list, max_length=8)


# Supported chat length (#12, docs/perf/scale.md): measured up to 25,000 messages; the extra room
# keeps a chat that grows past the measured tier syncing instead of failing with 422.
MAX_MANIFEST_MESSAGES = 30_000


class ReconcileRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str = Field(min_length=1, max_length=200)
    character_ref: Text | None = None
    # Display labels (the host's bot and chat names), refreshed on every sync; never identity.
    character_name: Text | None = Field(default=None, max_length=200)
    chat_name: Text | None = Field(default=None, max_length=200)
    # The user's persona name in this chat (ADR 0023): resolved as the persona, refreshed like the labels.
    persona_name: Text | None = Field(default=None, max_length=200)
    hash_version: Literal[1] = 1
    messages: list[ManifestMessage] = Field(max_length=MAX_MANIFEST_MESSAGES)


class RevisionRef(BaseModel):
    host_logical_id: str
    revision_hash: str


class ReconcileResponse(BaseModel):
    conversation_id: UUID
    status: Literal["noop", "applied", "needs_bodies"]
    active_commit: UUID | None
    manifest_hash: str
    needed_bodies: list[RevisionRef] = Field(default_factory=list)
    changes_summary: dict[str, int] = Field(default_factory=dict)
    commit_reason: str | None = None


class Body(BaseModel):
    host_logical_id: str
    revision_hash: str = Hex64
    content: BodyText
    metadata: dict[str, Any]


class BodiesRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str
    bodies: list[Body] = Field(max_length=20000)
    then_reconcile: ReconcileRequest | None = None


class BodiesResponse(BaseModel):
    ok: bool
    stored: int
    rejected: list[RevisionRef] = Field(default_factory=list)
    reconcile: ReconcileResponse | None = None


class RetrieveRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str
    active_commit: UUID | None = None
    manifest_hash: str | None = None
    query: Text = Field(max_length=200_000)
    previous_ai: Text | None = Field(default=None, max_length=200_000)
    in_context_ids: list[str] = Field(default_factory=list, max_length=20000)
    budget_tokens: int = Field(ge=0, le=20000)
    client_timings_ms: dict[str, float] = Field(default_factory=dict)


class Packet(BaseModel):
    text: str
    token_estimate: int
    excerpt_count: int


class RetrieveResponse(BaseModel):
    trace_id: UUID
    freshness: Literal["fresh", "stale", "unknown_conversation"]
    packet: Packet


class OutputRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str
    host_logical_id: str | None = None
    generation_id: str | None = None
    revision_hash: str | None = None
    message_index: int | None = None


class EntityLinkRequest(BaseModel):
    """The owner says two names of one conversation are the same entity (ADR 0025)."""
    entity_type: Literal["character", "place", "item", "group", "concept"]
    name: Text = Field(min_length=1, max_length=120)
    same_as: Text = Field(min_length=1, max_length=120)
