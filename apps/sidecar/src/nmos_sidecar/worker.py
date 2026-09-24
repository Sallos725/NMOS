"""nmos-worker: processes queued jobs (extraction, embedding). Several workers may run concurrently."""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import dict_row

from . import generations, retention
from .config import Settings
from .extraction import claim, extractor, fail, finish, process_extract
from .llm import ChatModel, Embedder, LLMError
from .runtime import effective, stored
from .vectors import process_embed, projection

# kind -> (generation key the handler implements, handler)
Handlers = dict[str, tuple[str, Callable[[psycopg.Connection, dict[str, Any]], str]]]

log = logging.getLogger("nmos.worker")


def handlers(settings: Settings) -> Handlers:
    out: Handlers = {}
    ex = extractor(settings)
    if ex is not None:
        model = ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                          settings.llm_json_mode)
        out["extract"] = (ex.key, lambda conn, job: process_extract(conn, job, model.complete_json, ex,
                                                                     settings.extract_turns))
    pj = projection(settings)
    if pj is not None:
        embedder = Embedder(settings.embed_url, settings.embed_model, settings.embed_api_key)
        out["embed"] = (pj.key, lambda conn, job: process_embed(conn, job, embedder, pj))
    return out


def run_once(conn: psycopg.Connection, jobs: Handlers) -> bool:
    """Process one job of a generation some handler implements. Returns False when none was ready.

    A job queued for another generation (e.g. right after the model was changed in the settings UI,
    before this worker reloaded) is never claimed by this handler; it waits for a matching one.
    """
    job = claim(conn, {kind: key for kind, (key, _) in jobs.items()})
    if job is None:
        return False
    try:
        status = jobs[job["kind"]][1](conn, job)
        finish(conn, job["id"], status)
    except (LLMError, psycopg.Error, ValueError, KeyError) as exc:
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()
        log.warning("job %s (%s) failed attempt %s: %s", job["id"], job["kind"], job["attempts"], exc)
        fail(conn, job, str(exc))
    return True


def prune(conn: psycopg.Connection, trace_days: int) -> None:
    """Derived data only: finished jobs after 7 days, retrieval traces after `trace_days`, and superseded
    embeddings the active projection replaced (O5, ADR 0015); full-manifest host observations are compacted
    losslessly (O5, ADR 0018)."""
    conn.execute("DELETE FROM job WHERE status IN ('done', 'obsolete') AND updated_at < now() - interval '7 days'")
    conn.execute("DELETE FROM retrieval_trace WHERE created_at < now() - make_interval(days => %s)", (trace_days,))
    if pruned := retention.prune_embeddings(conn):
        log.info("superseded embeddings pruned: %d rows", pruned)
    if compacted := retention.compact_observations(conn):
        log.info("host observations compacted: %d", compacted)


def maintenance(settings: Settings, stop: threading.Event, holder: dict[str, Any]) -> None:
    """Reload settings saved from the plugin UI every 30 s; prune derived data every 10 min."""
    last_prune = 0.0
    signature = None
    while not stop.is_set():
        try:
            with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as conn:
                current = effective(settings, stored(conn))
                jobs = handlers(current)
                new_signature = (tuple(sorted((k, key) for k, (key, _) in jobs.items())), current.llm_api_key,
                                 current.embed_api_key, current.llm_timeout_s)
                if new_signature != signature:
                    for gen in (extractor(current), projection(current)):
                        if gen is not None:
                            generations.ensure(conn, gen)  # rows reference their generation
                    holder["jobs"] = jobs
                    signature = new_signature
                    log.info("job generations now: %s", {k: key[:20] for k, (key, _) in jobs.items()}
                             or "none (no LLM/embedding configured)")
                if time.monotonic() - last_prune > 600:
                    prune(conn, settings.trace_retention_days)
                    last_prune = time.monotonic()
        except psycopg.Error as exc:
            log.warning("maintenance skipped: %s", exc)
        stop.wait(30)


def loop(settings: Settings, stop: threading.Event, holder: dict[str, Any]) -> None:
    while not stop.is_set():
        try:
            with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as conn:
                while not stop.is_set():
                    jobs = holder["jobs"]
                    if not jobs or not run_once(conn, jobs):
                        stop.wait(1.0)
        except psycopg.OperationalError as exc:
            log.warning("database unavailable (%s); retrying", exc)
            stop.wait(5.0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    holder: dict[str, Any] = {"jobs": {}}
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    threads = [threading.Thread(target=maintenance, args=(settings, stop, holder), daemon=True)]
    threads += [threading.Thread(target=loop, args=(settings, stop, holder), daemon=True)
                for _ in range(max(1, settings.worker_concurrency))]
    for t in threads:
        t.start()
    log.info("worker started: concurrency=%d", len(threads) - 1)
    while not stop.is_set():
        time.sleep(0.5)
    for t in threads:
        t.join(timeout=10)


if __name__ == "__main__":
    main()
