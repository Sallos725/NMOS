"""Seed synthetic characters and chats (no owner content) into a stopped PocketRisu save."""
import sqlite3, sys, random
from pathlib import Path
import msgpack
HEAD = b"\x00RISUSAVE\x00\x07"
save = Path(sys.argv[1])
random.seed(7)
PARTS = ["하나는 창가에 앉아 바다 쪽을 바라보았다.", "카이토가 낮은 목소리로 대답했다.", "바람이 불어 등대의 불빛이 흔들렸다.",
         "유이는 지도를 펼쳐 섬의 북쪽 길을 손가락으로 짚었다.", "\"내일은 비가 올지도 몰라.\"", "부두에서 종소리가 두 번 울렸다.",
         "둘은 잠시 말없이 파도 소리를 들었다.", "\"그 열쇠는 아직 네가 가지고 있지?\"", "등잔 기름이 거의 떨어져 가고 있었다."]
def text(i):
    s, out = 0, []
    while s < 150:
        p = random.choice(PARTS); out.append(p); s += len(p) + 1
    return f"({i}) " + " ".join(out)
def chat(cid, name, n):
    msgs = [{"role": "user" if i % 2 == 0 else "char", "data": text(i), "chatId": f"{cid}-{i:05d}", "time": 1790000000000 + i * 60000} for i in range(n)]
    return {"message": msgs, "note": "", "name": name, "id": cid, "fmIndex": -1, "localLore": [], "lastDate": 1790000000000 + n * 60000}
def char(cha, name, chats):
    return {"type": "character", "chaId": cha, "name": name, "image": "", "chatPage": 0, "chats": chats, "chatFolders": [],
            "desc": f"{name}는 작은 섬마을에 사는 합성 캐릭터다.", "personality": "", "scenario": "", "firstMessage": "", "alternateGreetings": [],
            "globalLore": [], "exampleMessage": "", "systemPrompt": "", "postHistoryInstructions": "", "creatorNotes": "", "tags": [],
            "customscript": [], "emotionImages": [], "bias": [], "viewScreen": "none", "sdData": [], "utilityBot": False,
            "additionalAssets": [], "firstMsgIndex": -1, "notes": ""}
chars = [
    char("cha-hana", "하나", [chat("c-hana-s1", "짧은 대화 1", 40), chat("c-hana-10k", "synthetic 10000", 10000), chat("c-hana-5k", "synthetic 5000", 5000), chat("c-hana-s2", "짧은 대화 2", 40)]),
    char("cha-kaito", "카이토", [chat("c-kaito-1", "카이토 1", 40), chat("c-kaito-2", "카이토 2", 40)]),
    char("cha-yui", "유이", [chat("c-yui-1", "유이 1", 40)]),
]
con = sqlite3.connect(save / "risuai.db")
blob = con.execute("SELECT value FROM kv WHERE key='database/database.bin'").fetchone()[0]
if blob.startswith(HEAD):
    db = msgpack.unpackb(blob[len(HEAD):], raw=False, strict_map_key=False)
else:
    print("unexpected header", blob[:24]); sys.exit(1)
persona = {"name": "타쿠미", "personaPrompt": "", "icon": "", "largePortrait": False, "id": "persona-syn"}
db |= {"characters": chars, "characterOrder": [c["chaId"] for c in chars], "personas": [persona], "selectedPersona": 0,
       "username": "타쿠미", "aiModel": "reverse_proxy", "subModel": "reverse_proxy", "forceReplaceUrl": "http://127.0.0.1:9/v1/chat/completions",
       "proxyKey": "stub", "requestLogEnabled": False, "didFirstSetup": True, "useStreaming": False, "maxContext": 8000, "maxResponse": 500}
blob = HEAD + msgpack.packb(db, use_bin_type=True)
con.execute("UPDATE kv SET value=? WHERE key='database/database.bin'", (blob,))
con.execute("DELETE FROM manifest_chunks WHERE manifest_key='database/database.bin'")
con.execute("DELETE FROM kv WHERE key LIKE 'database/dbbackup-%'")
con.commit()
tot = sum(len(m["data"]) for c in chars for ch in c["chats"] for m in ch["message"])
print(f"seeded {len(chars)} characters, {sum(len(c['chats']) for c in chars)} chats, {tot} message chars, {len(blob)} bytes")
