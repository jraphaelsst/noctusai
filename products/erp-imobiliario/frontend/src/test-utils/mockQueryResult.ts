import { vi } from 'vitest';

interface MockQueryResultOverrides<T> {
  data?: T;
  isPending?: boolean;
  isFetching?: boolean;
  isError?: boolean;
  error?: Error | null;
}

/**
 * Minimal TanStack Query `UseQueryResult`-shaped mock for hook-level page
 * tests that stub `@/hooks/use*` directly, bypassing the real QueryClient —
 * mirrors the pattern established in
 * `components/vista/__tests__/ClientesTab.test.tsx`.
 *
 * Absorbed to a shared helper because N≥3 page test files need the exact
 * same three canonical states (KB § PATTERNS/architect/project-execution.md
 * § the recurrence rule; KB § PATTERNS/frontend/lying-loading-state.md for
 * what the three states prove):
 *
 *   - NOT_ARRIVED  — `mockQueryResult({ isPending: true, isFetching: true })`
 *     `data` stays `undefined`. The query has never resolved.
 *   - REAL_ZERO    — `mockQueryResult({ data: <zero-shaped-payload> })`
 *     `isPending`/`isFetching` false. A genuine server-returned zero.
 *   - REFETCHING   — `mockQueryResult({ data: <existing>, isFetching: true })`
 *     `isPending` false, `isFetching` true. A background refetch on top of
 *     data that already exists — must never re-arm a skeleton/lying-zero.
 */
export function mockQueryResult<T>(overrides: MockQueryResultOverrides<T> = {}) {
  return {
    data: undefined,
    isPending: false,
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  };
}

/** A no-op mutation result, for pages that also destructure `useCreateX()` etc. */
export function mockMutationResult(overrides: Record<string, unknown> = {}) {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  };
}
