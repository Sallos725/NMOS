// A sidecar on this machine is reached directly from the browser. Anything else (LAN IP, Docker
// service name) goes through the PocketRisu server: an HTTPS page cannot fetch http:// directly, and
// a Docker name only resolves on the server. PocketRisu routes local-network hosts via /proxy2.
export function routeFor(url: string, setting: string): 'direct' | 'server' {
  if (setting === 'direct' || setting === 'server') return setting;
  try {
    const host = new URL(url).hostname.replace(/^\[|\]$/g, '');
    return ['localhost', '127.0.0.1', '::1'].includes(host) ? 'direct' : 'server';
  } catch {
    return 'direct';
  }
}
