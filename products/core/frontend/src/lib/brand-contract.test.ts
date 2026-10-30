import { describe, it, expect } from 'vitest';
import {
  contrastPairs, contrastRatio, hexToHslTriplet, hslTripletToHex, validateBrandFiles, HSL_RE,
} from './brand-contract';

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);

describe('validateBrandFiles', () => {
  it('accepts the contract formats', () => {
    expect(validateBrandFiles([], [file('a.md'), file('b.PDF'), file('c.png'), file('d.woff2')])).toEqual([]);
  });
  it('refuses svg, unknown formats, oversize, count and total', () => {
    expect(validateBrandFiles([], [file('x.svg')])[0]).toMatch(/SVG/);
    expect(validateBrandFiles([], [file('x.exe')])[0]).toMatch(/formato/);
    expect(validateBrandFiles([], [file('big.pdf', 10 * 1024 * 1024 + 1)])[0]).toMatch(/10 MB/);
    const eleven = Array.from({ length: 11 }, (_, i) => file(`f${i}.md`));
    expect(validateBrandFiles([], eleven)).toHaveLength(1);
    const a = file('a.pdf', 10 * 1024 * 1024);
    const b = file('b.pdf', 10 * 1024 * 1024);
    const c = file('c.pdf', 6 * 1024 * 1024);
    expect(validateBrandFiles([a, b], [c])[0]).toMatch(/25 MB/);
  });
});

describe('color helpers', () => {
  it('round-trips hex <-> HSL triplet within rounding', () => {
    const t = hexToHslTriplet('#336699');
    expect(HSL_RE.test(t)).toBe(true);
    expect(hslTripletToHex(t)).toBe('#336699');
  });
  it('black on white is 21:1; same color is 1:1', () => {
    expect(contrastRatio('0 0% 0%', '0 0% 100%')).toBeCloseTo(21, 0);
    expect(contrastRatio('10 50% 50%', '10 50% 50%')).toBeCloseTo(1, 5);
  });
  it('derives pairs from token names, not a list', () => {
    const pairs = contrastPairs({ background: 'a', foreground: 'b', primary: 'c', 'primary-foreground': 'd', border: 'e' });
    expect(pairs).toEqual([{ fg: 'primary-foreground', bg: 'primary' }, { fg: 'foreground', bg: 'background' }]);
  });
});
