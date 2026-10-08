"""HTTP API. Handlers translate requests; ledger/reconcile/retrieval own the logic."""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import os
import tempfile
import time
import dataclasses
import ipaddress
import re
from urllib.parse import quote
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from . import (__version__, archive, audit, canon, canonfacts, dropped, endings, extraction, generations, inspector, ledger,
               normtext, overuse,
               plugin, preview, readmodel, retention, repairs, reveals, runtime, scene, summaries, uploads, vectors)
from . import usage as model_usage
from .config import Settings
from .db import make_pool
from .entities import norm
from .extraction import enqueue_after_apply, job_counts, recent_errors
from .facts import STANDING, links_of as facts_links_of, memory_view, version_key
from .ids import uuid7
from .models import (
    ArchiveUploadChunk,
    ArchiveUploadCreate,
    BodiesRequest,
    BodiesResponse,
    CanonSyncRequest, CanonSyncResponse,
    EntityLinkRequest, ExpectRequest, MemoryModeRequest, ReextractRequest, RepairRequest,
    OutputRequest,
    Packet,
    ReconcileRequest,
    ReconcileResponse,
    RetrieveRequest,
    RetrieveResponse,
    RevisionRef,
)
from .canonical import manifest_hash, manifest_hashes, normalize_text, storable
from .reconcile import Entry, plan, plan_append
from .llm import Embedder
from .packet import DEFAULT_POLICY, POLICIES, clean_text
from .retrieval import RecallOptions, prefetched, query_prefix, retrieve
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
                  summarizer=sm, canon=canonfacts.generation(cur), reveal=reveals.generation(cur),
                  recall=RecallOptions(
            top_k=cur.recall_top_k, threshold=cur.recall_threshold, rules_version=rules.version,
            facts_limit=cur.facts_limit, events_limit=cur.events_limit,
            threads_limit=cur.threads_limit, embedder=emb if pj else None, embed_projection=pj.key if pj else "",
            extractor_key=rt.get("active_extractor"), embed_timeout_ms=cur.embed_timeout_ms,
            lexical_timeout_ms=cur.lexical_timeout_ms, rest_after=cur.rest_after,
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
        rv = rt["reveal"]
        if rv is None:
            if retired := extraction.retire(conn, "reveal"):
                log.info("LLM extraction is off: %d queued reveal checks made obsolete", retired)
        else:  # its checks are queued by "extract all history" only (ADR 0057); another generation's never run
            generations.activate(conn, rv)
            conn.execute("UPDATE job SET status = 'obsolete', updated_at = now() WHERE kind = 'reveal'"
                         " AND status = 'queued' AND payload->>'generation' IS DISTINCT FROM %s", (rv.key,))
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

    def startup_steps() -> int:
        """What every start does, idempotent: the stored settings, the derived text, turn data and state the ledger is
        missing, and each generation's missing jobs. A restore while NMOS runs (PHASE-38 Q4) runs it again for the rows
        it added. Each step commits on its own, the batched backfills batch by batch, so a restart during a long
        backfill resumes it instead of starting over (audit A-08)."""
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
        if backfilled:
            log.info("state backfilled: %d observations for rules %s", backfilled, rt["rules"].version)
        return queued

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        startup_steps()
        app.state.pool = pool or make_pool(settings.database_url)
        try:
            yield
        finally:
            spool.close()  # uploads do not outlive the sidecar (PHASE-38)
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

    def prefetch_query(body: BodiesRequest) -> None:
        """The newest user message's embedding is asked for as soon as its text arrives (ADR 0061 item 7): the
        retrieve that follows this sync sends the same text as its query (the plugin's `queryTexts`) and takes it from
        `retrieval.prefetched`. Nothing is stored; a text no retrieve asks for is dropped after a minute."""
        recall = rt["recall"]
        if recall.embedder is None or body.then_reconcile is None or not body.then_reconcile.messages:
            return
        last = body.then_reconcile.messages[-1]
        if last.role != "user" or last.disabled or last.is_comment:
            return
        content = next((b.content for b in body.bodies if b.host_logical_id == last.host_logical_id
                        and b.revision_hash == last.revision_hash), None)
        if content is None:
            return
        text = clean_text(normalize_text(content))
        if text.strip():
            prefetched.start(recall.embedder, recall.embed_projection, recall.query_prefix + text,
                             recall.embed_timeout_ms)

    @app.post("/v1/sync/bodies", response_model=BodiesResponse, dependencies=[Depends(auth)])
    def bodies(body: BodiesRequest, request: Request):
        prefetch_query(body)  # before the database work: the embedder gets that time too
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
            vectors=out.get("vectors"),
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
    def conversations(request: Request, host_chat_ref: str | None = None, host: str | None = None):
        with request.app.state.pool.connection() as conn:
            return readmodel.list_conversations(conn, host_chat_ref=host_chat_ref, host=host)

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

    def head_of(conn, conv_id: UUID) -> UUID:
        conv = readmodel.conversation(conn, conv_id)
        if conv is None or conv["head_commit_id"] is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return conv["head_commit_id"]

    def held_alias_of(conn, conv_id: UUID, head: UUID, view: dict[str, Any], held: int, entity_type: str, name: str,
                      same_as: str) -> None:
        """The held alias a link from "Needs attention" names (PHASE-29 Q5): listed now, of a character, the same two
        names (either way round); 422 otherwise."""
        listed = endings.held_aliases(conn, head, rt["active_extractor"], view, facts_links_of(conn, conv_id))
        pair = {norm(name), norm(same_as)}
        if entity_type != "character" or not any(
                a["id"] == held and {norm(a["subject"]), norm(a["value"])} == pair for a in listed):
            raise HTTPException(status_code=422, detail="not a held alias of these two names")

    def check_join(r, entity_type: str, name: str, same_as: str, held: bool = False) -> None:
        if r is None or (not held and any(r.status(entity_type, n) == "unresolved" for n in (name, same_as))):
            raise HTTPException(status_code=422, detail="both names must be mentioned in this chat")
        if r.node(entity_type, name) == r.node(entity_type, same_as):
            raise HTTPException(status_code=422, detail="the two names are the same")

    def in_force(conn, table: str, conv_id: UUID, row_id: UUID) -> dict[str, Any] | None:
        cols = "id, entity_type, name, same_as, created_at" if table == "entity_link" else "id, kind, target"
        return conn.execute(f"SELECT {cols} FROM {table} WHERE id = %s AND conversation_id = %s AND removed_at IS NULL",
                            (row_id, conv_id)).fetchone()

    def preview_of(conn, conv_id: UUID, head: UUID, action: str, **a: Any) -> dict[str, Any]:
        """What a join, a split or the undo of either would change (PHASE-20 Q1–Q4): the chat's memory now and as it
        would be, both read as every request reads them, and the difference; nothing is written."""
        now = view_of(conn, head)
        # now(), as the link the join would insert is stamped (DEFAULT now()): the database's clock, the same moment
        at = conn.execute("SELECT now() AS t").fetchone()["t"]
        exclude: set[str] = set()
        if action == "join":
            if a.get("held_alias") is not None:
                held_alias_of(conn, conv_id, head, now, a["held_alias"], a["entity_type"], a["name"], a["same_as"])
            check_join(now["resolution"], a["entity_type"], a["name"], a["same_as"], a.get("held_alias") is not None)
            names = [(a["entity_type"], a["name"]), (a["entity_type"], a["same_as"])]
            what_if = {"add_links": [{"id": "preview", "entity_type": a["entity_type"], "name": a["name"].strip(),
                                      "same_as": a["same_as"].strip(), "created_at": at}]}
        elif action == "split":
            try:
                target, value = repairs.plan("name_split", a["name"], now, head_turn(conn, head), None, None, None,
                                             None, None, a["other"], a["entity_type"], version_key)
            except repairs.RepairError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            names = [(target["entity_type"], target["name"]), (target["entity_type"], target["other"])]
            what_if = {"add_repairs": [{"id": "preview", "kind": "name_split", "target": target, "value": value,
                                        "note": None, "created_at": at}]}
            exclude = {"preview"}
        elif action == "unlink":
            link = in_force(conn, "entity_link", conv_id, a["row"])
            if link is None:
                raise HTTPException(status_code=404, detail="link not found")
            names = [(link["entity_type"], link["name"]), (link["entity_type"], link["same_as"])]
            what_if = {"drop_links": {str(link["id"])}}
        else:  # "unsplit"
            rep = in_force(conn, "owner_repair", conv_id, a["row"])
            if rep is None:
                raise HTTPException(status_code=404, detail="repair not found")
            if rep["kind"] != "name_split":
                raise HTTPException(status_code=422, detail="only a join or a split has a preview")
            t = rep["target"]
            names = [(t["entity_type"], t["name"]), (t["entity_type"], t["other"])]
            what_if = {"drop_repairs": {str(rep["id"])}}
            exclude = {str(rep["id"])}
        then = memory_view(conn, head, rt["active_extractor"], canon_key=rt.get("active_canon"), what_if=what_if)
        out = preview.diff(now, then, names, exclude)
        if action == "unlink":  # the turns an undo leaves as the join had them extracted (Q7)
            ra = then["resolution"]
            one = ra.entity(link["entity_type"], link["name"]), ra.entity(link["entity_type"], link["same_as"])
            apart = not (one[0] is not None and one[1] is not None and one[0]["id"] == one[1]["id"])
            found = extraction.joined_turns(conn, conv_id, link, rt["active_extractor"]) if apart else []
            turns = [t["turn"] for t in found]
            out["reextract"] = {"turns": len(turns), "list": turns}  # none while the names stay one entity anyway
        state = {"head": head, "links": sorted(str(x["id"]) for x in facts_links_of(conn, conv_id)),
                 "repairs": sorted(str(x["id"]) for x in now["repairs"]), "extractor": rt["active_extractor"],
                 "canon": rt.get("active_canon"), "canon_manifest": now.get("canon_names")}
        return {"action": action, **out, "fingerprint": preview.fingerprint(out, state)}

    def expect_same(conn, conv_id: UUID, expect: str | None, action: str, **a: Any) -> None:
        """An action made from a preview (Q4): 409 with a fresh preview when memory changed since. Called inside the
        action's transaction: the chat's row is locked first and its head read under the lock, so a sync, a join or a
        repair of the same chat waits until the action is written (ADR 0055)."""
        if expect is None:
            return
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s FOR UPDATE", (conv_id,)).fetchone()
        if head is None or head["head_commit_id"] is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        fresh = preview_of(conn, conv_id, head["head_commit_id"], action, **a)
        if fresh["fingerprint"] != expect:
            raise HTTPException(status_code=409, detail={"message": "memory changed since the preview",
                                                         "preview": jsonable_encoder(fresh)})

    @app.post("/v1/conversations/{conv_id}/entity-links/preview", dependencies=[Depends(auth)])
    def preview_entity_link(conv_id: UUID, body: EntityLinkRequest, request: Request):
        """What joining two names would change in this chat's memory (PHASE-20), before the owner joins them."""
        with request.app.state.pool.connection() as conn:
            return preview_of(conn, conv_id, head_of(conn, conv_id), "join", entity_type=body.entity_type,
                              name=body.name, same_as=body.same_as, held_alias=body.held_alias)

    @app.post("/v1/conversations/{conv_id}/entity-links", dependencies=[Depends(auth)])
    def add_entity_link(conv_id: UUID, body: EntityLinkRequest, request: Request):
        """The owner says two names of this chat are one entity (ADR 0025). Both must be mentioned on the
        head now, with that type. The link joins them on every read until the owner removes it. With `expect`, the
        fingerprint of the preview the owner saw: 409 when memory changed since (PHASE-20 Q4)."""
        with request.app.state.pool.connection() as conn:
            head = head_of(conn, conv_id)
            now = view_of(conn, head)
            if body.held_alias is not None:  # PHASE-29 Q5: linked from "Needs attention"
                held_alias_of(conn, conv_id, head, now, body.held_alias, body.entity_type, body.name, body.same_as)
            check_join(now["resolution"], body.entity_type, body.name, body.same_as, body.held_alias is not None)
            with conn.transaction():
                expect_same(conn, conv_id, body.expect, "join", entity_type=body.entity_type, name=body.name,
                            same_as=body.same_as, held_alias=body.held_alias)
                link = conn.execute(
                    "INSERT INTO entity_link (id, conversation_id, entity_type, name, same_as) VALUES (%s, %s, %s, %s, %s)"
                    " RETURNING id, entity_type, name, same_as, created_at",
                    (uuid7(), conv_id, body.entity_type, body.name.strip(), body.same_as.strip())).fetchone()
            log.info("entity link conversation=%s link=%s", conv_id, link["id"])
            entity = view_of(conn, head)["resolution"].entity(body.entity_type, body.name)
            return {"link": link, "entity": entity}

    @app.post("/v1/conversations/{conv_id}/entity-links/{link_id}/remove/preview", dependencies=[Depends(auth)])
    def preview_remove_entity_link(conv_id: UUID, link_id: UUID, request: Request):
        """What taking a join back would change (PHASE-20 Q2)."""
        with request.app.state.pool.connection() as conn:
            return preview_of(conn, conv_id, head_of(conn, conv_id), "unlink", row=link_id)

    @app.post("/v1/conversations/{conv_id}/entity-links/{link_id}/remove", dependencies=[Depends(auth)])
    def remove_entity_link(conv_id: UUID, link_id: UUID, request: Request, body: ExpectRequest | None = None):
        """The owner takes a link back (ADR 0025): the next read resolves the names as the story alone
        does. The row stays with `removed_at` for audit. With `expect`, as a join (PHASE-20 Q4)."""
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                expect_same(conn, conv_id, body.expect if body else None, "unlink", row=link_id)
                n = conn.execute("UPDATE entity_link SET removed_at = now() WHERE id = %s AND conversation_id = %s"
                                 " AND removed_at IS NULL", (link_id, conv_id)).rowcount
        if not n:
            raise HTTPException(status_code=404, detail="link not found")
        log.info("entity link removed conversation=%s link=%s", conv_id, link_id)
        return {"removed": str(link_id)}

    @app.post("/v1/conversations/{conv_id}/entity-links/{link_id}/reextract", dependencies=[Depends(auth)])
    def reextract_joined(conv_id: UUID, link_id: UUID, request: Request, body: ReextractRequest | None = None):
        """After the owner takes a join back (PHASE-20 Q7): extract again, with the names apart, the turns extracted
        while the join held. Their extractions of every generation are discarded (kept for audit) and just those
        turns queued; model calls at the owner's provider. A new call, not the old result brought back. With `turns`
        (the undo's preview listed them), only those of them still found: never more calls than the owner saw."""
        ex, cur = rt["extractor"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            head = head_of(conn, conv_id)
            link = conn.execute("SELECT id, entity_type, name, same_as, created_at, removed_at FROM entity_link"
                                " WHERE id = %s AND conversation_id = %s", (link_id, conv_id)).fetchone()
            if link is None:
                raise HTTPException(status_code=404, detail="link not found")
            if link["removed_at"] is None:
                raise HTTPException(status_code=422, detail="take the join back first")
            if ex is None:
                raise HTTPException(status_code=409, detail="fact extraction is off")
            r = view_of(conn, head)["resolution"]
            a, b = r.entity(link["entity_type"], link["name"]), r.entity(link["entity_type"], link["same_as"])
            if a is not None and b is not None and a["id"] == b["id"]:
                raise HTTPException(status_code=422, detail="the two names are one entity now")
            turns = extraction.joined_turns(conn, conv_id, link, ex.key)
            if body is not None and body.turns is not None:
                turns = [t for t in turns if t["turn"] in set(body.turns)]
            with conn.transaction():
                discarded = extraction.discard_turns(conn, turns)
                queued = extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id)
            log.info("reextract joined turns conversation=%s link=%s turns=%d discarded=%d queued=%d", conv_id,
                     link_id, len(turns), discarded, queued)
            return {"turns": [t["turn"] for t in turns], "discarded": discarded, "queued": queued,
                    "coverage": coverage_view(conn, conv_id)}

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

    @app.get("/v1/conversations/{conv_id}/dropped", dependencies=[Depends(auth)])
    def conversation_dropped(conv_id: UUID, request: Request):
        """Narrated facts a re-extraction of this chat dropped and its memory no longer holds (PHASE-22 Q5), oldest turn
        first, with the `id` a restore names (Q7)."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            if head is None:
                return []
            return [{k: f.get(k) for k in ("id", "turn", "predicate", "subject", "object", "value", "text", "evidence")}
                    for f in dropped.find(conn, head, rt["active_extractor"], view_of(conn, head))]

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

    @app.post("/v1/conversations/{conv_id}/repairs/preview", dependencies=[Depends(auth)])
    def preview_repair(conv_id: UUID, body: RepairRequest, request: Request):
        """What splitting two names would change in this chat's memory (PHASE-20 Q2); other repairs have no preview."""
        if body.kind != "name_split":
            raise HTTPException(status_code=422, detail="only a join or a split has a preview")
        with request.app.state.pool.connection() as conn:
            return preview_of(conn, conv_id, head_of(conn, conv_id), "split", entity_type=body.entity_type,
                              name=body.item, other=body.other)

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
            view = view_of(conn, head)
            if body.kind == "fact_restore":  # a fact a re-extraction dropped, or a held role ending (PHASE-28 Q7)
                view["dropped"] = (dropped.find(conn, head, rt["active_extractor"], view)
                                   + endings.held(conn, head, rt["active_extractor"], view))
            try:
                target, value = repairs.plan(body.kind, body.item, view,
                                             head_turn(conn, head), body.outcome, body.character, body.turn,
                                             body.new_object, body.new_value, body.other, body.entity_type,
                                             version_key)
            except repairs.RepairError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            with conn.transaction():
                if body.kind == "name_split":
                    expect_same(conn, conv_id, body.expect, "split", entity_type=body.entity_type, name=body.item,
                                other=body.other)
                row = conn.execute(
                    "INSERT INTO owner_repair (id, conversation_id, kind, target, value, note) VALUES (%s, %s, %s, %s, %s, %s)"
                    " RETURNING id, kind, target, value, note, created_at",
                    (uuid7(), conv_id, body.kind, Jsonb(target), Jsonb(value), (body.note or "").strip() or None)).fetchone()
            applied = next((x["applied"] for x in view_of(conn, head)["repairs"]
                            if x["id"] == row["id"]), None)
        log.info("owner repair conversation=%s repair=%s kind=%s applied=%s", conv_id, row["id"], body.kind,
                 applied is not None)
        return {"repair": row, "applied": applied}

    @app.post("/v1/conversations/{conv_id}/repairs/{repair_id}/remove/preview", dependencies=[Depends(auth)])
    def preview_remove_repair(conv_id: UUID, repair_id: UUID, request: Request):
        """What taking a split back would change (PHASE-20 Q2)."""
        with request.app.state.pool.connection() as conn:
            return preview_of(conn, conv_id, head_of(conn, conv_id), "unsplit", row=repair_id)

    @app.post("/v1/conversations/{conv_id}/repairs/{repair_id}/remove", dependencies=[Depends(auth)])
    def remove_repair(conv_id: UUID, repair_id: UUID, request: Request, body: ExpectRequest | None = None):
        """The owner takes a repair back (ADR 0044): the next read is as the story alone says. The row stays with
        `removed_at` for audit. With `expect`, a split's undo made from its preview (PHASE-20 Q4)."""
        with request.app.state.pool.connection() as conn:
            with conn.transaction():
                expect_same(conn, conv_id, body.expect if body else None, "unsplit", row=repair_id)
                n = conn.execute("UPDATE owner_repair SET removed_at = now() WHERE id = %s AND conversation_id = %s"
                                 " AND removed_at IS NULL", (repair_id, conv_id)).rowcount
        if not n:
            raise HTTPException(status_code=404, detail="repair not found")
        log.info("owner repair removed conversation=%s repair=%s", conv_id, repair_id)
        return {"removed": str(repair_id)}

    @app.get("/v1/conversations/{conv_id}/coverage", dependencies=[Depends(auth)])
    def conversation_coverage(conv_id: UUID, request: Request, usage: bool = False):
        """How completely the active generations cover this chat's head (#8, #13); with `usage`, what its model
        calls used (ADR 0051), which the HUD's frequent polls leave out."""
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            return coverage_view(conn, conv_id, usage)

    def coverage_view(conn, conv_id: UUID, usage: bool = False, lost: int | None = None) -> dict[str, Any]:
        """With `usage` (the panel's chat card and the Inspector, not the HUD's polls): the model usage, and how many facts
        a re-extraction dropped (PHASE-22 Q6; `lost`: counted already)."""
        ex_key = rt["active_extractor"]
        pj_key = rt["projection"].key if rt["projection"] else None
        rv_key = rt["reveal"].key if rt["reveal"] else None
        spent = {"usage": model_usage.totals(conn, conv_id, {ex_key, pj_key, rt.get("active_summarizer"),
                                                              rt.get("active_canon"), rv_key} - {None})} if usage else {}
        if usage:
            if lost is None:
                head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (conv_id,)).fetchone()
                lost = len(dropped.find(conn, head["head_commit_id"], ex_key, view_of(conn, head["head_commit_id"]))) \
                    if head and head["head_commit_id"] else 0
            spent["dropped"] = lost
        compiled = extraction.coverage(conn, ex_key, conv_id).get(conv_id)
        return {
            "extraction": {"generation": generations.describe(conn, ex_key), **(compiled or {}),
                           **({"reveal_checks": reveals.coverage(conn, rv_key, conv_id)} if compiled else {})},
            "embeddings": {"generation": generations.describe(conn, pj_key),
                           **vectors.coverage(conn, pj_key, conv_id).get(conv_id, {})},
            "canon": {"generation": generations.describe(conn, rt.get("active_canon")),
                      **canonfacts.coverage(conn, rt.get("active_canon"), conv_id)},
            **model_usage.work(conn, conv_id, ex_key, rt.get("active_summarizer")),
            **spent,
        }

    # Per-chat actions (D22, ADR 0008). Only for chats NMOS has seen: NMOS never ingests a chat itself.
    @app.post("/v1/conversations/{conv_id}/extract-history", dependencies=[Depends(auth)])
    def extract_history(conv_id: UUID, request: Request):
        """Queue every turn / message of this chat's head that the active generations have not
        processed, beyond the first-sight backfill, at background priority; failed ones are retried, and
        turns extracted before an earlier turn's secret get a reveal check (K29, PHASE-22 Q1): their extractions stay."""
        ex, pj, cur = rt["extractor"], rt["projection"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if ex is None and pj is None:
                raise HTTPException(status_code=409, detail="fact extraction and embeddings are both off")
            for kind, gen in (("extract", ex), ("embed", pj), ("canon", rt["canon"])):
                if gen:
                    extraction.retry_failed(conn, kind, gen.key, conv_id)
            queued = {
                "extract": extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id, history=True)
                if ex else 0,
                "embed": vectors.schedule_projection(conn, pj.key, cur.embed_backfill, conv_id, history=True)
                if pj else 0,
                "canon": canonfacts.schedule(conn, rt["canon"].key, conv_id) if rt["canon"] else 0,
                # after the extract jobs: a turn queued again is extracted with what is open by then, not checked
                "reveal": reveals.schedule(conn, rt["reveal"].key, ex.key, conv_id) if ex and rt["reveal"] else 0,
            }
            log.info("extract history conversation=%s queued=%s", conv_id, queued)
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

    @app.get("/v1/archive", dependencies=[Depends(auth)])
    def archive_export(request: Request, background: BackgroundTasks,
                       conversation: list[UUID] | None = Query(None), projections: bool = True,
                       embeddings: bool = False):
        """An NMOS Archive (ADR 0050): the whole install with its settings, or the chosen conversations. One
        read-only snapshot; the file holds chat text, never a key or the token."""
        tmp = tempfile.NamedTemporaryFile(prefix="nmos-archive-", suffix=archive.SUFFIX, delete=False)
        try:
            with tmp, request.app.state.pool.connection() as conn:
                result = archive.write_archive(conn, tmp, [str(c) for c in conversation] if conversation else None,
                                               projections=projections, embeddings=embeddings,
                                               settings=[settings, rt["settings"]])
        except archive.ArchiveError as error:
            os.unlink(tmp.name)
            missing = isinstance(error, archive.NoSuchConversation)
            raise HTTPException(status_code=404 if missing else 409, detail=str(error)) from None
        except BaseException:
            os.unlink(tmp.name)
            raise
        background.add_task(os.unlink, tmp.name)
        log.info("archive scope=%s conversations=%d bytes=%d", result.manifest["scope"],
                 len(result.manifest["conversations"]), os.path.getsize(tmp.name))
        chosen = None if result.manifest["scope"] == "install" else len(result.manifest["conversations"])
        return FileResponse(tmp.name, media_type="application/zip", filename=archive.default_name(chosen))

    # --- restore from the panel (PHASE-38; ADR 0050 amendment 2) ------------------------------------------------------
    spool = uploads.Uploads(settings.restore_max_mb * 1024 * 1024, make_dir=lambda: uploads.spool_dir())

    def upload_error(error: uploads.UploadError) -> HTTPException:
        return HTTPException(status_code=error.status, detail=error.detail)

    @app.post("/v1/archive/uploads", dependencies=[Depends(auth)])
    def upload_create(body: ArchiveUploadCreate):
        """Start an upload of `bytes` bytes, sent in chunks of `chunk_bytes`; it replaces any other upload (Q2)."""
        try:
            return spool.create(body.bytes).view()
        except uploads.UploadError as e:
            raise upload_error(e) from None

    @app.put("/v1/archive/uploads/{upload_id}/chunks/{index}", dependencies=[Depends(auth)])
    def upload_chunk(upload_id: str, index: int, body: ArchiveUploadChunk):
        try:
            data = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=422, detail=f"chunk {index} is not base64") from None
        try:
            up = spool.chunk(upload_id, index, data, body.sha256)
        except uploads.UploadError as e:
            raise upload_error(e) from None
        return {"state": up.state, "received": up.received, "bytes": up.size}

    @app.get("/v1/archive/uploads/{upload_id}", dependencies=[Depends(auth)])
    def upload_status(upload_id: str):
        try:
            return spool.get(upload_id).view()
        except uploads.UploadError as e:
            raise upload_error(e) from None

    @app.delete("/v1/archive/uploads/{upload_id}", dependencies=[Depends(auth)])
    def upload_discard(upload_id: str):
        try:
            spool.discard(upload_id)
        except uploads.UploadError as e:
            raise upload_error(e) from None
        return {"discarded": True}

    def check_upload(up: uploads.Upload) -> None:
        try:
            up.checked = archive.check_archive(str(up.path))
            up.summary = archive.summary(settings.database_url, up.checked)
            up.state = "checked"
        except archive.ArchiveError as e:
            up.state, up.detail = "refused", str(e)
        except Exception as e:  # noqa: BLE001 — the panel shows it; the log has the trace
            log.exception("archive check failed upload=%s", up.id)
            up.state, up.detail = "refused", f"the archive could not be checked: {e}"
        log.info("archive upload=%s %s %s", up.id, up.state, up.detail)

    def restore_upload(up: uploads.Upload) -> None:
        try:
            done = archive.restore_archive(settings.database_url, up.checked)
        except archive.ArchiveError as e:
            up.state, up.detail = "failed", str(e)
            log.info("archive restore upload=%s refused: %s", up.id, e)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("archive restore failed upload=%s", up.id)
            up.state, up.detail = "failed", f"the archive could not be restored; none of it was written: {e}"
            return
        up.result = dataclasses.asdict(done)
        try:  # the rows it added get what a start would write for them (Q4)
            up.result["queued_jobs"] = startup_steps()
        except Exception as e:  # noqa: BLE001 — the restore is committed; the next start writes them
            log.exception("after the restore of upload=%s", up.id)
            up.detail = f"restored; the derived rows will be written at the next start ({e})"
        up.state = "restored"
        log.info("archive restored upload=%s conversations=%d rows=%s", up.id, len(done.conversations), done.rows)

    @app.post("/v1/archive/uploads/{upload_id}/check", status_code=202, dependencies=[Depends(auth)])
    def upload_check(upload_id: str):
        """Check the whole archive (every file's size, rows and hash; its schema) and summarize what it would bring
        (Q2); in the background: poll the upload."""
        try:
            return spool.run(upload_id, "received", "checking", check_upload).view()
        except uploads.UploadError as e:
            raise upload_error(e) from None

    @app.post("/v1/archive/uploads/{upload_id}/restore", status_code=202, dependencies=[Depends(auth)])
    def upload_restore(upload_id: str):
        """Restore a checked archive while NMOS runs (Q4): writes that draw a shared id wait; reads go on."""
        try:
            return spool.run(upload_id, "checked", "restoring", restore_upload).view()
        except uploads.UploadError as e:
            raise upload_error(e) from None

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
                                   plugin={"expected": plugin.expected(), "seen": plugins.recent()},
                                   version=__version__, errors=recent_errors(conn))

    def inspector_detail_html(conv_id: UUID, request: Request, token: str | None, lang: str | None,
                              embed: bool = False, span: str | None = None, lazy: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            ex_key = rt["active_extractor"]
            pj_key = rt["projection"].key if rt["projection"] else None
            view = inspector.with_participants(view_of(conn, head))
            lost = dropped.find(conn, head, ex_key, view)  # PHASE-22 Q6
            role_ends = {"automatic": endings.automatic(conn, view, head_turn(conn, head)),  # PHASE-28 Q7
                         "held": endings.held(conn, head, ex_key, view),
                         "aliases_held": endings.held_aliases(conn, head, ex_key, view,  # PHASE-29 Q5
                                                              facts_links_of(conn, conv_id))}
            traces = readmodel.traces(conn, conv_id)
            cov = coverage_view(conn, conv_id, usage=True, lost=len(lost))
            with inspector.turn_links(conv_id, token, inspector.lang_of(lang)):  # turn cells lead to their turns
                html = inspector.detail(conv, current_state(conn, head, rt["rules"].version),
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
                                        canon_facts=view.get("canon_facts", 0), dropped=lost,
                                        endings=role_ends, span=inspector.span_of(span),
                                        cast=None if embed else cast_of(view, traces), lazy=lazy,
                                        overuse=overuse.placement(readmodel.ledgers(conn, conv_id)))
            return html

    def inspector_cast_html(conv_id: UUID, request: Request, lang: str | None, span: str | None) -> str:
        """The conversation's cast lines alone for the panel (PHASE-32 step 3), asked for when their section opens."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            view = inspector.with_participants(view_of(conn, conv["head_commit_id"]))
            return inspector.conversation_cast(conv, cast_of(view, readmodel.traces(conn, conv_id)),
                                               head_turn(conn, conv["head_commit_id"]), inspector.lang_of(lang),
                                               inspector.span_of(span))

    def cast_of(view: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any]:
        """What the conversation page's cast lines draw (PHASE-32): every fact and entity, and the characters of the
        newest request's scene (its trace records their names), first."""
        r = view.get("resolution")
        names = ((traces[0].get("latency_ms") or {}).get("scene_cast") or []) if traces else []
        return {"facts": view["facts"], "entities": view["entities"],
                "scene": [scene.key(r, n) for n in names] if r is not None else []}

    def summary_view(conn, conv_id: UUID, head: UUID, secrets: list[dict[str, Any]]) -> dict[str, Any] | None:
        """The Inspector's summaries of a chat (PHASE-12 step 6), with the generation and whether packets use them."""
        key = rt.get("active_summarizer")
        if key is None:
            return None
        view = summaries.inspect(conn, conv_id, head, key, secrets)
        view.update(generation=generations.describe(conn, key), on=rt["summarizer"] is not None)
        return view

    def inspector_character_html(conv_id: UUID, entity_id: UUID, request: Request, token: str | None,
                                 lang: str | None, embed: bool = False, span: str | None = None, lazy: bool = False,
                                 part: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            view = inspector.with_participants(view_of(conn, conv["head_commit_id"]))
            with inspector.turn_links(conv_id, token, inspector.lang_of(lang)):
                if part:  # the timeline alone, for the panel (PHASE-32 step 3)
                    return inspector.character_timeline(conv, str(entity_id), view, inspector.lang_of(lang),
                                                        head_turn(conn, conv["head_commit_id"]), inspector.span_of(span))
                return inspector.character(conv, str(entity_id), view, token, active=rt["active_extractor"],
                                           lang=inspector.lang_of(lang), embed=embed,
                                           now=None if embed else head_turn(conn, conv["head_commit_id"]),
                                           span=inspector.span_of(span), lazy=lazy)

    def inspector_turn_html(conv_id: UUID, turn: int, request: Request, token: str | None, lang: str | None,
                            embed: bool = False) -> str:
        """The source-turn page (PHASE-33 Q7): read-only, the same token handling as the other pages."""
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            messages = readmodel.turn_messages(conn, head, turn)
            revisions = {str(m["revision_id"]) for m in messages}
            view = view_of(conn, head)
            made = [a for a in view.get("assertions") or [] if a.get("turn") == turn]
            return inspector.source_turn(
                conv, turn, messages, made, readmodel.turn_generations(conn, [m["revision_id"] for m in messages]),
                readmodel.turn_uses(conn, conv_id, revisions, {str(a["id"]) for a in made}),
                readmodel.turn_bounds(conn, head), token, lang=inspector.lang_of(lang), embed=embed,
                active=rt["active_extractor"])

    @app.get("/inspector", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_index(request: Request, token: str | None = None, lang: str | None = None):
        return inspector_index_html(request, token, lang)

    # The Docker-free bundles' tray and menu bar open this (PHASE-23 Q8): the Inspector's first page, which holds
    # the version, the plugin build, the generations in use, the background jobs and their recent errors.
    @app.get("/dashboard", dependencies=[Depends(auth)])
    def dashboard(token: str | None = None, lang: str | None = None):
        q = "&".join(f"{k}={quote(v)}" for k, v in (("token", token), ("lang", lang)) if v)
        return RedirectResponse("/inspector" + (f"?{q}" if q else ""), status_code=307)

    @app.get("/inspector/c/{conv_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_detail(conv_id: UUID, request: Request, token: str | None = None, lang: str | None = None,
                         span: str | None = None):
        return inspector_detail_html(conv_id, request, token, lang, span=span)

    @app.get("/inspector/c/{conv_id}/e/{entity_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_character(conv_id: UUID, entity_id: UUID, request: Request, token: str | None = None,
                            lang: str | None = None, span: str | None = None):
        return inspector_character_html(conv_id, entity_id, request, token, lang, span=span)

    @app.get("/inspector/c/{conv_id}/t/{turn}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_turn(conv_id: UUID, turn: int, request: Request, token: str | None = None, lang: str | None = None):
        return inspector_turn_html(conv_id, turn, request, token, lang)

    # The same pages as body fragments for the plugin panel, which cannot open a browser tab (H15).
    @app.get("/v1/inspector", dependencies=[Depends(auth)])
    def inspector_index_embed(request: Request, lang: str | None = None):
        return {"html": inspector_index_html(request, None, lang, embed=True)}

    # PHASE-32 step 3: a plugin that can show the timeline asks with `timeline=lazy` (a closed section to fill), then
    # for the timeline alone with `part=timeline` when that section opens. Without them the answer is as before.
    @app.get("/v1/inspector/c/{conv_id}", dependencies=[Depends(auth)])
    def inspector_detail_embed(conv_id: UUID, request: Request, lang: str | None = None, timeline: str | None = None,
                               part: str | None = None, span: str | None = None):
        if part == "timeline":
            return {"html": inspector_cast_html(conv_id, request, lang, span)}
        return {"html": inspector_detail_html(conv_id, request, None, lang, embed=True, lazy=timeline == "lazy")}

    @app.get("/v1/inspector/c/{conv_id}/e/{entity_id}", dependencies=[Depends(auth)])
    def inspector_character_embed(conv_id: UUID, entity_id: UUID, request: Request, lang: str | None = None,
                                  timeline: str | None = None, part: str | None = None, span: str | None = None):
        return {"html": inspector_character_html(conv_id, entity_id, request, None, lang, embed=True, span=span,
                                                 lazy=timeline == "lazy", part=part == "timeline")}

    @app.get("/v1/inspector/c/{conv_id}/t/{turn}", dependencies=[Depends(auth)])
    def inspector_turn_embed(conv_id: UUID, turn: int, request: Request, lang: str | None = None):
        return {"html": inspector_turn_html(conv_id, turn, request, None, lang, embed=True)}

    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("uvicorn.access").addFilter(RedactToken())
    return create_app()
