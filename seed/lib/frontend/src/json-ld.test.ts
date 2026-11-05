import { describe, it, expect } from 'vitest';
import { safeJsonLd } from './json-ld';

describe('safeJsonLd', () => {
  const payload = { text: '</script><script>alert(1)</script> a & b \u2028\u2029 >' };

  it('emits no raw <, >, & or line separators', () => {
    const out = safeJsonLd(payload);
    expect(out).not.toMatch(/[<>&\u2028\u2029]/);
    expect(out.toLowerCase()).not.toContain('</script');
  });

  it('round-trips to the identical value', () => {
    expect(JSON.parse(safeJsonLd(payload))).toEqual(payload);
  });
});
