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


@pytest.mark.parametrize("path", ["docker-compose.yml", "deploy/docker-compose.yml"])
def test_compose_defaults_are_the_sidecar_defaults(path):
    """A default written in a compose file overrides the sidecar's own: `NMOS_PACKET_POLICY` stayed `packet-v4` there
    while the sidecar's default moved to `packet-v5` and `packet-v6` (Phase 11), so a compose install never got them."""
    import dataclasses

    from nmos_sidecar.config import Settings

    base = Settings()
    names = {f.name for f in dataclasses.fields(Settings)}
    text = (ROOT / path).read_text()
    wrong = {}
    for name, default in re.findall(r"^  (NMOS_\w+): \$\{NMOS_\w+:-([^}]*)\}", text, re.M):
        attr = name.removeprefix("NMOS_").lower()
        if attr not in names or name in ("NMOS_CORS_ORIGINS", "NMOS_ALLOWED_HOSTS"):  # lists: set per install
            continue
        ours = getattr(base, attr)
        theirs = (default != "0") if isinstance(ours, bool) else type(ours)(default) if default else type(ours)()
        if theirs != ours:
            wrong[name] = (default, ours)
    assert wrong == {}, f"{path}: compose default differs from the sidecar's: {wrong}"
