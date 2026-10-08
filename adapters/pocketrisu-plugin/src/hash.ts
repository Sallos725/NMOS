// SHA-256 via crypto.subtle, which is available wherever a V3 plugin can run (ARCHITECTURE H8).

export async function sha256Hex(text: string): Promise<string> {
  return sha256HexOf(new TextEncoder().encode(text));
}

/** The SHA-256 of bytes (an archive's chunk, PHASE-38). */
export async function sha256HexOf(bytes: BufferSource): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}
