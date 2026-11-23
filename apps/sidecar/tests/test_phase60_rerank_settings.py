"""PHASE-60 S5 (ADR 0084 items 4, 6, 7): the reranker's settings, its key as a credential, and the archive's refusal.

No recall wiring here: these tests only check that the reranker is configured, redacted, bound to its host and never
archived. Nothing calls a reranker."""

from __future__ import annotations

import pytest

from nmos_sidecar import rerank
from nmos_sidecar.config import Settings

RERANK_ENV = ("NMOS_RERANK_URL", "NMOS_RERANK_MODEL", "NMOS_RERANK_API_KEY", "NMOS_RERANK_TIMEOUT_MS",
              "NMOS_RERANK_FORMAT")


@pytest.fixture
def clean_env(monkeypatch):
    for name in RERANK_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_the_defaults_leave_the_reranker_off(clean_env):
    s = Settings()
    assert (s.rerank_url, s.rerank_model, s.rerank_api_key) == ("", "", "")
    assert s.rerank_timeout_ms == rerank.DEFAULT_TIMEOUT_MS == 600
    assert s.rerank_format == "standard"


def test_the_environment_sets_every_field(clean_env):
    clean_env.setenv("NMOS_RERANK_URL", "http://rerank.test/v1")
    clean_env.setenv("NMOS_RERANK_MODEL", "rerank-a")
    clean_env.setenv("NMOS_RERANK_API_KEY", "rk-env-0123456789")
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", "900")
    clean_env.setenv("NMOS_RERANK_FORMAT", "standard")
    s = Settings()
    assert (s.rerank_url, s.rerank_model, s.rerank_api_key) == ("http://rerank.test/v1", "rerank-a", "rk-env-0123456789")
    assert (s.rerank_timeout_ms, s.rerank_format) == (900, "standard")


def test_an_empty_environment_value_is_the_default(clean_env):
    """The compose files pass an unset variable as an empty string."""
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", "")
    clean_env.setenv("NMOS_RERANK_FORMAT", "")
    s = Settings()
    assert (s.rerank_timeout_ms, s.rerank_format) == (rerank.DEFAULT_TIMEOUT_MS, "standard")


@pytest.mark.parametrize("value", ["49", "5001", "0", "-1"])
def test_a_timeout_out_of_range_is_refused_at_startup(clean_env, value):
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", value)
    with pytest.raises(ValueError, match="NMOS_RERANK_TIMEOUT_MS"):
        Settings()


@pytest.mark.parametrize("value", ["50", "5000"])
def test_the_timeout_bounds_are_accepted(clean_env, value):
    clean_env.setenv("NMOS_RERANK_TIMEOUT_MS", value)
    assert Settings().rerank_timeout_ms == int(value)


@pytest.mark.parametrize("value", ["systemone", "Standard", "other"])
def test_an_unknown_format_is_refused_at_startup(clean_env, value):
    clean_env.setenv("NMOS_RERANK_FORMAT", value)
    with pytest.raises(ValueError, match=r"NMOS_RERANK_FORMAT must be standard, not"):
        Settings()


def test_the_format_and_timeout_are_checked_for_every_settings(clean_env):
    with pytest.raises(ValueError, match="NMOS_RERANK_FORMAT"):
        Settings(rerank_format="other")
    with pytest.raises(ValueError, match="NMOS_RERANK_TIMEOUT_MS"):
        Settings(rerank_timeout_ms=10)
