"""ADR 0037: the sidecar knows the plugin build it ships and says whether the plugin in use is that one."""

from __future__ import annotations

from conftest import make_client
from nmos_sidecar import plugin
from simchat import SimChat


def reconcile(c, chat: SimChat, build: str | None) -> None:
    body = {**chat.manifest(), **({"plugin_build": build} if build else {})}
    assert c.post("/v1/sync/reconcile", json=body).status_code == 200


def test_the_shipped_build_is_read_from_the_plugin_file():
    want = plugin.expected()
    assert want is not None and plugin.BUILD.fullmatch(f"nmos-build:{want}")
    assert f"nmos-build:{want}" in plugin.plugin_file().read_text(encoding="utf-8")


def test_the_inspector_says_whether_the_plugin_in_use_is_the_sidecars(migrated):
    want = plugin.expected()
    with make_client(migrated) as c:
        page = lambda: c.get("/inspector", params={"lang": "en"}).text
        assert c.get("/v1/health").json()["plugin"] == {"expected": want, "seen": []}
        assert "none has synced since this sidecar started" in page()
        chat = SimChat()
        chat.user("hello")
        reconcile(c, chat, None)  # a plugin too old to send its build
        assert "The plugin is not this sidecar's build: in use no build id" in page()
        assert "/v1/plugin/nmos-pocketrisu.js" in page()
        reconcile(c, chat, want)
        assert f"Plugin: the sidecar's build {want}" in page()
        assert "An older plugin (no build id (an older plugin)) synced from another tab" in page()
        seen = c.get("/v1/health").json()["plugin"]["seen"]
        assert [(s["build"], s["matches"]) for s in seen] == [(want, True), (None, False)]
        reconcile(c, chat, "not-a-build")  # anything else counts as no build id
        assert c.get("/v1/health").json()["plugin"]["seen"][0]["build"] is None
        got = c.get("/v1/plugin/nmos-pocketrisu.js")
        assert got.status_code == 200 and f"nmos-build:{want}".encode() in got.content
