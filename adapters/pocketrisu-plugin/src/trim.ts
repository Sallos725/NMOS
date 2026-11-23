// Pure prompt trimming (Phase 60 S1, ADR 0083 item 7): conservatively drops pre-boundary
// dialogue from a copy of the outgoing prompt; never mutates inputs or throws.

import { estimateTokens } from './budget';
import { selectedContent } from './manifest';
import { MEMORY_MARKER } from './placement';
import { cleanText, isActive, latestUserIndex, matchPromptToHost, userTurnIndex } from './prompt';
import type { HostMessage, PromptMessage } from './types';

export type TrimReason = 'format';

export interface TrimResult {
  prompt: PromptMessage[];
  dropped: number;
  savedTokens: number;
  reason: TrimReason | null;
}

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
    const b = hostMessages.findIndex(
      (m) => isActive(m) && m?.chatId != null && String(m.chatId) === keepFromId,
    );
    if (b < 0) return refuse();

    if (b > latestUserIndex(hostMessages)) return refuse();

    const turn = userTurnIndex(prompt, hostMessages);
    if (turn < 0) return refuse();

    const pairs = matchPromptToHost(prompt, hostMessages);

    let K = turn;
    for (const [hostIdx, promptIdx] of pairs) {
      if (hostIdx >= b && promptIdx < K) K = promptIdx;
    }

    // Newest anchor-matched active host message before the boundary.
    let j = -1;
    for (let i = b - 1; i >= 0; i -= 1) {
      if (isActive(hostMessages[i]) && pairs.has(i)) {
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
      if (!isActive(hostMessages[i])) continue;
      if (pairs.has(i)) return refuse();
      if (q < K && sameText(prompt, hostMessages, q, i)) {
        run.set(q, i);
        q += 1;
      } else {
        break;
      }
    }

    // Walk back from j: each older active host message must sit right before the run.
    let p = jPrompt - 1;
    for (let i = j - 1; i >= 0; i -= 1) {
      if (!isActive(hostMessages[i])) continue;
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

    // Validate every dropped prompt message.
    let savedTokens = 0;
    for (const [k, hostIdx] of run) {
      const m = prompt[k];
      if (!m || (m.role !== 'user' && m.role !== 'assistant')) return refuse();
      if (typeof m.content !== 'string') return refuse();
      if (m.content.includes(MEMORY_MARKER)) return refuse();
      if (k >= K || k >= turn) return refuse();
      const sent = cleanText(m.content).length;
      const own = cleanText(selectedContent(hostMessages[hostIdx])).length;
      if (sent > 1.25 * own + 64) return refuse();
      savedTokens += estimateTokens(m.content);
    }

    const out = prompt.filter((_, idx) => !run.has(idx));
    return { prompt: out, dropped: run.size, savedTokens, reason: null };
  } catch {
    return refuse();
  }
}
