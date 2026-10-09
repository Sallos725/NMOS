// Why NMOS could not help with a request, from its error text (pre-0.4.0 audit F24, F25, F27). Pure; the Status tab,
// the one-time alert and the request path share it.

/** The error a request records when the page has no Web Crypto: PocketRisu opened over plain HTTP on a LAN
 * address (H8 as measured on v1.13.0: the plugin loads, but `crypto.subtle` is missing). */
export const INSECURE_ERROR = 'insecure page: open PocketRisu over HTTPS or localhost (crypto.subtle is missing)';

export type FailureKind = 'deadline' | 'insecure' | 'unauthorized' | 'host_refused' | 'unreachable' | 'other';

/** Whether this page can hash (the manifest needs SHA-256). */
export function secureContext(): boolean {
  return typeof globalThis.crypto?.subtle?.digest === 'function';
}

/** What an error says went wrong. A sidecar that answered with an HTTP status is reachable unless the status is a
 * proxy's 502/503/504; an error without a status (a refused connection, a DNS failure, a closed port) is not. */
export function failureKind(error: string | null | undefined): FailureKind | null {
  if (!error) return null;
  if (error.startsWith('deadline')) return 'deadline';
  if (error.startsWith('insecure page')) return 'insecure';
  const status = /-> HTTP (\d{3})/.exec(error);
  if (status) {
    if (status[1] === '401') return 'unauthorized';
    if (status[1] === '400' && /not allowed without a token/.test(error)) return 'host_refused';
    return ['502', '503', '504'].includes(status[1] as string) ? 'unreachable' : 'other';
  }
  // Errors of NMOS's own protocol name the sidecar; anything else is the connection failing.
  return /^sidecar /.test(error) ? 'other' : 'unreachable';
}
