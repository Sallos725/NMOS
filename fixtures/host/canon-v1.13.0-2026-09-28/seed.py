"""Seed the isolated PocketRisu v1.13.0 (port 6141) for Phase 14 step 2 with synthetic canon: one character with a
card, a character lorebook (a keyed entry, an always-active entry, a folder and an entry in it), a chat with an
author's note and a local lorebook entry, a bound persona with a prompt, and an enabled module with a lorebook.
The model is the local stub on port 8806. Run with the container stopped, after `first.mjs` opened the fresh instance
once: `uv run --with msgpack python seed.py [messages] [other chat messages]` (msgpack for this script only)."""
import sqlite3
import sys
from pathlib import Path

import msgpack

HERE = Path(__file__).parent
STUB = "http://127.0.0.1:8806/v1/chat/completions"


def lore(id, content, key="", mode="normal", always=False, comment="", folder=None, order=100):
    e = {"key": key, "secondkey": "", "insertorder": order, "comment": comment or id, "content": content, "mode": mode,
         "alwaysActive": always, "selective": False, "extentions": {"risu_case_sensitive": False}, "id": id}
    if folder:
        e["folder"] = folder
    return e


def messages(n: int, tag: str) -> list:
    line = "하나와 타쿠미는 항구를 걸으며 등대와 도서관 이야기를 나누었다. 바람이 차가웠다. "
    return [{"role": "user" if i % 2 == 0 else "char", "data": f"{tag} {i}: {line * 2}", "chatId": f"{tag}-{i}",
             "time": 1790000000000 + i} for i in range(n)]


def main():
    big = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    other = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    chat = {"message": messages(big, "m"), "note": "지금은 한겨울 밤이다.", "name": "canon probe", "id": "p14-chat-1", "fmIndex": -1,
            "localLore": [lore("lore-tunnel", "등대 지하에는 비밀 통로가 있다.", key="비밀 통로")],
            "bindedPersona": "persona-takumi"}
    chats = [chat] + ([{"message": messages(other, "o"), "note": "", "name": "other chat", "id": "p14-chat-2", "fmIndex": -1,
                        "localLore": []}] if other else [])
    char = {"type": "character", "chaId": "p14-hana", "name": "하나", "image": "", "chatPage": 0, "chats": chats,
            "desc": "하나는 항구 마을 등대지기의 딸이다. 하나의 눈은 푸른색이다.",
            "personality": "하나는 밝고 고집이 세다.", "scenario": "겨울의 항구 마을.",
            "firstMessage": "하나가 등대 문을 열었다.", "alternateGreetings": ["하나가 부두에서 손을 흔들었다."],
            "globalLore": [lore("lore-kaito", "카이토는 견습 기사이고 하나의 소꿉친구다.", key="카이토, 카이"),
                           lore("lore-world", "이 세계의 등대는 마법으로 빛난다.", mode="constant", always=True),
                           lore("lore-folder", "", mode="folder", comment="장소"),
                           lore("lore-library", "도서관은 항구 언덕 위에 있다.", key="도서관", folder="lore-folder")],
            "exampleMessage": "", "systemPrompt": "", "postHistoryInstructions": "", "creatorNotes": "", "tags": [],
            "customscript": [], "emotionImages": [], "bias": [], "viewScreen": "none", "sdData": [], "utilityBot": False,
            "additionalAssets": [], "firstMsgIndex": -1}
    module = {"name": "항구 모듈", "description": "", "id": "mod-harbor",
              "lorebook": [lore("lore-market", "어시장은 새벽에만 열린다.", key="시장, 어시장")]}
    persona = {"name": "타쿠미", "personaPrompt": "타쿠미는 항구 신문의 기자다.", "icon": "", "largePortrait": False,
               "id": "persona-takumi"}
    db = {"characters": [char], "characterOrder": ["p14-hana"], "modules": [module], "enabledModules": ["mod-harbor"],
          "personas": [persona], "selectedPersona": 0, "username": "타쿠미", "personaPrompt": persona["personaPrompt"],
          "aiModel": "reverse_proxy", "subModel": "reverse_proxy", "forceReplaceUrl": STUB, "proxyKey": "stub",
          "requestLogEnabled": True, "didFirstSetup": True, "useStreaming": False, "plugins": []}
    blob = b"\x00RISUSAVE\x00\x07" + msgpack.packb(db, use_bin_type=True)
    con = sqlite3.connect(HERE / "save" / "risuai.db")
    n = con.execute("update kv set value=? where key='database/database.bin'", (blob,)).rowcount
    if n != 1:  # open the fresh instance once first (first.mjs): it writes the row this replaces
        con.rollback()
        raise SystemExit(f"expected one database/database.bin row, found {n}; nothing changed")
    con.execute("delete from manifest_chunks where manifest_key='database/database.bin'")
    con.execute("delete from kv where key like 'database/dbbackup-%'")
    con.commit()
    print("seeded", n, len(blob), "bytes")


if __name__ == "__main__":
    sys.exit(main())
