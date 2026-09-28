"""HTTP API. Handlers translate requests; ledger/reconcile/retrieval own the logic."""

from __future__ import annotations

import hmac
import logging
import time
import dataclasses
import ipaddress
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import (__version__, audit, canon, canonfacts, extraction, generations, inspector, ledger, normtext, plugin,
               readmodel, retention, repairs, runtime, summaries, vectors)
from .config import Settings
from .db import make_pool
from .extraction import enqueue_after_apply, job_counts
from .facts import STANDING, memory_view, version_key
from .ids import uuid7
from .models import (
    BodiesRequest,
    BodiesResponse,
    CanonSyncRequest, CanonSyncResponse,
    EntityLinkRequest, MemoryModeRequest, RepairRequest,
    OutputRequest,
    Packet,
    ReconcileRequest,
    ReconcileResponse,
    RetrieveRequest,
    RetrieveResponse,
    RevisionRef,
)
from .canonical import manifest_hash, manifest_hashes, storable
from .reconcile import Entry, plan, plan_append
from .llm import Embedder
from .packet import DEFAULT_POLICY, POLICIES
from .retrieval import RecallOptions, query_prefix, retrieve
from .state import current_state, rebuild_state, sync_rules, write_state

log = logging.getLogger("nmos.sidecar")


def _entries(request: ReconcileRequest, start: int = 0) -> list[Entry]:
    return [
        Entry(
            host_logical_id=m.host_logical_id,
            revision_hash=m.revision_hash,
            role=m.role,
            disabled=m.disabled,
            is_comment=m.is_comment,
            swipe_id=m.swipe_id,
            swipe_count=m.swipe_count,
            generation_id=m.generation_id,
            special_comments=tuple(m.special_comments),
        )
        for m in request.messages[start:]
    ]


def _compact_observation(body: ReconcileRequest, result, base_hash: str | None, base_len: int) -> dict:
    """Host manifest as observed: every entry when a commit is created, only the appended tail otherwise."""
    appended = result.commit_reason is None
    rows = [[m.host_logical_id, m.revision_hash, m.role, m.disabled, m.is_comment, m.swipe_id, m.swipe_count,
             m.generation_id, m.special_comments or None] for m in body.messages[base_len if appended else 0:]]
    columns = ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count",
               "generation_id", "special_comments"]
    if appended:
        return {"chat_id": body.chat_id, "columns": columns, "base_manifest_hash": base_hash, "appended": rows}
    return {"chat_id": body.chat_id, "columns": columns, "entries": rows}


_TOKEN_QUERY = re.compile(r"([?&]token=)[^&#]*")


