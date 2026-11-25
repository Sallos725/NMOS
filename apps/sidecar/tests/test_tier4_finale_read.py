"""PHASE-67 part 2 (owner decision 2026-11-25): the author's note and carry read the open turn's finished early
extraction; the request packet never does. Synthetic chats only."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import carry, facts, notes
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_sidecar_integration import recall, sync
from test_tier3_read_ontology import a, current, model_for

PL = "place"
SCRIPT = {
    "t0": [a("하나", "located_in", "항구", None, ot=PL)],
    "t1": [a("하나", "has_status", None, "피곤함")],
    "fin": [a("하나", "located_in", "등대", None, ot=PL),
            a("하나", "knows", None, "등대지기의 비밀", knowledge="limited", known_by=["하나"], hidden_from=["도윤"])],
    "alt": [a("하나", "located_in", "시장", None, ot=PL)],
}


class Finale:
    """A chat whose last reply was synced by its output sync (still provisional) and extracted early."""

    def __init__(self, c, url: str, name: str = "w3-finale") -> None:
        self.c, self.url = c, url
        self.chat = SimChat(name)
        for k in ("t0", "t1"):
            self.chat.user(f"장면 ({k}).")
            self.chat.reply(f"장면 ⟦{k}⟧")
        self.chat.user("마지막 장면.")
        sync(c, self.chat)
        drain(url, model_for(SCRIPT))
        self.chat.reply("하나는 등대에 도착했다. ⟦fin⟧")
        sync(c, self.chat, trigger="output")
        drain(url, model_for(SCRIPT))
        self.cid = conv_id(c, self.chat)

    def view(self, **kw: Any) -> dict[str, Any]:
        with psycopg.connect(self.url, row_factory=dict_row) as conn:
            key = active_generation(conn, "extract").key
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                                (self.cid,)).fetchone()["head_commit_id"]
            return facts.memory_view(conn, head, key, **kw)

    def reroll(self, text: str = "하나는 시장으로 돌아갔다. ⟦alt⟧", output: bool = True) -> None:
        self.chat.messages.pop()  # the host drops the tail before the reroll's request (H14)
        sync(self.c, self.chat)
        self.chat.reply(text)
        sync(self.c, self.chat, trigger="output" if output else "request")
        drain(self.url, model_for(SCRIPT))


def places(view: dict[str, Any]) -> set[str]:
    return {f["object"] for f in current(view, "located_in")}


def test_only_a_read_that_asks_takes_the_finale_and_a_request_never_does(migrated: str):
    with make_client(migrated, **LLM, extract_on_output=True) as c:
        fin = Finale(c, migrated)
        plain, with_finale = fin.view(), fin.view(include_open_turn=True)
        assert places(plain) == {"항구"} and "open_turn" not in plain
        assert places(with_finale) == {"등대"}
        lighthouse = current(with_finale, "located_in")[0]
        assert lighthouse["open_turn"] is True and lighthouse["turn"] == with_finale["open_turn"]["turn"]
        assert not any("open_turn" in f for f in plain["facts"] + plain["assertions"])
        # the finale's secret folds as any turn's: kept from 도윤
        assert any(s["text"].endswith("등대지기의 비밀") and s["open"] == ["도윤"] for s in with_finale["secrets"])
        packet = recall(c, fin.chat, "하나는 어디 있어? 등대", in_context=[])["packet"]["text"]
        assert "등대" not in packet  # /v1/retrieve is unchanged


def test_a_rerolled_or_edited_finale_never_counts(migrated: str):
    with make_client(migrated, **LLM, extract_on_output=True) as c:
        fin = Finale(c, migrated)
        first = fin.view(include_open_turn=True)["open_turn"]["revision"]
        fin.reroll(output=False)  # replaced, and the new reply not extracted early: no finale at all
        view = fin.view(include_open_turn=True)
        assert places(view) == {"항구"} and "open_turn" not in view
        fin.reroll()  # the new reply's own output sync: its own early extraction
        view = fin.view(include_open_turn=True)
        assert places(view) == {"시장"} and view["open_turn"]["revision"] != first


def test_with_the_switch_off_the_option_changes_nothing(migrated: str):
    with make_client(migrated, **LLM) as c:
        fin = Finale(c, migrated)
        assert fin.view(include_open_turn=True) == fin.view() or (
            {k: v for k, v in fin.view(include_open_turn=True).items() if k != "resolution"}
            == {k: v for k, v in fin.view().items() if k != "resolution"})


def test_the_note_reads_the_finale_keeps_its_secret_and_keys_its_cache_by_the_reply(migrated: str):
    with make_client(migrated, **LLM, extract_on_output=True) as c:
        fin = Finale(c, migrated)
        view = fin.view(include_open_turn=True)
        out = notes.make(notes.Ask.of({"sections": ["changed"], "model": False}), view, None, 2, None, "2026-11-25")
        assert out["open_turn"]["revision"] == view["open_turn"]["revision"]
        assert "등대지기의 비밀" not in out["text"]  # secrets off: the finale's kept fact stays out
        assert "open_turn" not in notes.make(notes.Ask.of({"sections": ["changed"], "model": False}), fin.view(), None,
                                             2, None, "2026-11-25")

    calls = []

    def model(system: str, user: str):
        calls.append(1)
        return {"events": "- 하나가 등대에 갔다", "now": ""}, "{}", {"calls": 1}

    notes.clear_cache()
    args = (None, [], view["facts"], [], 3000, model)
    notes.chronicle(*args, finale="rev-a")
    assert notes.chronicle(*args, finale="rev-a")["cached"] is True
    assert notes.chronicle(*args, finale="rev-b")["cached"] is False  # a rerolled reply is a new key
    assert len(calls) == 2


def link_view(url: str, target: str, key: str) -> dict[str, Any]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (target,)).fetchone()
        return facts.memory_view(conn, head["head_commit_id"], key, carried=carry.target_rows(carry.in_force(conn, target)))


def test_a_carry_snapshot_takes_the_finale_and_leaves_it_out_once_the_reply_is_replaced(migrated: str):
    with make_client(migrated, **LLM, extract_on_output=True) as c:
        fin = Finale(c, migrated)
        kept = Finale(c, migrated, name="w3-finale-kept")
        targets = {}
        for name in ("cont", "reg", "kept"):
            t = SimChat(f"w3-carry-{name}")
            t.user("새 이야기.")
            t.reply("둘은 다시 만났다.")
            t.user("계속.")
            sync(c, t)
            targets[name] = conv_id(c, t)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            key = active_generation(conn, "extract").key
            keys = carry.Keys(extractor=key)
            preview = carry.preview(conn, targets["cont"], fin.cid, "continue", None, keys)
            assert preview["open_turn"]["turn"] is not None
            carry.link(conn, targets["cont"], fin.cid, "continue", None, keys)
            carry.link(conn, targets["reg"], fin.cid, "regression", ["하나"], keys)
            carry.link(conn, targets["kept"], kept.cid, "continue", None, keys)
            conn.commit()
            snap = carry.in_force(conn, targets["cont"])["snapshot"]
        assert snap["open_turn"]["revision"]
        assert any(f.get("open_turn") and f["object"] == "등대" for f in snap["facts"])
        view = link_view(migrated, targets["cont"], key)
        assert "등대" in places(view) and view["carried"]["finale"]["stale"] == []
        assert any(x.get("object") == "등대" for x in link_view(migrated, targets["reg"], key)["regression"])

        fin.reroll()  # the source's reply is replaced: the frozen snapshot's finale rows serve no more
        view = link_view(migrated, targets["cont"], key)
        # its rows serve no more; the place it replaced was never in the snapshot (current facts only): relink for it
        assert "등대" not in places(view)
        assert view["carried"]["finale"]["stale"] == view["carried"]["finale"]["revisions"]
        assert not any(x.get("object") == "등대" for x in link_view(migrated, targets["reg"], key)["regression"])

        kept.chat.user("좋아, 계속하자.")  # the source's user answers: the reply is accepted, its rows stay
        sync(c, kept.chat)
        view = link_view(migrated, targets["kept"], key)
        assert "등대" in places(view) and view["carried"]["finale"]["stale"] == []
