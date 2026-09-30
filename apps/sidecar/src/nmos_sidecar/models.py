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
    # The plugin's build id (ADR 0037): tells an outdated plugin. Older plugins send none.
    plugin_build: str | None = Field(default=None, max_length=40)
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


class CanonEntry(BaseModel):
    """One canon text of the chat as the host shows it (ADR 0045): its key, the hash of its text and what it is."""
    key: str = Field(pattern=r"^(card:(name|desc|personality|scenario|greeting)|note|persona|lore:[A-Za-z0-9_.:-]{1,120}(~[0-9]{1,4})?)$")
    hash: str = Hex64
    metadata: dict[str, Any] = Field(default_factory=dict)


class CanonSyncRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str
    entries: list[CanonEntry] = Field(max_length=5000)
    contents: dict[str, BodyText] = Field(default_factory=dict, max_length=5000)  # hash -> text the sidecar asked for
    observed_at: int | None = Field(default=None, ge=0)  # when the plugin read this canon (ms since the epoch)


class CanonSyncResponse(BaseModel):
    needed: list[str] = Field(default_factory=list)
    stored: int = 0
    applied: bool = False  # this manifest became the conversation's canon
    stale: bool = False  # a newer observation is in force: not applied
    manifest_id: str | None = None
    in_force: int | None = None


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
    canon_manifest_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")  # the canon this prompt was built with
    canon_held: list[str] = Field(default_factory=list, max_length=5000)  # canon keys this prompt holds (ADR 0045)


class Packet(BaseModel):
    text: str
    token_estimate: int
    excerpt_count: int


class MemoryFit(BaseModel):
    """How much memory the budget held (ADR 0036): memory lines offered (state, promises, facts, claims),
    those left out for the budget, and the smallest budget in 100s up to `packet.FIT_CAP` that holds them all (None:
    nothing left out, or more than FIT_CAP needed)."""
    offered: int
    cut: int
    fits_at: int | None = None


class RetrieveResponse(BaseModel):
    trace_id: UUID
    freshness: Literal["fresh", "stale", "unknown_conversation"]
    packet: Packet
    memory: MemoryFit | None = None
    # Whether vector search ran (PHASE-15 Q5, K34): "on", "off" (no embedder, or nothing to search), or "fallback" (the
    # embedder failed or did not answer in time, so recall was lexical only). None: not recalled (stale or unknown).
    vectors: Literal["on", "off", "fallback"] | None = None


class OutputRequest(BaseModel):
    host: Literal["pocketrisu"] = "pocketrisu"
    chat_id: str
    host_logical_id: str | None = None
    generation_id: str | None = None
    revision_hash: str | None = None
    message_index: int | None = None


class MemoryModeRequest(BaseModel):
    """This chat's memory mode (ADR 0035): strict withholding, and a first-person narrator (None: none)."""
    strict: bool = False
    narrator: Text | None = Field(default=None, max_length=60)


class RepairRequest(BaseModel):
    """The owner repairs one item of a conversation's memory (ADR 0044): the id the Inspector shows for a thread, a
    secret or a fact (for a name split, a name of the entity), what to do, and what the kind needs: a close's outcome,
    a secret's character, a correction's new object or value, a split's other name, and the turn it takes effect.
    `fact_lock` keeps a canon fact or a correction current against the story (ADR 0047)."""
    kind: Literal["thread_close", "thread_reopen", "secret_found_out", "secret_keep", "fact_retract", "fact_correct",
                  "name_split", "fact_lock"]
    item: Text = Field(min_length=1, max_length=120)
    outcome: Text | None = Field(default=None, max_length=32)
    character: Text | None = Field(default=None, max_length=120)
    turn: int | None = Field(default=None, ge=0)
    note: Text | None = Field(default=None, max_length=300)
    new_object: Text | None = Field(default=None, max_length=200)
    new_value: Text | None = Field(default=None, max_length=500)
    other: Text | None = Field(default=None, max_length=120)
    entity_type: Literal["character", "place", "item", "group", "concept"] = "character"
    expect: str | None = Field(default=None, max_length=64)  # a split's preview fingerprint (PHASE-20 Q4)


class EntityLinkRequest(BaseModel):
    """The owner says two names of one conversation are the same entity (ADR 0025)."""
    entity_type: Literal["character", "place", "item", "group", "concept"]
    name: Text = Field(min_length=1, max_length=120)
    same_as: Text = Field(min_length=1, max_length=120)
    expect: str | None = Field(default=None, max_length=64)  # the preview's fingerprint (PHASE-20 Q4)


class ExpectRequest(BaseModel):
    """An undo of a join or a split, made from its preview (PHASE-20 Q4): the preview's fingerprint."""
    expect: str | None = Field(default=None, max_length=64)
