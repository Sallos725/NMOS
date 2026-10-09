# Changes without a cause, on the owner's chats (PHASE-39 step 4)

Measured 2026-10-08, read only (a read-only session on the trial install's database; nothing written), with the code of
this branch and the owner's two card-bound rules as saved on the trial install. Every key of each chat was watched, an
upper bound: the count per kind of key is what a watch list would give. No model is called.

## The two chats

| | Replies with a bar | Keys | Changes between neighbouring bars |
|---|---:|---:|---:|
| Game-like card A | 23 | 23 (16 changed) | 130 |
| Game-like card B | 6 | 9 (5 changed) | 11 |

## Flags

| Kind of key | Keys | Changes | First rules | As merged |
|---|---:|---:|---:|---:|
| A: inventory and equipment | 3 | 16 | 5 | **5** |
| A: resources and stats (money, HP, MP, SP, experience, level, points, two attributes) | 9 | 66 | 2 | **1** |
| A: place, date, time, quests | 4 | 48 | 6 | **0** |
| B: place, time, weather, mood, who is present | 5 | 11 | 2 | 2 |

**The first rules** (Q4 as approved) flagged 15. Seven were not changes without a cause, and the rules changed:

- **A place is not a count** (5). A place's name holds numbers (a floor, a zone, a rank); a move changed its words and
  its numbers, and (ii) read a number change. (ii) now needs the value's words to stay the same: only numbers moved.
- **Money in words** (1). The reply wrote the bar's +1,000,000 in Korean words. The story's numbers now include Korean
  amounts: digits with 만, 억 or 조, and Hangul numerals before a unit of money or count.
- **A revert the story names** (1). After a reroll the place went back to the one two bars before, and the reply
  walks there, naming it. (iii) now leaves out a revert whose key or value the reply names.

One more change came from reading the flags: a Latin key is looked for as a word (a two-letter key was found inside
an English word of the reply).

**As merged**, card A's flags:

- inventory and equipment (5), each an item the story never names: one item gone from the bar for two turns and back
  with nothing said (two flags), and one reply that changed the bar's clothes, armour and weapon while its story
  talked about another piece (three flags);
- one resource back to its maximum after a reroll, the reply's night passing in between: borderline, a dismissal.

Card B's two are a character leaving the scene without being named and a clock moving five minutes: keys a player
would not watch.

Every other change of money, HP, MP, experience, level and points (65 of 66) was named by its reply: the key, the new
number or the difference.

## Reading it

Watching the inventory and equipment keys of card A would have raised 5 flags in 23 replies, each a real disagreement
between the bar and the story; the resources add one borderline flag in 66 changes. Place, time, date and who is
present change on almost every reply and are not worth watching; the guide says so.
