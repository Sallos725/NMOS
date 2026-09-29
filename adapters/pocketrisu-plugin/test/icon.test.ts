import { describe, expect, it } from 'vitest';
import { NMOS_ICON, namedIcon } from '../src/icon';

describe('NMOS icon', () => {
  it('is decoration beside a visible name', () => {
    expect(NMOS_ICON).toContain('aria-hidden="true"');
    expect(NMOS_ICON).not.toContain('<title>');
  });

  it('carries its name, escaped, where it is shown alone', () => {
    const icon = namedIcon('NMOS <"기억"> & co');
    expect(icon).toContain('role="img" aria-label="NMOS &lt;&quot;기억&quot;&gt; &amp; co"');
    expect(icon).toContain('<title>NMOS &lt;&quot;기억&quot;&gt; &amp; co</title>');
    expect(icon).not.toContain('aria-hidden');
  });
});
