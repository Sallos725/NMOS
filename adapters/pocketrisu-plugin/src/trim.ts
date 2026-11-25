// Pure prompt trimming (Phase 60 S1, ADR 0083 item 7): conservatively drops pre-boundary
// dialogue from a copy of the outgoing prompt; never mutates inputs or throws.

import { estimateTokens } from './budget';
import { selectedContent } from './manifest';
import { activeStartIndex, anchorOf, cleanText, contentText, isActive, latestUserIndex, markerCount, matchPromptToHost,
  MIN_ANCHOR, userTurnIndex } from './prompt';
import type { HostMessage, PromptMessage } from './types';

export type TrimReason = 'format';

export interface TrimResult {
  prompt: PromptMessage[];
  dropped: number;
  savedTokens: number;
  reason: TrimReason | null;
}

/**
 * The only keys a dropped prompt message may carry: a plain text turn and the per-message bookkeeping the host
 * itself puts on every chat message it builds (`memo`, the message's id; `attr`; `thoughts`, the reasoning the host
 * split out of that same message), and the other keys its `OpenAIChat` type allows on a chat message (`name`,
 * `removable`, `cachePoint`). Source reading of the host at v1.17.0 (`OpenAIChat` and the chat loop in
 * `src/ts/process/index.svelte.ts`), not a runtime observation: allowing them only lets a message be dropped with
 * its own bookkeeping, so it is safe whether or not they are there. A cache point on a dropped message moves to the
 * first message kept after the dropped run, so the prompt keeps one where the host asked for it (source reading
 * only: the host's cache-point setting marks messages counted from the end). Any other key
 * (`multimodals`: the message carries images; tool calls; …) means the message is more than its text and nothing is
 * dropped.
 */
const DROPPABLE_KEYS: ReadonlySet<string> = new Set(['role', 'content', 'memo', 'attr', 'thoughts', 'name', 'removable',
  'cachePoint']);

function sameText(prompt: PromptMessage[], hostMessages: HostMessage[], p: number, i: number): boolean {
  const m = prompt[p];
  if (!m || typeof m.content !== 'string') return false;
  const sent = cleanText(m.content);
  if (!sent) return false;
  return sent === cleanText(selectedContent(hostMessages[i]));
}

/**
 * Applies the sidecar's `trim.keep_from_id` boundary to a copy of `prompt`.
 * On any ambiguity, layout mismatch, or malformed input, refuses conservatively with
 * `{ prompt, dropped: 0, savedTokens: 0, reason: 'format' }` (returning the same reference).
 */
