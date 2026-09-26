"""Host check without a token (audit A-05, ADR 0030).

A DNS-rebinding page reaches a loopback or LAN sidecar under the attacker's own domain name. Without a
token, the sidecar answers only to IP addresses, `localhost` and single-label names (`nmos`, `sidecar`),
plus the names in NMOS_ALLOWED_HOSTS."""

from __future__ import annotations

import pytest

from conftest import make_client
from nmos_sidecar.api import host_allowed


@pytest.mark.parametrize("header", ["127.0.0.1:8790", "localhost:8790", "localhost", "[::1]:8790",
                                    "192.168.219.103:6003", "100.101.1.2", "nmos:8790", "sidecar", "testserver"])
def test_addresses_localhost_and_single_label_names_pass(header):
    assert host_allowed(header, ())


@pytest.mark.parametrize("header", ["evil.example.com", "evil.example.com:8790", "rebind.attacker.net:6003",
                                    "localhost.attacker.net", ""])
def test_domain_names_need_the_allow_list(header):
    assert not host_allowed(header, ())


def test_the_allow_list_takes_exact_names_and_subdomain_wildcards():
    allowed = ("risu.example.com", "*.ts.net")
    assert host_allowed("RISU.example.com:443", allowed)
    assert host_allowed("box.tail1234.ts.net", allowed)
    assert not host_allowed("ts.net.evil.com", allowed)
    assert not host_allowed("other.example.com", allowed)
    assert host_allowed("anything.example.org", ("*",))


def test_without_a_token_a_foreign_host_is_refused(migrated):
    with make_client(migrated, auth_token="") as c:
        assert c.get("/v1/health", headers={"host": "127.0.0.1:8790"}).status_code == 200
        res = c.get("/v1/health", headers={"host": "rebind.attacker.net:8790"})
        assert res.status_code == 400 and "NMOS_ALLOWED_HOSTS" in res.json()["detail"]
        # The settings API that sends the stored key elsewhere is behind the same check.
        assert c.post("/v1/config/models", json={"url": "http://x/v1"},
                      headers={"host": "rebind.attacker.net"}).status_code == 400
    with make_client(migrated, auth_token="", allowed_hosts=("risu.example.com",)) as c:
        assert c.get("/v1/health", headers={"host": "risu.example.com"}).status_code == 200


def test_with_a_token_the_token_decides(migrated):
    with make_client(migrated) as c:  # conftest sets a token
        assert c.get("/v1/health", headers={"host": "risu.example.com"}).status_code == 200
        c.headers.pop("Authorization")
        assert c.get("/v1/health", headers={"host": "risu.example.com"}).status_code == 401
