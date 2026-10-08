import { describe, expect, it } from 'vitest';
import { failureKind, INSECURE_ERROR } from '../src/failure';

describe('why a request could not reach NMOS (pre-0.4.0 audit F24, F25, F27)', () => {
  it('tells a stopped sidecar, a token, a refused host and an insecure page apart', () => {
    expect(failureKind('deadline during /v1/sync/reconcile')).toBe('deadline');
    expect(failureKind(INSECURE_ERROR)).toBe('insecure');
    expect(failureKind('/v1/sync/reconcile -> HTTP 401: unauthorized')).toBe('unauthorized');
    expect(failureKind("/v1/health -> HTTP 400: host '10.0.0.2:8790' not allowed without a token: add it to NMOS_ALLOWED_HOSTS or set NMOS_AUTH_TOKEN"))
      .toBe('host_refused');
    expect(failureKind('TypeError: Failed to fetch')).toBe('unreachable');
    expect(failureKind('connect ECONNREFUSED 127.0.0.1:8790')).toBe('unreachable');
    expect(failureKind('/v1/retrieve -> HTTP 502')).toBe('unreachable');  // a proxy with nothing behind it
    expect(failureKind('/v1/retrieve -> HTTP 500: boom')).toBe('other');  // reached, and it failed
    expect(failureKind('sidecar rejected bodies')).toBe('other');
    expect(failureKind(undefined)).toBeNull();
  });
});
