"""The compose files hand the sidecar and the worker the same settings (audit A-03).

Both processes derive generation keys from their settings; a variable passed to one only (as
`NMOS_LLM_JSON_MODE` once was) makes them disagree, and the worker never claims the sidecar's jobs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_ONLY = {"NMOS_DB_PASSWORD", "NMOS_DB_PORT", "NMOS_SIDECAR_BIND", "NMOS_SIDECAR_PORT", "NMOS_VERSION"}


def service_env(text: str) -> dict[str, str]:
    """Each service's `environment:` as written: an anchor alias (`*name`) or an inline block."""
    out: dict[str, str] = {}
    for m in re.finditer(r"^  (\w+):\n(.*?)(?=^  \w+:\n|^\S|\Z)", text.split("\nservices:\n", 1)[1], re.M | re.S):
        env = re.search(r"^    environment:(.*?)(?=^    \w|\Z)", m[2], re.M | re.S)
        if env:
            out[m[1]] = env[1].strip()
    return out


def anchor_vars(text: str) -> set[str]:
    block = re.search(r"^x-nmos-env: &nmos-env\n((?:  .*\n)+)", text, re.M)
    assert block, "no x-nmos-env anchor"
    return set(re.findall(r"^  (NMOS_\w+):", block[1], re.M))


def documented() -> set[str]:
    names = set(re.findall(r"`(NMOS_\w+)`", (ROOT / "README.md").read_text()))
    names |= set(re.findall(r"^#?\s*(NMOS_\w+)=", (ROOT / ".env.example").read_text(), re.M))
    return names - COMPOSE_ONLY


@pytest.mark.parametrize("path", ["docker-compose.yml", "deploy/docker-compose.yml"])
def test_sidecar_and_worker_share_one_environment(path):
    text = (ROOT / path).read_text()
    env = service_env(text)
    assert env["sidecar"] == env["worker"] == "*nmos-env"
    missing = documented() - anchor_vars(text)
    assert not missing, f"{path} does not pass {sorted(missing)}"
