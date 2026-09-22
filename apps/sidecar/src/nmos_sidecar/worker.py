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

from .config import Settings
from .extraction import claim, fail, finish, process_extract
from .llm import ChatModel, Embedder, LLMError

log = logging.getLogger("nmos.worker")


def handlers(settings: Settings) -> dict[str, Callable[[psycopg.Connection, dict[str, Any]], str]]:
    out: dict[str, Callable[[psycopg.Connection, dict[str, Any]], str]] = {}
    if settings.llm_url and settings.llm_model:
        model = ChatModel(settings.llm_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                          settings.llm_json_mode)
        out["extract"] = lambda conn, job: process_extract(conn, job, model.complete_json, settings.llm_model,
                                                           settings.extract_window)
    if settings.embed_url and settings.embed_model:
        from .vectors import process_embed  # Phase 3

        embedder = Embedder(settings.embed_url, settings.embed_model, settings.embed_api_key)
        out["embed"] = lambda conn, job: process_embed(conn, job, embedder, settings.embed_model)
    return out


def run_once(conn: psycopg.Connection, jobs: dict[str, Callable[[psycopg.Connection, dict[str, Any]], str]]) -> bool:
    """Process one job. Returns False when the queue had nothing ready."""
    job = claim(conn, tuple(jobs))
    if job is None:
        return False
    try:
        status = jobs[job["kind"]](conn, job)
        finish(conn, job["id"], status)
    except (LLMError, psycopg.Error, ValueError, KeyError) as exc:
        if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            conn.rollback()
        log.warning("job %s (%s) failed attempt %s: %s", job["id"], job["kind"], job["attempts"], exc)
        fail(conn, job, str(exc))
    return True


def loop(settings: Settings, stop: threading.Event, jobs: dict) -> None:
    while not stop.is_set():
        try:
            with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=True) as conn:
                while not stop.is_set():
                    if not run_once(conn, jobs):
                        stop.wait(1.0)
        except psycopg.OperationalError as exc:
            log.warning("database unavailable (%s); retrying", exc)
            stop.wait(5.0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings()
    jobs = handlers(settings)
    if not jobs:
        log.info("no LLM or embedding endpoint configured (NMOS_LLM_URL / NMOS_EMBED_URL); idling")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    threads = [threading.Thread(target=loop, args=(settings, stop, jobs), daemon=True)
               for _ in range(max(1, settings.worker_concurrency))] if jobs else []
    for t in threads:
        t.start()
    log.info("worker started: kinds=%s concurrency=%d", sorted(jobs), len(threads))
    while not stop.is_set():
        time.sleep(0.5)
    for t in threads:
        t.join(timeout=10)


if __name__ == "__main__":
    main()
