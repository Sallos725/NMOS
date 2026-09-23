"""Synthetic PocketRisu-shaped chats for sidecar integration tests.

Mirrors the plugin's manifest/body construction (hash format v1). Host *behavior* in these tests
follows the recorded a14c911 evidence (H4–H6); the recorded fixtures themselves drive
test_reconcile_fixtures.py.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from nmos_sidecar.canonical import normalize_text, revision_hash


def selected(message: dict[str, Any]) -> str:
    swipes = message.get("swipes")
    sid = message.get("swipeId")
    if isinstance(swipes, list) and isinstance(sid, int) and 0 <= sid < len(swipes):
        return swipes[sid]
    return message.get("data", "")


def metadata(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "chatId": message.get("chatId"),
        "role": message.get("role"),
        "saying": message.get("saying"),
        "name": message.get("name"),
        "otherUser": message.get("otherUser"),
        "isComment": message.get("isComment"),
        "disabled": message.get("disabled"),
        "swipeId": message.get("swipeId"),
        "generationId": (message.get("generationInfo") or {}).get("generationId"),
        "swipeCount": len(message.get("swipes") or []),
        "specialComments": [message["data"]] if str(message.get("data", "")).startswith("{{specialcomment::") else [],
    }


class SimChat:
    def __init__(self, chat_id: str | None = None) -> None:
        self.id = chat_id or str(uuid.uuid4())
        self.messages: list[dict[str, Any]] = []

    def complete_turns(self) -> int:
        """Turns the user continued from (ADR 0008), for chats without comments or disabled messages."""
        n, replied = 0, False
        for m in self.messages:
            if m["role"] == "user":
                n, replied = n + replied, False
            else:
                replied = True
        return n

    # --- host actions (behavior per HOST-FACTS) ---
    def user(self, text: str) -> dict[str, Any]:
        msg = {"role": "user", "data": text, "chatId": str(uuid.uuid4())}
        self.messages.append(msg)
        return msg

    def reply(self, text: str) -> dict[str, Any]:
        gen = str(uuid.uuid4())
        msg = {"role": "char", "data": text, "chatId": gen, "generationInfo": {"generationId": gen}}
        self.messages.append(msg)
        return msg

    def reroll(self, text: str) -> dict[str, Any]:
        old = self.messages.pop()
        gen = str(uuid.uuid4())
        msg = {"role": "char", "data": text, "chatId": gen, "generationInfo": {"generationId": gen},
               "swipes": [*(old.get("swipes") or [old["data"]]), text]}
        msg["swipeId"] = len(msg["swipes"]) - 1
        self.messages.append(msg)
        return msg

    def swipe(self, index: int) -> None:
        msg = self.messages[-1]
        msg["swipeId"] = index
        msg["data"] = msg["swipes"][index]

    def cont(self, more: str) -> None:
        msg = self.messages[-1]
        msg["data"] += more
        if msg.get("swipes"):
            msg["swipes"][msg["swipeId"]] = msg["data"]
        msg["generationInfo"] = {"generationId": str(uuid.uuid4())}

    def edit(self, index: int, text: str) -> None:
        msg = self.messages[index]
        msg["data"] = text
        if msg.get("swipes"):
            msg["swipes"][msg["swipeId"]] = text

    def delete(self, index: int) -> None:
        del self.messages[index]

    def disable(self, index: int, value: bool | str = True) -> None:
        self.messages[index]["disabled"] = value

    def branch(self, index: int, name: str = "Chat") -> "SimChat":
        other = SimChat()
        for msg in self.messages[: index + 1]:
            clone = copy.deepcopy(msg)
            clone["chatId"] = str(uuid.uuid4())  # reissueMessageIds (H5); generationInfo kept
            other.messages.append(clone)
        other.messages.append({
            "role": "char", "isComment": True, "disabled": True, "chatId": str(uuid.uuid4()),
            "data": f"{{{{specialcomment::branchedfrom::{self.id}::{name}::{self.messages[index]['chatId']}::}}}}",
        })
        return other

    # --- plugin view ---
    def manifest(self) -> dict[str, Any]:
        out = []
        for msg in self.messages:
            meta = metadata(msg)
            out.append({
                "host_logical_id": msg["chatId"],
                "revision_hash": revision_hash(meta, normalize_text(selected(msg))),
                "role": msg["role"],
                "name": msg.get("name"),
                "disabled": msg.get("disabled"),
                "is_comment": msg.get("isComment"),
                "swipe_id": msg.get("swipeId"),
                "swipe_count": meta["swipeCount"],
                "generation_id": meta["generationId"],
                "special_comments": meta["specialComments"],
            })
        return {"host": "pocketrisu", "chat_id": self.id, "hash_version": 1, "messages": out}

    def bodies(self, needed: list[dict[str, str]]) -> list[dict[str, Any]]:
        wanted = {(n["host_logical_id"], n["revision_hash"]) for n in needed}
        out = []
        for msg in self.messages:
            meta = metadata(msg)
            content = normalize_text(selected(msg))
            key = (msg["chatId"], revision_hash(meta, content))
            if key in wanted:
                out.append({"host_logical_id": key[0], "revision_hash": key[1], "content": content, "metadata": meta})
        return out
