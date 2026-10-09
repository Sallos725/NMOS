// SHA-256 via crypto.subtle. A secure page (HTTPS or localhost) has it; a LAN address over plain HTTP does not, and the
// request path says so before calling here (failure.ts, ARCHITECTURE H8 as measured on v1.13.0).

export async function sha256Hex(text: string): Promise<string> {
  return sha256HexOf(new TextEncoder().encode(text));
}

/** The SHA-256 of bytes (an archive's chunk, PHASE-38). */
export async function sha256HexOf(bytes: BufferSource): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
