"""HTTP API. Handlers translate requests; ledger/reconcile/retrieval own the logic."""

from __future__ import annotations

import hmac
import logging
import time
import dataclasses
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from psycopg_pool import ConnectionPool

from . import __version__, extraction, generations, inspector, ledger, normtext, readmodel, runtime, vectors
from .config import Settings
from .db import make_pool
from .extraction import enqueue_after_apply, job_counts
from .facts import fact_versions
from .ids import uuid7
from .models import (
    BodiesRequest,
    BodiesResponse,
    OutputRequest,
    Packet,
    ReconcileRequest,
    ReconcileResponse,
    RetrieveRequest,
    RetrieveResponse,
    RevisionRef,
)
from .reconcile import Entry, plan
from .llm import Embedder
from .retrieval import RecallOptions, query_prefix, retrieve
from .state import current_state, rebuild_state, sync_rules, write_state

log = logging.getLogger("nmos.sidecar")


def _entries(request: ReconcileRequest) -> list[Entry]:
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
        for m in request.messages
    ]


def _compact_observation(body: ReconcileRequest, result, base_hash: str | None, base_len: int) -> dict:
    """Host manifest as observed: every entry when a commit is created, only the appended tail otherwise."""
    rows = [[m.host_logical_id, m.revision_hash, m.role, m.disabled, m.is_comment, m.swipe_id, m.swipe_count,
             m.generation_id, m.special_comments or None] for m in body.messages]
    columns = ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count",
               "generation_id", "special_comments"]
    if result.commit_reason is None:
        return {"chat_id": body.chat_id, "columns": columns, "base_manifest_hash": base_hash, "appended": rows[base_len:]}
    return {"chat_id": body.chat_id, "columns": columns, "entries": rows}


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
        rt.update(settings=cur, rules=rules, overrides=overrides, extractor=extraction.extractor(cur), projection=pj,
                  recall=RecallOptions(
            top_k=cur.recall_top_k, threshold=cur.recall_threshold, rules_version=rules.version,
            facts_limit=cur.facts_limit, embedder=emb if pj else None, embed_projection=pj.key if pj else "",
            extractor_key=rt.get("active_extractor"), embed_timeout_ms=cur.embed_timeout_ms,
            lexical_timeout_ms=cur.lexical_timeout_ms,
            vector_min_sim=cur.vector_min_sim, query_prefix=query_prefix(cur.embed_model, cur.embed_query_instruction),
        ))

    def activate(conn, before_extractor: str | None, before_projection: str | None) -> int:
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
        rt["active_extractor"] = generations.active(conn, "extract")
        rt["recall"] = dataclasses.replace(rt["recall"], extractor_key=rt["active_extractor"])
        return queued

    rebuild({})

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = pool or make_pool(settings.database_url)
        with app.state.pool.connection() as conn:
            rebuild(runtime.stored(conn))
            normalized = normtext.backfill(conn)
            if normalized:
                log.info("normalized text written for %d revisions (%s)", normalized, normtext.NORMALIZER_VERSION)
            if turned := ledger.refresh_turns(conn, settings.extract_turns):
                log.info("turn data written for %d head members (K=%d)", turned, settings.extract_turns)
            backfilled = sync_rules(conn, rt["rules"])
            queued = activate(conn, None, None)
            log.info("generations: extract=%s embed=%s; queued %d missing jobs",
                     rt["active_extractor"], rt["projection"].key if rt["projection"] else None, queued)
        if backfilled:
            log.info("state backfilled: %d observations for rules %s", backfilled, rt["rules"].version)
        try:
            yield
        finally:
            if pool is None:
                app.state.pool.close()

    app = FastAPI(title="NMOS sidecar", version=__version__, lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT"],  # PUT: settings panel saves /v1/config directly
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

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

    def do_reconcile(conn, body: ReconcileRequest) -> ReconcileResponse:
        conv = ledger.lock_conversation(conn, body.host, body.chat_id, body.character_ref, body.character_name,
                                        body.chat_name)
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
        head = ledger.apply_plan(conn, conv, state, result, observation, manifest, settings.extract_window,
                                settings.extract_turns)
        cur = rt["settings"]
        if rt["extractor"] or rt["projection"]:
            enqueue_after_apply(conn, conv.id, state.head, state.lifecycle, manifest,
                                {**state.lifecycle, **result.lifecycle}, state.revision_ids,
                                settings.extract_turns, cur.extract_backfill,
                                extractor_key=rt["extractor"].key if rt["extractor"] else None,
                                embed_key=rt["projection"].key if rt["projection"] else None,
                                embed_backfill=cur.embed_backfill)
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
                                "embed": rt["projection"].key if rt["projection"] else None}}

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

    @app.post("/v1/retrieve", response_model=RetrieveResponse, dependencies=[Depends(auth)])
    def retrieve_route(body: RetrieveRequest, request: Request):
        delay()
        with request.app.state.pool.connection() as conn:
            out = retrieve(conn, body, rt["recall"])
        return RetrieveResponse(
            trace_id=out["trace_id"] or uuid7(),
            freshness=out["freshness"],
            packet=Packet(text=out["text"], token_estimate=out["tokens"], excerpt_count=out["count"]),
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
            facts = (fact_versions(conn, conv["head_commit_id"], rt["active_extractor"])
                     if conv["head_commit_id"] else [])
        return [{k: v for k, v in f.items() if history or k != "history"} for f in facts]

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
        }

    # Per-chat actions (D22, ADR 0008). Only for chats NMOS has seen: NMOS never ingests a chat itself.
    @app.post("/v1/conversations/{conv_id}/extract-history", dependencies=[Depends(auth)])
    def extract_history(conv_id: UUID, request: Request):
        """Queue every turn / message of this chat's head that the active generations have not
        processed, beyond the first-sight backfill, at background priority."""
        ex, pj, cur = rt["extractor"], rt["projection"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if ex is None and pj is None:
                raise HTTPException(status_code=409, detail="fact extraction and embeddings are both off")
            queued = {
                "extract": extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id, history=True)
                if ex else 0,
                "embed": vectors.schedule_projection(conn, pj.key, cur.embed_backfill, conv_id, history=True)
                if pj else 0,
            }
            log.info("extract history conversation=%s queued=%s", conv_id, queued)
            return {"queued": queued, "coverage": coverage_view(conn, conv_id)}

    @app.post("/v1/conversations/{conv_id}/rebuild", dependencies=[Depends(auth)])
    def rebuild_memory(conv_id: UUID, request: Request):
        """Redo this chat's facts: discard its extractions of the active generation (kept for audit)
        and re-extract every turn, recent ones first. Raw evidence, state and embeddings stay."""
        ex, cur = rt["extractor"], rt["settings"]
        with request.app.state.pool.connection() as conn:
            if readmodel.conversation(conn, conv_id) is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            if ex is None:
                raise HTTPException(status_code=409, detail="fact extraction is off")
            with conn.transaction():
                discarded = extraction.discard(conn, ex.key, conv_id)
                queued = extraction.schedule_generation(conn, ex.key, cur.extract_backfill, conv_id, history=True)
            log.info("rebuild conversation=%s discarded=%d queued=%d", conv_id, discarded, queued)
            return {"discarded": discarded, "queued": {"extract": queued}, "coverage": coverage_view(conn, conv_id)}

    @app.get("/v1/config", dependencies=[Depends(auth)])
    def get_config():
        return runtime.public_view(rt["settings"], rt["overrides"], rt["rules"])

    @app.put("/v1/config", dependencies=[Depends(auth)])
    def put_config(update: dict[str, Any], request: Request):
        clean, errors = runtime.validate_update(update)
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        before_ex, before_pj = rt["extractor"], rt["projection"]
        before_backfill = rt["settings"].extract_backfill
        with request.app.state.pool.connection() as conn:
            runtime.save(conn, clean)
            rebuild(runtime.stored(conn))
            if runtime.PARSERS_KEY in clean:
                rebuild_state(conn, rt["rules"])
            queued = activate(conn, before_ex.key if before_ex else None, before_pj.key if before_pj else None)
            ex = rt["extractor"]
            if ex and before_ex and ex.key == before_ex.key and rt["settings"].extract_backfill != before_backfill:
                # Same generation, different backfill: queue what the new window is missing now, not at
                # the next restart (ADR 0008). Idempotent; a smaller backfill queues nothing.
                queued += extraction.schedule_generation(conn, ex.key, rt["settings"].extract_backfill)
        return {**runtime.public_view(rt["settings"], rt["overrides"], rt["rules"]), "queued_jobs": queued}

    @app.post("/v1/config/test", dependencies=[Depends(auth)])
    def test_config(body: dict[str, Any]):
        cur = rt["settings"]
        kind = body.get("kind")
        if kind == "llm":
            return runtime.test_llm(body.get("url") or cur.llm_url, body.get("model") or cur.llm_model,
                                    body.get("api_key") or cur.llm_api_key, bool(body.get("json_mode", cur.llm_json_mode)))
        if kind == "embeddings":
            return runtime.test_embeddings(body.get("url") or cur.embed_url, body.get("model") or cur.embed_model,
                                           body.get("api_key") or cur.embed_api_key)
        raise HTTPException(status_code=422, detail="kind must be 'llm' or 'embeddings'")

    @app.post("/v1/config/models", dependencies=[Depends(auth)])
    def config_models(body: dict[str, Any]):
        cur = rt["settings"]
        kind = body.get("kind", "llm")
        fallback_key = cur.embed_api_key if kind == "embeddings" else cur.llm_api_key
        return runtime.list_models(body.get("url") or "", body.get("api_key") or fallback_key)

    def inspector_index_html(request: Request, token: str | None, lang: str | None, embed: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            ex_key = rt["active_extractor"]
            pj_key = rt["projection"].key if rt["projection"] else None
            return inspector.index(readmodel.list_conversations(conn), token, job_counts(conn),
                                   {"extraction": generations.describe(conn, ex_key),
                                    "embeddings": generations.describe(conn, pj_key)},
                                   # no generation ever active: "—", not a 0 % that reads as unfinished work
                                   extraction.coverage(conn, ex_key) if ex_key else {},
                                   vectors.coverage(conn, pj_key) if pj_key else {},
                                   lang=inspector.lang_of(lang), embed=embed)

    def inspector_detail_html(conv_id: UUID, request: Request, token: str | None, lang: str | None,
                              embed: bool = False) -> str:
        with request.app.state.pool.connection() as conn:
            conv = readmodel.conversation(conn, conv_id)
            if conv is None or conv["head_commit_id"] is None:
                raise HTTPException(status_code=404, detail="conversation not found")
            head = conv["head_commit_id"]
            ex_key = rt["active_extractor"]
            pj_key = rt["projection"].key if rt["projection"] else None
            return inspector.detail(conv, current_state(conn, head, rt["rules"].version),
                                    readmodel.membership(conn, head, ex_key, pj_key),
                                    readmodel.commits(conn, conv_id), readmodel.traces(conn, conv_id),
                                    fact_versions(conn, head, ex_key)[:300], token, coverage_view(conn, conv_id),
                                    lang=inspector.lang_of(lang), embed=embed)

    @app.get("/inspector", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_index(request: Request, token: str | None = None, lang: str | None = None):
        return inspector_index_html(request, token, lang)

    @app.get("/inspector/c/{conv_id}", response_class=HTMLResponse, dependencies=[Depends(auth)])
    def inspector_detail(conv_id: UUID, request: Request, token: str | None = None, lang: str | None = None):
        return inspector_detail_html(conv_id, request, token, lang)

    # The same pages as body fragments for the plugin panel, which cannot open a browser tab (H15).
    @app.get("/v1/inspector", dependencies=[Depends(auth)])
    def inspector_index_embed(request: Request, lang: str | None = None):
        return {"html": inspector_index_html(request, None, lang, embed=True)}

    @app.get("/v1/inspector/c/{conv_id}", dependencies=[Depends(auth)])
    def inspector_detail_embed(conv_id: UUID, request: Request, lang: str | None = None):
        return {"html": inspector_detail_html(conv_id, request, None, lang, embed=True)}

    return app


def app_factory() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
