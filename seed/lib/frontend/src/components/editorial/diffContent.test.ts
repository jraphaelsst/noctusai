import { describe, expect, it } from 'vitest';
import { diffContent, flattenContent, hasChanges } from './diffContent';

describe('diffContent', () => {
  it('flattens nested objects to dotted paths, arrays are leaves', () => {
    expect(flattenContent({ a: { b: 1, c: [1, 2] }, d: 'x' })).toEqual({ 'a.b': 1, 'a.c': [1, 2], d: 'x' });
  });

  it('classifies added / removed / changed / unchanged, sorted by path', () => {
    const r = diffContent({ a: 1, b: 2, c: 3, n: { x: 1 } }, { a: 1, b: 9, d: 4, n: { x: 2 } });
    expect(r).toEqual([
      { path: 'a', kind: 'unchanged', before: 1, after: 1 },
      { path: 'b', kind: 'changed', before: 2, after: 9 },
      { path: 'c', kind: 'removed', before: 3 },
      { path: 'd', kind: 'added', after: 4 },
      { path: 'n.x', kind: 'changed', before: 1, after: 2 },
    ]);
  });

  it('compares arrays deeply', () => {
    expect(diffContent({ t: [1, 2] }, { t: [1, 2] })[0].kind).toBe('unchanged');
    expect(diffContent({ t: [1, 2] }, { t: [1, 3] })[0].kind).toBe('changed');
  });

  it('handles null/empty inputs and hasChanges', () => {
    expect(diffContent(null, undefined)).toEqual([]);
    expect(hasChanges(diffContent({ a: 1 }, { a: 1 }))).toBe(false);
    expect(hasChanges(diffContent({}, { a: 1 }))).toBe(true);
  });
});