class RedactToken(logging.Filter):
    """Masks `token=` in uvicorn's access log (audit A-11): a standalone inspector link carries it."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], _TOKEN_QUERY.sub(r"\1***", args[2]), *args[3:])
        return True


def host_allowed(header: str, allowed: tuple[str, ...]) -> bool:
    """Whether a tokenless sidecar answers a request for this Host (ADR 0030). A DNS-rebinding page can
    only send its own domain name, so addresses, `localhost` and single-label names are safe."""
    host = header.strip().lower()
    if host.startswith("["):  # IPv6 literal, with or without a port
        return host.find("]") > 1
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if host == "localhost" or "." not in host or "*" in allowed:
        return True
    return any(host == a or (a.startswith("*.") and host.endswith(a[1:])) for a in allowed)


def create_app(settings: Settings | None = None, pool: ConnectionPool | None = None,
               embedder: Embedder | None = None) -> FastAPI:
    settings = settings or Settings()

    # Runtime-editable part (plugin settings UI): effective settings, parser rules, recall options.
    rt: dict[str, Any] = {}

    def rebuild(overrides: dict[str, Any]) -> None:
        cur = runtime.effective(settings, overrides)
        rules = runtime.ruleset(settings, overrides)
        emb = embedder or (Embedder(cur.embed_url, cur.embed_model, cur.embed_api_key)
                           if cur.embed_url and cur.embed_model else None)
        pj = vectors.projection(cur)
        sm = summaries.summarizer(cur)
        rt.update(settings=cur, rules=rules, overrides=overrides, extractor=extraction.extractor(cur), projection=pj,
                  summarizer=sm, canon=canonfacts.generation(cur),
                  recall=RecallOptions(
            top_k=cur.recall_top_k, threshold=cur.recall_threshold, rules_version=rules.version,
            facts_limit=cur.facts_limit, events_limit=cur.events_limit,
            threads_limit=cur.threads_limit, embedder=emb if pj else None, embed_projection=pj.key if pj else "",
            extractor_key=rt.get("active_extractor"), embed_timeout_ms=cur.embed_timeout_ms,
            lexical_timeout_ms=cur.lexical_timeout_ms,
            vector_min_sim=cur.vector_min_sim, query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction),
            policy=cur.packet_policy if cur.packet_policy in POLICIES else DEFAULT_POLICY,
            summarize_key=sm.key if sm else None, canon_key=rt.get("active_canon") if cur.canon_facts else None,
        ))

    def activate(conn, before_extractor: str | None, before_projection: str | None,
                 before_summarizer: str | None = None, before_canon: str | None = None) -> int:
        """Make the configured generations active and queue what they are missing (D20, #8).

        Runs at startup (idempotent: only missing work is queued) and whenever a setting changed a
        generation key. An API-key-only change keeps the keys, so nothing is re-derived. A provider
        that is off gets no further jobs started, in the same transaction as the settings save (#18).
        """
        cur = rt["settings"]
        queued = 0
        ex, pj = rt["extractor"], rt["projection"]
        if ex is None:
            if retired := extraction.retire(conn, "extract"):
                log.info("LLM extraction is off: %d queued extract jobs made obsolete", retired)
        elif ex.key != before_extractor:
            generations.activate(conn, ex)
            queued += extraction.schedule_generation(conn, ex.key, cur.extract_backfill)
        if pj is None:
            if retired := extraction.retire(conn, "embed"):
                log.info("embeddings are off: %d queued embed jobs made obsolete", retired)
        elif pj.key != before_projection:
            # Vectors from before projections existed (migration 0008: 'legacy:<model>') recorded no
            # endpoint, so their space is unknown: they stay for audit and are never searched. The
            # revisions they covered are re-embedded at background priority (#17).
            generations.activate(conn, pj)
            queued += vectors.schedule_projection(conn, pj.key, cur.embed_backfill)
        sm = rt["summarizer"]
        if sm is None:
            if retired := extraction.retire(conn, "summarize"):
                log.info("summaries are off: %d queued summarize jobs made obsolete", retired)
        elif sm.key != before_summarizer:
            generations.activate(conn, sm)
            queued += summaries.schedule_all(conn, sm.key)  # every chat's due windows, oldest first (PHASE-12 Q7)
        cg = rt["canon"]
        if cg is None:
            if retired := extraction.retire(conn, "canon"):
                log.info("canon facts are off: %d queued canon jobs made obsolete", retired)
        elif cg.key != before_canon:
            generations.activate(conn, cg)
            queued += canonfacts.schedule(conn, cg.key)  # every chat's canon in force (ADR 0047)
        rt["active_extractor"] = generations.active(conn, "extract")
        rt["active_summarizer"] = generations.active(conn, "summarize")
        # Off means none read or made (the panel's switch), as for summaries.
        rt["active_canon"] = generations.active(conn, "canon") if cg is not None else None
        rt["recall"] = dataclasses.replace(rt["recall"], extractor_key=rt["active_extractor"],
                                           canon_key=rt["active_canon"])
        return queued

    rebuild({})

    def view_of(conn, head: UUID) -> dict[str, Any]:
        """The chat's memory now (ADR 0013), with its canon facts while they are on (ADR 0047)."""
        return memory_view(conn, head, rt["active_extractor"], canon_key=rt.get("active_canon"))

    held_seen: dict[tuple[UUID, str | None], frozenset[str]] = {}  # canon keys a prompt held, already scheduled

    def schedule_held(conv_id: UUID, manifest_id: str | None, held: frozenset[str]) -> None:
        """After a request's answer (off its path): read the lorebook entries its prompt held for the first time (Q3)."""
        cg = rt["canon"]
        if cg is None:
            return
        try:
            with app.state.pool.connection() as conn:
                queued = canonfacts.schedule(conn, cg.key, conv_id)
        except psycopg.Error as exc:
            log.warning("canon jobs not queued conversation=%s: %s", conv_id, exc)
            return
        if len(held_seen) > 1000:
            held_seen.clear()
        held_seen[(conv_id, manifest_id)] = held_seen.get((conv_id, manifest_id), frozenset()) | held
        if queued:
            log.info("canon jobs queued conversation=%s jobs=%d", conv_id, queued)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Each startup step commits on its own, the batched backfills batch by batch, so a restart during
        # a long backfill resumes it instead of starting over (audit A-08).
        with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as conn:
            rebuild(runtime.stored(conn))
            normalized = normtext.backfill(conn)
            if normalized:
                log.info("normalized text written for %d revisions (%s)", normalized, normtext.NORMALIZER_VERSION)
            if pruned := retention.prune_text(conn):
                log.info("normalized text of older normalizers pruned: %d rows (ADR 0015)", pruned)
            if turned := ledger.refresh_turns(conn, settings.extract_turns):
                log.info("turn data written for %d head members (K=%d)", turned, settings.extract_turns)
            with conn.transaction():  # drop other rule versions and backfill as one: a partial backfill looks done
                backfilled = sync_rules(conn, rt["rules"])
            with conn.transaction():  # a generation becomes active together with the jobs it is missing
                queued = activate(conn, None, None, None, None)
            log.info("generations: extract=%s embed=%s summarize=%s; queued %d missing jobs",
                     rt["active_extractor"], rt["projection"].key if rt["projection"] else None,
                     rt["summarizer"].key if rt["summarizer"] else None, queued)
        app.state.pool = pool or make_pool(settings.database_url)
        if backfilled:
            log.info("state backfilled: %d observations for rules %s", backfilled, rt["rules"].version)
        try:
            yield
        finally:
            if pool is None:
                app.state.pool.close()

    app = FastAPI(title="NMOS sidecar", version=__version__, lifespan=lifespan)
    plugins = plugin.Seen()  # plugin builds that synced lately (ADR 0037)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT"],  # PUT: settings panel saves /v1/config directly
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # As FastAPI's default, but an echoed lone surrogate would make the 422 itself a 500 (ADR 0029).
        return JSONResponse(status_code=422, content={"detail": storable(jsonable_encoder(exc.errors()))})

    if not settings.auth_token:
        refused: set[str] = set()

        @app.middleware("http")
        async def check_host(request: Request, call_next):
            host = request.headers.get("host", "")
            if host_allowed(host, settings.allowed_hosts):
                return await call_next(request)
            if host not in refused:
                refused.add(host)
                log.warning("refused a request for host %r: add it to NMOS_ALLOWED_HOSTS or set NMOS_AUTH_TOKEN", host)
            return JSONResponse(status_code=400, content={
                "detail": f"host {host!r} not allowed without a token: add it to NMOS_ALLOWED_HOSTS or set NMOS_AUTH_TOKEN"})

    def auth(authorization: str | None = Header(default=None), token: str | None = None) -> None:
        if not settings.auth_token:
            return  # optional (default): the sidecar binds to loopback unless configured otherwise
        expected = f"Bearer {settings.auth_token}"
        given = authorization or (f"Bearer {token}" if token else "")
        if not hmac.compare_digest(given.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="unauthorized")

    def delay() -> None:
        if settings.debug_delay_ms > 0:
            time.sleep(settings.debug_delay_ms / 1000)

    @app.middleware("http")
    async def trace_ids(request: Request, call_next):
        trace_id = request.headers.get("x-nmos-trace") or str(uuid7())
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-nmos-trace"] = trace_id
        log.info("trace_id=%s %s %s %s %.1fms", trace_id, request.method, request.url.path,
                 response.status_code, (time.perf_counter() - started) * 1000)
        return response

    def enqueue(conn, conv_id, old_head, old_lifecycle, manifest, new_lifecycle, ids) -> None:
        cur = rt["settings"]
        if rt["extractor"] or rt["projection"]:
            enqueue_after_apply(conn, conv_id, old_head, old_lifecycle, manifest, new_lifecycle, ids,
                                settings.extract_turns, cur.extract_backfill,
                                extractor_key=rt["extractor"].key if rt["extractor"] else None,
                                embed_key=rt["projection"].key if rt["projection"] else None,
                                embed_backfill=cur.embed_backfill)

    def summarize_after(conn, conv_id, head, since: int | None) -> None:
        """Queue the windows this sync made due (an append from position `since`), or every window missing a summary
        (any other commit)."""
        if rt["summarizer"]:
            summaries.schedule(conn, conv_id, head, rt["summarizer"].key, full=since is None, since=since)

    def append_reconcile(conn, conv, body: ReconcileRequest) -> ReconcileResponse | None:
        """Verified append fast path (Track A, A1): None means "not provably an append", and the caller
        runs the full path. Every check here only decides between the two paths; results are equal."""
        length = ledger.head_length(conn, conv.head_commit_id)
        messages = body.messages
        if length == 0 or len(messages) < length:
            return None
        keys = [(m.host_logical_id, m.revision_hash) for m in messages]
        if len(messages) == length:
            if manifest_hash(keys) != conv.head_manifest_hash:
                return None
            return ReconcileResponse(conversation_id=conv.id, status="noop", active_commit=conv.head_commit_id,
                                     manifest_hash=conv.head_manifest_hash)
        prefix_hash, full_hash = manifest_hashes(keys, length)
        if prefix_hash != conv.head_manifest_hash:
            return None
        suffix = keys[length:]
        ids = [k[0] for k in suffix]
        if len(set(ids)) != len(ids) or any(m.disabled == "allBefore" for m in messages[length:]):
            return None
        stored, in_head = ledger.revisions_of(conn, conv, ids)
        if in_head:
            return None
        needed = list(dict.fromkeys(k for k in suffix if k not in stored))
        if needed:
            return ReconcileResponse(
                conversation_id=conv.id, status="needs_bodies", active_commit=None, manifest_hash=full_hash,
                needed_bodies=[RevisionRef(host_logical_id=k[0], revision_hash=k[1]) for k in needed],
            )
        tail = ledger.load_tail(conn, conv, length, settings.extract_turns)
        if tail is None:
            return None
        entries = _entries(body, tail.start)
        lifecycle = {**tail.lifecycle, **{k: stored[k][0] for k in suffix}}
        revision_ids = {**tail.revision_ids, **{k: stored[k][1] for k in suffix}}
        result = plan_append(tail.start, tail.entries, entries, full_hash, lifecycle)
        observation = ledger.record_observation(
            conn, conv.id, "manifest", full_hash, _compact_observation(body, result, conv.head_manifest_hash, length),
            f"{conv.id}:{full_hash}:manifest",
        )
        head = ledger.apply_append(conn, conv, tail, result, observation, entries, revision_ids,
                                   settings.extract_turns)
        # From the tail's first turn on is enough: lifecycle and turn hashes change only there.
        offset = tail.turn_start - tail.start
        enqueue(conn, conv.id, tail.entries[offset:], lifecycle, entries[offset:], {**lifecycle, **result.lifecycle},
                revision_ids)
        summarize_after(conn, conv.id, head, since=length)
        return ReconcileResponse(conversation_id=conv.id, status="applied", active_commit=head,
                                 manifest_hash=full_hash, changes_summary=result.summary, commit_reason=None)

    def do_reconcile(conn, body: ReconcileRequest) -> ReconcileResponse:
        plugins.saw(body.plugin_build)
        conv = ledger.lock_conversation(conn, body.host, body.chat_id, body.character_ref, body.character_name,
                                        body.chat_name, body.persona_name)
        if settings.append_fast_path and conv.head_commit_id is not None:
            fast = append_reconcile(conn, conv, body)
            if fast is not None:
                return fast
        state = ledger.load_state(conn, conv)
        manifest = _entries(body)
        result = plan(state.head, conv.head_manifest_hash, manifest, state.known, state.lifecycle,
                      settings.large_divergence_ratio)
        if result.kind == "noop":
            return ReconcileResponse(conversation_id=conv.id, status="noop", active_commit=conv.head_commit_id,
                                     manifest_hash=result.manifest_hash)
        if result.kind == "needs_bodies":
            return ReconcileResponse(
                conversation_id=conv.id, status="needs_bodies", active_commit=None, manifest_hash=result.manifest_hash,
                needed_bodies=[RevisionRef(host_logical_id=k[0], revision_hash=k[1]) for k in result.needed],
            )
        observation = ledger.record_observation(
            conn, conv.id, "manifest", result.manifest_hash,
            _compact_observation(body, result, conv.head_manifest_hash, len(state.head or [])),
            f"{conv.id}:{result.manifest_hash}:manifest",
        )
        head = ledger.apply_plan(conn, conv, state, result, observation, manifest, settings.extract_turns)
        enqueue(conn, conv.id, state.head, state.lifecycle, manifest, {**state.lifecycle, **result.lifecycle},
                state.revision_ids)
        summarize_after(conn, conv.id, head, since=len(state.head or []) if result.commit_reason is None else None)
        return ReconcileResponse(conversation_id=conv.id, status="applied", active_commit=head,
                                 manifest_hash=result.manifest_hash, changes_summary=result.summary,
                                 commit_reason=result.commit_reason)

    @app.get("/v1/health", dependencies=[Depends(auth)])
    def health(request: Request):
        with request.app.state.pool.connection() as conn:
            conn.execute("SELECT 1")
        return {"ok": True, "service": "nmos-sidecar", "version": __version__,
                "features": {"state": bool(rt["rules"].rules),
                             "extraction": bool(rt["settings"].llm_url and rt["settings"].llm_model),
                             "vectors": rt["recall"].embedder is not None},
                "generations": {"extract": rt["active_extractor"],
                                "embed": rt["projection"].key if rt["projection"] else None},
                "plugin": {"expected": plugin.expected(), "seen": plugins.recent()}}

    @app.get(f"/v1/plugin/{plugin.FILENAME}", dependencies=[Depends(auth)])
    def plugin_download():
        """The plugin file of this sidecar's build (ADR 0037), to install when the one in use differs."""
        path = plugin.plugin_file()
        if path is None:
            raise HTTPException(status_code=404, detail="this sidecar ships no plugin file")
        return FileResponse(path, media_type="application/javascript", filename=plugin.FILENAME)

    @app.post("/v1/sync/reconcile", response_model=ReconcileResponse, dependencies=[Depends(auth)])
    def reconcile(body: ReconcileRequest, request: Request):
        delay()
        with request.app.state.pool.connection() as conn:
            return do_reconcile(conn, body)

    @app.post("/v1/sync/bodies", response_model=BodiesResponse, dependencies=[Depends(auth)])
    def bodies(body: BodiesRequest, request: Request):
        with request.app.state.pool.connection() as conn:
            conv = ledger.lock_conversation(conn, body.host, body.chat_id, None)
            def derive(rid: UUID, content: str, meta: dict[str, Any]) -> None:
                normtext.write(conn, rid, content)
                write_state(conn, rt["rules"], conv.id, rid, content, meta)

            stored, rejected = ledger.store_bodies(conn, conv.id, [b.model_dump() for b in body.bodies],
                                                   on_insert=derive)
            result = None
            if body.then_reconcile is not None and not rejected:
                if body.then_reconcile.chat_id != body.chat_id:
                    raise HTTPException(status_code=422, detail="then_reconcile.chat_id mismatch")
                result = do_reconcile(conn, body.then_reconcile)
        return BodiesResponse(ok=not rejected, stored=stored,
                              rejected=[RevisionRef(host_logical_id=k[0], revision_hash=k[1]) for k in rejected],
                              reconcile=result)

    @app.post("/v1/sync/canon", response_model=CanonSyncResponse, dependencies=[Depends(auth)])
    def sync_canon(body: CanonSyncRequest, request: Request):
        """The chat's canon as the host shows it (ADR 0045): the manifest of keys and hashes, and the texts the sidecar
        asked for. Answers the hashes it still needs; the canon in force changes only once it has them all."""
        with request.app.state.pool.connection() as conn, conn.transaction():
            conv = ledger.find_conversation(conn, body.host, body.chat_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            conn.execute("SELECT 1 FROM conversation WHERE id = %s FOR UPDATE", (conv.id,))
            observed = (datetime.fromtimestamp(body.observed_at / 1000, tz=timezone.utc)
                        if body.observed_at is not None else None)
            try:
                out = canon.sync(conn, conv.id, [e.model_dump() for e in body.entries], dict(body.contents), observed)
            except canon.CanonError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
        log.info("canon sync conversation=%s entries=%d needed=%d stored=%d applied=%s stale=%s", conv.id,
                 len(body.entries), len(out["needed"]), out["stored"], out["applied"], out.get("stale"))
        if out["applied"] and rt["canon"] is not None:  # the canon in force changed: read what it has not (ADR 0047)
            with request.app.state.pool.connection() as conn:
                if queued := canonfacts.schedule(conn, rt["canon"].key, conv.id):
                    log.info("canon jobs queued conversation=%s jobs=%d", conv.id, queued)
        return out

    @app.post("/v1/retrieve", response_model=RetrieveResponse, dependencies=[Depends(auth)])
    def retrieve_route(body: RetrieveRequest, request: Request, background: BackgroundTasks):
        delay()
        with request.app.state.pool.connection() as conn:
            out = retrieve(conn, body, rt["recall"])
        lore = frozenset(k for k in body.canon_held if k.startswith("lore:"))
        conv_id = out.get("conversation_id")
        if lore and conv_id is not None and rt["canon"] is not None and \
                not lore <= held_seen.get((conv_id, body.canon_manifest_id), frozenset()):
            background.add_task(schedule_held, conv_id, body.canon_manifest_id, lore)
        return RetrieveResponse(
            trace_id=out["trace_id"] or uuid7(),
            freshness=out["freshness"],
            packet=Packet(text=out["text"], token_estimate=out["tokens"], excerpt_count=out["count"]),
            memory=out.get("memory"),
        )

    @app.post("/v1/output", status_code=202, dependencies=[Depends(auth)])
    def output(body: OutputRequest, request: Request):
        # Provisional hint only (H7): the next request snapshot is authoritative.
        with request.app.state.pool.connection() as conn:
            conv = ledger.lock_conversation(conn, body.host, body.chat_id, None)
            key = f"{conv.id}:{body.host_logical_id}:{body.generation_id}:{body.revision_hash}:output"
            ledger.record_observation(conn, conv.id, "output", None, body.model_dump(mode="json"), key)
        return JSONResponse(status_code=202, content={"accepted": True})

    @app.get("/v1/trace/{trace_id}", dependencies=[Depends(auth)])
    def trace(trace_id: UUID, request: Request):
        with request.app.state.pool.connection() as conn:
            row = conn.execute(
                "SELECT t.*, c.host_chat_ref FROM retrieval_trace t JOIN conversation c ON c.id = t.conversation_id"
                " WHERE t.id = %s",
                (trace_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return row

    @app.get("/v1/trace/{trace_id}/audit", dependencies=[Depends(auth)])
    def trace_audit(trace_id: UUID, request: Request):
        """The packet ledger of a request with each line's echo in the reply that followed (ADR 0027)."""
        with request.app.state.pool.connection() as conn:
            out = audit.audit(conn, trace_id)
        if out is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return out

    @app.get("/v1/trace/{trace_id}/replay", dependencies=[Depends(auth)])
    def trace_replay(trace_id: UUID, request: Request, policy: str | None = None):
        """The request compiled again as of its time, by its own or another packet policy. Read-only."""
        if policy is not None and policy not in POLICIES:
            raise HTTPException(status_code=422, detail=f"policy must be one of {', '.join(POLICIES)}")
        with request.app.state.pool.connection() as conn:
            out = audit.replay(conn, trace_id, rt["recall"], policy)
        if out is None:
            raise HTTPException(status_code=404, detail="trace not found")
        return out

    @app.get("/v1/conversations", dependencies=[Depends(auth)])
    def conversations(request: Request):
        with request.app.state.pool.connection() as conn:
            return readmodel.list_conversations(conn)

    @app.get("/v1/conversations/{conv_id}/state", dependencies=[Depends(auth)])
    def conversation_state(conv_id: UUID, request: Request):
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            return current_state(conn, conv["head_commit_id"], rt["rules"].version) if conv["head_commit_id"] else []

    @app.get("/v1/conversations/{conv_id}/traces", dependencies=[Depends(auth)])
    def conversation_traces(conv_id: UUID, request: Request, limit: int = 30):
        with request.app.state.pool.connection() as conn:
            return readmodel.traces(conn, conv_id, min(limit, 200))

    @app.get("/v1/conversations/{conv_id}/facts", dependencies=[Depends(auth)])
    def conversation_facts(conv_id: UUID, request: Request, history: bool = False):
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            facts = view_of(conn, conv["head_commit_id"])["facts"] if conv["head_commit_id"] else []
        return [{k: v for k, v in f.items() if history or k != "history"} for f in facts]

    @app.get("/v1/conversations/{conv_id}/entities", dependencies=[Depends(auth)])
    def conversation_entities(conv_id: UUID, request: Request):
        """Read-time entities of this chat's head (ADR 0012): names, mentions, where aliases were stated."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            view = (view_of(conn, conv["head_commit_id"])
                    if conv["head_commit_id"] else {"entities": []})
        return view["entities"]

    @app.get("/v1/conversations/{conv_id}/memory-mode", dependencies=[Depends(auth)])
    def get_memory_mode(conv_id: UUID, request: Request):
        """This chat's memory mode (ADR 0035), and the characters a narrator can be chosen from."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            names: list[str] = []
            if conv["head_commit_id"] is not None:
                r = view_of(conn, conv["head_commit_id"])["resolution"]
                names = [e["name"] for e in (r.entities() if r else []) if e["type"] == "character" and not e.get("persona")]
            return {"strict": conv["memory_strict"], "narrator": conv["memory_narrator"], "characters": names}

    @app.put("/v1/conversations/{conv_id}/memory-mode", dependencies=[Depends(auth)])
    def put_memory_mode(conv_id: UUID, body: MemoryModeRequest, request: Request):
        """Set this chat's memory mode (ADR 0035): owner input, read by every request of the chat from then on
        and recorded with each trace."""
        narrator = (body.narrator or "").strip() or None
        with request.app.state.pool.connection() as conn, conn.transaction():
            row = conn.execute("UPDATE conversation SET memory_strict = %s, memory_narrator = %s WHERE id = %s"
                               " RETURNING memory_strict, memory_narrator", (body.strict, narrator, conv_id)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="conversation not found")
        log.info("memory mode conversation=%s strict=%s narrator=%s", conv_id, row["memory_strict"],
                 "set" if row["memory_narrator"] else "none")
        return {"strict": row["memory_strict"], "narrator": row["memory_narrator"]}

    @app.post("/v1/conversations/{conv_id}/entity-links", dependencies=[Depends(auth)])
    def add_entity_link(conv_id: UUID, body: EntityLinkRequest, request: Request):
        """The owner says two names of this chat are one entity (ADR 0025). Both must be mentioned on the
        head now, with that type. The link joins them on every read until the owner removes it."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            r = view_of(conn, conv["head_commit_id"])["resolution"]
            if r is None or any(r.status(body.entity_type, n) == "unresolved" for n in (body.name, body.same_as)):
                raise HTTPException(status_code=422, detail="both names must be mentioned in this chat")
            if r.node(body.entity_type, body.name) == r.node(body.entity_type, body.same_as):
                raise HTTPException(status_code=422, detail="the two names are the same")
            with conn.transaction():
                link = conn.execute(
                    "INSERT INTO entity_link (id, conversation_id, entity_type, name, same_as) VALUES (%s, %s, %s, %s, %s)"
                    " RETURNING id, entity_type, name, same_as, created_at",
                    (uuid7(), conv_id, body.entity_type, body.name.strip(), body.same_as.strip())).fetchone()
            log.info("entity link conversation=%s link=%s", conv_id, link["id"])
            entity = view_of(conn, conv["head_commit_id"])["resolution"].entity(
                body.entity_type, body.name)
            return {"link": link, "entity": entity}

    @app.post("/v1/conversations/{conv_id}/entity-links/{link_id}/remove", dependencies=[Depends(auth)])
    def remove_entity_link(conv_id: UUID, link_id: UUID, request: Request):
        """The owner takes a link back (ADR 0025): the next read resolves the names as the story alone
        does. The row stays with `removed_at` for audit."""
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                n = conn.execute("UPDATE entity_link SET removed_at = now() WHERE id = %s AND conversation_id = %s"
                                 " AND removed_at IS NULL", (link_id, conv_id)).rowcount
        if not n:
            raise HTTPException(status_code=404, detail="link not found")
        log.info("entity link removed conversation=%s link=%s", conv_id, link_id)
        return {"removed": str(link_id)}

    def repair_rows(conn, conv_id: UUID, live: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Every repair of a chat, newest first, with the item each in force applies to now (ADR 0044)."""
        applied = {str(x["id"]): x["applied"] for x in live}
        rows = conn.execute("SELECT id, kind, target, value, note, created_at, removed_at FROM owner_repair"
                            " WHERE conversation_id = %s ORDER BY created_at DESC, id DESC", (conv_id,)).fetchall()
        return [{**row, "applied": applied.get(str(row["id"]))} for row in rows]

    def head_turn(conn, head: UUID) -> int | None:
        return conn.execute("SELECT max(turn) AS t FROM active_membership WHERE commit_id = %s", (head,)).fetchone()["t"]

    def items_of(conv_id: UUID, request: Request, key: str) -> list[dict[str, Any]]:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if conv["head_commit_id"] is None:
                return []
            return view_of(conn, conv["head_commit_id"])[key]

    @app.get("/v1/conversations/{conv_id}/threads", dependencies=[Depends(auth)])
    def conversation_threads(conv_id: UUID, request: Request):
        """This chat's threads, newest first (ADR 0019, 0039), with the `id` a repair names (ADR 0044)."""
        return [{k: t.get(k) for k in ("id", "kind", "by", "to", "text", "turn", "status", "closed_by", "restated",
                                       "repair")} for t in items_of(conv_id, request, "threads")]

    @app.get("/v1/conversations/{conv_id}/secrets", dependencies=[Depends(auth)])
    def conversation_secrets(conv_id: UUID, request: Request):
        """This chat's secrets, newest first (ADR 0033): who keeps each from whom, who found it out, and the `id` a
        repair names (ADR 0044)."""
        return [{k: s.get(k) for k in ("id", "text", "turn", "holders", "kept_from", "open", "ended", "repair")}
                for s in items_of(conv_id, request, "secrets")]

    @app.get("/v1/conversations/{conv_id}/repairs", dependencies=[Depends(auth)])
    def list_repairs(conv_id: UUID, request: Request):
        """The owner's repairs of this chat (ADR 0044), newest first: each in force with the item it applies to now
        (None when it matches nothing), and those taken back, with `removed_at`."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            view = view_of(conn, conv["head_commit_id"])
            return {"repairs": repair_rows(conn, conv_id, view["repairs"])}

    @app.post("/v1/conversations/{conv_id}/repairs", dependencies=[Depends(auth)])
    def add_repair(conv_id: UUID, body: RepairRequest, request: Request):
        """The owner repairs one item of this chat's memory (ADR 0044): `item` is the id the Inspector shows for a
        thread or a secret. The repair stores what the item says, not the id, so it survives rebuilds and new
        extractor generations; it applies on every read until the owner takes it back."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            try:
                target, value = repairs.plan(body.kind, body.item, view_of(conn, head),
                                             head_turn(conn, head), body.outcome, body.character, body.turn,
                                             body.new_object, body.new_value, body.other, body.entity_type,
                                             version_key)
            except repairs.RepairError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO owner_repair (id, conversation_id, kind, target, value, note) VALUES (%s, %s, %s, %s, %s, %s)"
                    " RETURNING id, kind, target, value, note, created_at",
                    (uuid7(), conv_id, body.kind, Jsonb(target), Jsonb(value), (body.note or "").strip() or None)).fetchone()
            applied = next((x["applied"] for x in view_of(conn, head)["repairs"]
                            if x["id"] == row["id"]), None)
        log.info("owner repair conversation=%s repair=%s kind=%s applied=%s", conv_id, row["id"], body.kind,
                 applied is not None)
        return {"repair": row, "applied": applied}

    @app.post("/v1/conversations/{conv_id}/repairs/{repair_id}/remove", dependencies=[Depends(auth)])
    def remove_repair(conv_id: UUID, repair_id: UUID, request: Request):
        """The owner takes a repair back (ADR 0044): the next read is as the story alone says. The row stays with
        `removed_at` for audit."""
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                n = conn.execute("UPDATE owner_repair SET removed_at = now() WHERE id = %s AND conversation_id = %s"
                                 " AND removed_at IS NULL", (repair_id, conv_id)).rowcount
        if not n:
            raise HTTPException(status_code=404, detail="repair not found")
        log.info("owner repair removed conversation=%s repair=%s", conv_id, repair_id)
        return {"removed": str(repair_id)}

    @app.get("/v1/conversations/{conv_id}/coverage", dependencies=[Depends(auth)])
    def conversation_coverage(conv_id: UUID, request: Request):
        """How completely the active generations cover this chat's head (#8, #13)."""
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            return coverage_view(conn, conv_id)

    def coverage_view(conn, conv_id: UUID) -> dict[str, Any]:
        ex_key = rt["active_extractor"]
        pj_key = rt["projection"].key if rt["projection"] else None
        return {
            "extraction": {"generation": generations.describe(conn, ex_key),
                           **extraction.coverage(conn, ex_key, conv_id).get(conv_id, {})},
            "embeddings": {"generation": generations.describe(conn, pj_key),
                           **vectors.coverage(conn, pj_key, conv_id).get(conv_id, {})},
            "canon": {"generation": generations.describe(conn, rt.get("active_canon")),
                      **canonfacts.coverage(conn, rt.get("active_canon"), conv_id)},
        }

    # Per-chat actions (D22, ADR 0008). Only for chats NMOS has seen: NMOS never ingests a chat itself.
    @app.post("/v1/conversations/{conv_id}/extract-history", dependencies=[Depends(auth)])
    def extract_history(conv_id: UUID, request: Request):
        """Queue every turn / message of this chat's head that the active generations have not
        processed, beyond the first-sight backfill, at background priority; failed ones are retried, and
        turns extracted before an earlier turn's secret are extracted again (K29)."""
        ex, pj, cur = rt["extractor"], rt["projection"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if ex is None and pj is None:
                raise HTTPException(status_code=409, detail="fact extraction and embeddings are both off")
            for kind, gen in (("extract", ex), ("embed", pj), ("canon", rt["canon"])):
                if gen:
                    extraction.retry_failed(conn, kind, gen.key, conv_id)
            unseen = extraction.discard_unseen_secrets(conn, ex.key, conv_id) if ex else 0
            queued = {
                "extract": extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id, history=True)
                if ex else 0,
                "embed": vectors.schedule_projection(conn, pj.key, cur.embed_backfill, conv_id, history=True)
                if pj else 0,
                "canon": canonfacts.schedule(conn, rt["canon"].key, conv_id) if rt["canon"] else 0,
            }
            log.info("extract history conversation=%s queued=%s unseen_secrets=%d", conv_id, queued, unseen)
            return {"queued": queued, "coverage": coverage_view(conn, conv_id)}

    @app.post("/v1/conversations/{conv_id}/rebuild", dependencies=[Depends(auth)])
    def rebuild_memory(conv_id: UUID, request: Request):
        """Redo this chat's facts: discard its extractions of every generation (kept for audit, ADR
        0014) and re-extract every turn, recent ones first. Raw evidence, state and embeddings stay."""
        ex, cur = rt["extractor"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if ex is None:
                raise HTTPException(status_code=409, detail="fact extraction is off")
            with conn.transaction():
                discarded = extraction.discard(conn, conv_id)  # the canon's extractions too (ADR 0047)
                queued = extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id, history=True)
                canonfacts.requeue(conn, conv_id)
            read = canonfacts.schedule(conn, rt["canon"].key, conv_id) if rt["canon"] else 0
            log.info("rebuild conversation=%s discarded=%d queued=%d canon=%d", conv_id, discarded, queued, read)
            return {"discarded": discarded, "queued": {"extract": queued, "canon": read},
                    "coverage": coverage_view(conn, conv_id)}

    @app.post("/v1/conversations/{conv_id}/delete", dependencies=[Depends(auth)])
    def delete_conversation(conv_id: UUID, request: Request):
        """Delete this chat from NMOS with everything recorded for it, raw messages included (ADR 0009).
        Irreversible. If the host chat still exists, the next generation in it syncs it as a new chat."""
        with request.app.state.pool.connection() as conn:
            deleted = ledger.delete_conversation(conn, conv_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        log.info("deleted conversation=%s rows=%s", conv_id, deleted)
        return {"deleted": deleted}

    @app.get("/v1/config", dependencies=[Depends(auth)])
    def get_config():
        return runtime.public_view(rt["settings"], rt["overrides"], rt["rules"])

    @app.put("/v1/config", dependencies=[Depends(auth)])
    def put_config(update: dict[str, Any], request: Request):
        clean, errors = runtime.validate_update(update)
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        clean = runtime.keys_follow_hosts(settings, rt["overrides"], clean)
        before_ex, before_pj, before_sm, before_cg = rt["extractor"], rt["projection"], rt["summarizer"], rt["canon"]
        before_backfill = rt["settings"].extract_backfill
        with request.app.state.pool.connection() as conn:
            runtime.save(conn, clean)
            rebuild(runtime.stored(conn))
            if runtime.PARSERS_KEY in clean:
                rebuild_state(conn, rt["rules"])
            queued = activate(conn, before_ex.key if before_ex else None, before_pj.key if before_pj else None,
                              before_sm.key if before_sm else None, before_cg.key if before_cg else None)
            ex = rt["extractor"]
            if ex and before_ex and ex.key == before_ex.key and rt["settings"].extract_backfill != before_backfill:
                # Same generation, different backfill: queue what the new window is missing now, not at
                # the next restart (ADR 0008). Idempotent; a smaller backfill queues nothing.
                queued += extraction.schedule_generation(conn, ex.key, rt["settings"].extract_backfill)
        return {**runtime.public_view(rt["settings"], rt["overrides"], rt["rules"]), "queued_jobs": queued}

    def key_for(body: dict[str, Any], kind: str) -> tuple[str, str]:
        """The key a test or model list sends, and a note when the saved one was kept from another host."""
        cur = rt["settings"]
        saved_url, saved_key = (cur.embed_url, cur.embed_api_key) if kind == "embeddings" else (cur.llm_url, cur.llm_api_key)
        if body.get("api_key"):
            return body["api_key"], ""
        key = runtime.saved_key_for(body.get("url") or "", saved_url, saved_key)
        return key, runtime.withheld_note(saved_url) if saved_key and not key else ""

    def noted(result: dict[str, Any], note: str) -> dict[str, Any]:
        return {**result, "error": result["error"] + note} if note and not result.get("ok") and "error" in result else result

    @app.post("/v1/config/test", dependencies=[Depends(auth)])
    def test_config(body: dict[str, Any]):
        cur = rt["settings"]
        kind = body.get("kind")
        if kind == "llm":
            key, note = key_for(body, kind)
            return noted(runtime.test_llm(body.get("url") or cur.llm_url, body.get("model") or cur.llm_model, key,
                                          bool(body.get("json_mode", cur.llm_json_mode))), note)
        if kind == "embeddings":
            key, note = key_for(body, kind)
            return noted(runtime.test_embeddings(body.get("url") or cur.embed_url, body.get("model") or cur.embed_model,
                                                 key), note)
        raise HTTPException(status_code=422, detail="kind must be 'llm' or 'embeddings'")

    @app.post("/v1/config/models", dependencies=[Depends(auth)])
    def config_models(body: dict[str, Any]):
        kind = body.get("kind", "llm")
        key, note = key_for(body, kind)
        return noted(runtime.list_models(body.get("url") or "", key, kind), note)

    def inspector_index_html(request: Request, token: str | None, lang: str | None, embed: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            ex_key = rt["active_extractor"]
            pj_key = rt["projection"].key if rt["projection"] else None
            return inspector.index(readmodel.list_conversations(conn), token, job_counts(conn),
                                   {"extraction": generations.describe(conn, ex_key),
                                    "embeddings": generations.describe(conn, pj_key),
                                    "summaries": generations.describe(conn, rt.get("active_summarizer"))},
                                   # no generation ever active: "—", not a 0 % that reads as unfinished work
                                   extraction.coverage(conn, ex_key) if ex_key else {},
                                   vectors.coverage(conn, pj_key) if pj_key else {},
                                   lang=inspector.lang_of(lang), embed=embed,
                                   plugin={"expected": plugin.expected(), "seen": plugins.recent()})

    def inspector_detail_html(conv_id: UUID, request: Request, token: str | None, lang: str | None,
                              embed: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            ex_key = rt["active_extractor"]
            pj_key = rt["projection"].key if rt["projection"] else None
            view = inspector.with_participants(view_of(conn, head))
            traces = readmodel.traces(conn, conv_id)
            cov = coverage_view(conn, conv_id)
            return inspector.detail(conv, current_state(conn, head, rt["rules"].version),
                                    readmodel.membership(conn, head, ex_key, pj_key),
                                    readmodel.commits(conn, conv_id), traces,
                                    view["facts"][:300], token, cov,
                                    lang=inspector.lang_of(lang), embed=embed, claims=view["claims"],
                                    other=view["other"], entities=view["entities"], ambiguous=view["ambiguous"],
                                    conflicts=view["conflicts"], items=view["items"], threads=view["threads"],
                                    unmatched=view["unmatched"], secrets=view["secrets"],
                                    unrevealed=view["unrevealed"],
                                    standing=[f for f in view["facts"] if f["predicate"] in STANDING],
                                    packet=audit.audit(conn, traces[0]["id"]) if traces else None,
                                    summaries=summary_view(conn, conv_id, head, view["secrets"]),
                                    repairs=repair_rows(conn, conv_id, view["repairs"]), last_turn=head_turn(conn, head),
                                    canon_rows=canon.manifest(conn, conv_id), canon_history=canon.history(conn, conv_id),
                                    canon_held=canon.held(conn, conv_id), canon_read=cov["canon"].get("keys"),
                                    canon_facts=view.get("canon_facts", 0))

    def summary_view(conn, conv_id: UUID, head: UUID, secrets: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The Inspector's summaries of a chat (PHASE-12 step 6), with the generation and whether packets use them."""
        key = rt.get("active_summarizer")
        if key is None:
            return None
        view = summaries.inspect(conn, conv_id, head, key, secrets)
        view.update(generation=generations.describe(conn, key), on=rt["summarizer"] is not None)
        return view

    def inspector_character_html(conv_id: UUID, entity_id: UUID, request: Request, token: str | None,
                                 lang: str | None, embed: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            view = inspector.with_participants(view_of(conn, conv["head_commit_id"]))
            return inspector.character(conv, str(entity_id), view, token, active=rt["active_extractor"],
                                       lang=inspector.lang_of(lang), embed=embed)

    @app.get("/inspector", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_index(request: Request, token: str | None = None, lang: str | None = None):
        return inspector_index_html(request, token, lang)

    @app.get("/inspector/c/{conv_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_detail(conv_id: UUID, request: Request, token: str | None = None, lang: str | None = None):
        return inspector_detail_html(conv_id, request, token, lang)

    @app.get("/inspector/c/{conv_id}/e/{entity_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_character(conv_id: UUID, entity_id: UUID, request: Request, token: str | None = None,
                            lang: str | None = None):
        return inspector_character_html(conv_id, entity_id, request, token, lang)

    # The same pages as body fragments for the plugin panel, which cannot open a browser tab (H15).
    @app.get("/v1/inspector", dependencies=[Depends(auth)])
    def inspector_index_embed(request: Request, lang: str | None = None):
        return {"html": inspector_index_html(request, None, lang, embed=True)}

    @app.get("/v1/inspector/c/{conv_id}", dependencies=[Depends(auth)])
    def inspector_detail_embed(conv_id: UUID, request: Request, lang: str | None = None):
        return {"html": inspector_detail_html(conv_id, request, None, lang, embed=True)}

    @app.get("/v1/inspector/c/{conv_id}/e/{entity_id}", dependencies=[Depends(auth)])
    def inspector_character_embed(conv_id: UUID, entity_id: UUID, request: Request, lang: str | None = None):
        return {"html": inspector_character_html(conv_id, entity_id, request, None, lang, embed=True)}

    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("uvicorn.access").addFilter(RedactToken())
    return create_app()