export function trimPrompt(
  prompt: PromptMessage[],
  hostMessages: HostMessage[],
  keepFromId: string,
): TrimResult {
  const refuse = (): TrimResult => ({ prompt, dropped: 0, savedTokens: 0, reason: 'format' });
  if (!Array.isArray(prompt) || !Array.isArray(hostMessages) || typeof keepFromId !== 'string' || !keepFromId) {
    return refuse();
  }

  try {
    // A message whose content is neither text nor parts is a shape this does not know: drop nothing.
    if (prompt.some((m) => m != null && typeof m.content !== 'string' && !Array.isArray(m.content))) return refuse();

    // Messages before a "Cut Messages for AI" cut are never sent (HOST-FACTS S8b).
    const start = activeStartIndex(hostMessages);
    const active = (i: number) => i >= start && isActive(hostMessages[i]);

    const b = hostMessages.findIndex(
      (m, i) => active(i) && m?.chatId != null && String(m.chatId) === keepFromId,
    );
    if (b < 0) return refuse();

    if (b > latestUserIndex(hostMessages)) return refuse();

    const turn = userTurnIndex(prompt, hostMessages);
    if (turn < 0) return refuse();

    const pairs = matchPromptToHost(prompt, hostMessages);
    const matched = new Set(pairs.values());
    let lowestMatched = Infinity;
    for (const k of matched) if (k < lowestMatched) lowestMatched = k;
    // A system block no chat message matched (a lorebook entry or author's note the host put at a depth, between two
    // chat messages) is not dialogue: walked past and kept, never dropped.
    const injected = (p: number, i: number) => prompt[p]?.role === 'system' && !matched.has(p)
      && !sameText(prompt, hostMessages, p, i);

    let K = turn;
    for (const [hostIdx, promptIdx] of pairs) {
      if (hostIdx >= b && promptIdx < K) K = promptIdx;
    }

    // Newest anchor-matched active host message before the boundary.
    let j = -1;
    for (let i = b - 1; i >= start; i -= 1) {
      if (active(i) && pairs.has(i)) {
        j = i;
        break;
      }
    }
    if (j < 0) return refuse();

    const jPrompt = pairs.get(j);
    if (jPrompt === undefined) return refuse();

    // Prompt index -> host index for every candidate dropped message.
    const run = new Map<number, number>([[jPrompt, j]]);

    // Short messages (under the anchor size, so never matched) between j and b: placed by exact text, in order.
    let q = jPrompt + 1;
    for (let i = j + 1; i < b; i += 1) {
      if (!active(i)) continue;
      if (pairs.has(i)) return refuse();
      while (q < K && injected(q, i)) q += 1;
      if (q < K && sameText(prompt, hostMessages, q, i)) {
        run.set(q, i);
        q += 1;
      } else {
        break;
      }
    }

    // Walk back from j: each older active host message must sit right before the run (past injected blocks, only while
    // a matched chat message lies further back: never out of the chat, onto a preset's own blocks above it).
    let p = jPrompt - 1;
    for (let i = j - 1; i >= start; i -= 1) {
      if (!active(i)) continue;
      while (p > lowestMatched && injected(p, i)) p -= 1;
      if (pairs.has(i)) {
        if (pairs.get(i) === p) {
          run.set(p, i);
          p -= 1;
          continue;
        }
        break;
      }
      if (p >= 0 && sameText(prompt, hostMessages, p, i)) {
        run.set(p, i);
        p -= 1;
        continue;
      }
      break;
    }

    // Contiguity: every anchor-matched host message before the boundary must be inside the run.
    for (const [hostIdx, promptIdx] of pairs) {
      if (hostIdx < b && !run.has(promptIdx)) return refuse();
    }

    if (run.size === 0) return refuse();

    // The pointer match stops after a few consecutive misses (a request script that rewrote several turns), so
    // older chat messages may still be in the prompt unmatched: dropping the run would leave them before a hole.
    // Refuse when any older active host message long enough to anchor still has its anchor before the run.
    let runStart = Infinity;
    let runOldest = Infinity;
    for (const [k, hostIdx] of run) {
      if (k < runStart) runStart = k;
      if (hostIdx < runOldest) runOldest = hostIdx;
    }
    const before = prompt.slice(0, runStart).map((m) => cleanText(contentText(m?.content)));
    if (before.length > 0) {
      for (let i = runOldest - 1; i >= start; i -= 1) {
        if (!active(i)) continue;
        const text = cleanText(selectedContent(hostMessages[i]));
        if (text.length < MIN_ANCHOR) continue;
        const anchor = anchorOf(text);
        if (before.some((t) => t.includes(anchor))) return refuse();
      }
    }

    // Validate every dropped prompt message.
    let savedTokens = 0;
    for (const [k, hostIdx] of run) {
      const m = prompt[k];
      if (!m || (m.role !== 'user' && m.role !== 'assistant')) return refuse();
      if (typeof m.content !== 'string') return refuse();
      if (Object.keys(m).some((key) => !DROPPABLE_KEYS.has(key))) return refuse();
      // A marker the chat message itself holds is its text (it mentions the placeholder); any other is a preset's.
      if (markerCount(m.content) > markerCount(selectedContent(hostMessages[hostIdx]))) return refuse();
      if (k >= K || k >= turn) return refuse();
      const sent = cleanText(m.content).length;
      const own = cleanText(selectedContent(hostMessages[hostIdx])).length;
      if (sent > 1.25 * own + 64) return refuse();
      savedTokens += estimateTokens(m.content);
    }

    // A boundary message too short to anchor, merged by a preset into the prompt message before it, passes the size
    // allowance and would be dropped with it. Refuse when the newest dropped message, after its own host message's
    // text, still holds the boundary's text (a merged later message follows the own text). When the own text is not
    // there verbatim, the remainder cannot be isolated, so the whole message is searched.
    let newest = -1;
    for (const k of run.keys()) if (k > newest) newest = k;
    const boundary = cleanText(selectedContent(hostMessages[b]));
    if (boundary) {
      const sent = cleanText(prompt[newest]?.content);
      const own = cleanText(selectedContent(hostMessages[run.get(newest) as number]));
      const at = own ? sent.lastIndexOf(own) : -1;
      const tail = at >= 0 ? sent.slice(at + own.length) : sent;
      if (tail.includes(boundary)) return refuse();
    }

    // The newest cache point among the dropped messages moves to the first message kept after the run.
    let point: unknown;
    let pointAt = -1;
    for (const k of run.keys()) {
      const value = prompt[k]?.cachePoint;
      if (value !== undefined && value !== null && value !== false && k > pointAt) {
        point = value;
        pointAt = k;
      }
    }
    const out: PromptMessage[] = [];
    let moved = pointAt < 0;
    for (let idx = 0; idx < prompt.length; idx += 1) {
      if (run.has(idx)) continue;
      const m = prompt[idx] as PromptMessage;
      if (!moved && idx > newest) {
        moved = true;
        const own = m?.cachePoint;
        if (m && typeof m === 'object' && (own === undefined || own === null || own === false)) {
          out.push({ ...m, cachePoint: point });
          continue;
        }
      }
      out.push(m);
    }
    return { prompt: out, dropped: run.size, savedTokens, reason: null };
  } catch {
    return refuse();
  }
}

/**
 * Whether trimming can apply to this prompt at all, before the sidecar is asked for a boundary (so a request never
 * gets a packet built for a cut the prompt cannot take): the smallest cut, right after the oldest chat message the
 * prompt holds before the latest user turn, must trim. Every later cut drops that message too.
 */
export function canTrimPrompt(prompt: PromptMessage[], hostMessages: HostMessage[]): boolean {
  try {
    if (!Array.isArray(prompt) || !Array.isArray(hostMessages)) return false;
    const latest = latestUserIndex(hostMessages);
    const turn = userTurnIndex(prompt, hostMessages);
    if (latest < 0 || turn < 0) return false;
    let oldest = -1;
    for (const [hostIdx, promptIdx] of matchPromptToHost(prompt, hostMessages)) {
      if (hostIdx < latest && promptIdx < turn && (oldest < 0 || hostIdx < oldest)) oldest = hostIdx;
    }
    if (oldest < 0) return false;
    for (let i = oldest + 1; i <= latest; i += 1) {
      if (!isActive(hostMessages[i])) continue;
      const id = hostMessages[i]?.chatId;
      return id != null && trimPrompt(prompt, hostMessages, String(id)).reason === null;
    }
    return false;
  } catch {
    return false;
  }
}
