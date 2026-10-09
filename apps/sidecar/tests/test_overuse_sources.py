"""Only eligible replies influence whether supportive memory rests, live and at a historical request."""

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import overuse
from simchat import SimChat
from test_sidecar_integration import sync

ECHO = "Hana is a cartographer of the northern sea."


@pytest.mark.parametrize("state", ["active", "disabled", "comment", "before-cut"])
def test_reply_echo_uses_eligible_sources_and_the_metadata_as_of_replay(migrated, state):
    chat = SimChat()
    chat.user("What now?")
    chat.reply(ECHO)
    chat.user("Continue.")
    if state == "disabled":
        chat.disable(1, True)
    elif state == "comment":
        chat.messages[1]["isComment"] = True
    elif state == "before-cut":
        chat.disable(2, "allBefore")

    def read(before=None):
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref = %s",
                                (chat.id,)).fetchone()["head_commit_id"]
            return overuse.reply_text(conn, head, 0, before)

    with make_client(migrated) as client:
        sync(client, chat)
        with psycopg.connect(migrated) as conn:
            recorded_at = conn.execute("SELECT clock_timestamp()").fetchone()[0]
        expected = ECHO if state == "active" else None
        assert read() == expected and read(recorded_at) == expected
        line = {"kind": "fact", "ref": {"assertion": 1}, "placed": True, "content": ECHO}
        recent = overuse.of_ledger([line], read(), ("What now?", ""))
        assert bool(recent.echoed) == (state == "active")
        assert bool(overuse.tired([recent, recent])) == (state != "active")

        # A later metadata edit makes an inactive reply eligible, or an active reply ineligible.
        chat.disable(1, state == "active")
        chat.messages[1]["isComment"] = False
        chat.disable(2, False)
        sync(client, chat)
        assert read() == (None if state == "active" else ECHO)
        assert read(recorded_at) == expected
        chat.edit(1, "The harbour was quiet.")
        sync(client, chat)
        assert read(recorded_at) == expected
        chat.edit(1, ECHO)  # undo reuses the older immutable revision
        sync(client, chat)
        assert read(recorded_at) == expected
        chat.messages[1], chat.messages[2] = chat.messages[2], chat.messages[1]
        sync(client, chat)
        assert read() is None and read(recorded_at) == expected
