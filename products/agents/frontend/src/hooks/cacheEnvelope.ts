/**
 * Cache edits for `{ items: [...] }` / `{ itens: [...] }` envelopes (the shape most
 * agents list endpoints return). Composes with `listOps` from `@noctusai/lib/cache-writes`:
 *
 *     optimistic: (old) => editList(old, "items", (l) => listOps.remove(l, id))
 *
 * An uncached entry (`undefined`) or one without that array passes through untouched,
 * so a `match: 'prefix'` target can never mangle a sibling query that shares the prefix.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function editList<E extends object>(env: E | undefined, field: keyof E & string, fn: (list: any[]) => any[] | undefined): E | undefined {
  if (!env || typeof env !== "object") return env;
  const list = (env as Record<string, unknown>)[field];
  if (!Array.isArray(list)) return env;
  const next = fn(list);
  return next ? { ...env, [field]: next } : env;
}
