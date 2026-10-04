/**
 * Structured field diff for JSON version content. Pure — no React.
 * Nested objects flatten to dotted paths (`a.b`); arrays and scalars are
 * leaves compared by deep equality.
 */
export type FieldChangeKind = 'added' | 'removed' | 'changed' | 'unchanged';

export interface FieldChange {
  path: string;
  kind: FieldChangeKind;
  before?: unknown;
  after?: unknown;
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function flattenContent(
  value: unknown,
  prefix = '',
  out: Record<string, unknown> = {},
): Record<string, unknown> {
  if (isPlainObject(value) && Object.keys(value).length > 0) {
    for (const [k, v] of Object.entries(value)) {
      flattenContent(v, prefix ? `${prefix}.${k}` : k, out);
    }
  } else if (prefix) {
    out[prefix] = value;
  }
  return out;
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Diff two content objects; result is sorted by path, unchanged included. */
export function diffContent(
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined,
): FieldChange[] {
  const a = flattenContent(before ?? {});
  const b = flattenContent(after ?? {});
  const paths = Array.from(new Set([...Object.keys(a), ...Object.keys(b)])).sort();
  return paths.map((path): FieldChange => {
    const inA = path in a;
    const inB = path in b;
    if (inA && !inB) return { path, kind: 'removed', before: a[path] };
    if (!inA && inB) return { path, kind: 'added', after: b[path] };
    return deepEqual(a[path], b[path])
      ? { path, kind: 'unchanged', before: a[path], after: b[path] }
      : { path, kind: 'changed', before: a[path], after: b[path] };
  });
}

export function hasChanges(changes: FieldChange[]): boolean {
  return changes.some((c) => c.kind !== 'unchanged');
}
