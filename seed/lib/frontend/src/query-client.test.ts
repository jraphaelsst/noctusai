/**
 * createQueryClient — the global error toast, plus its per-status opt-out.
 *
 * `meta.suppressErrorToastStatuses` lets a query swallow the toast for
 * exactly the status codes it names (a hook's own "expected 404, not a
 * transient failure" shape — see social-wiring's `useImovel`); any other
 * status, or a non-`ApiError` failure, still surfaces loudly.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

import { createQueryClient } from './query-client';
import { ApiError } from './api';

beforeEach(() => {
  toastError.mockClear();
});

async function runQuery(
  key: string,
  queryFn: () => Promise<unknown>,
  meta?: Record<string, unknown>,
) {
  const qc = createQueryClient();
  await qc.fetchQuery({ queryKey: [key], queryFn, retry: false, meta }).catch(() => {});
}

describe('createQueryClient — global error toast', () => {
  it('toasts a query error when no suppression meta is set', async () => {
    await runQuery('no-meta', async () => {
      throw new ApiError(404, 'não encontrado');
    });

    expect(toastError).toHaveBeenCalledTimes(1);
  });

  it('suppresses the toast when the error status is listed in suppressErrorToastStatuses', async () => {
    await runQuery(
      'suppressed-404',
      async () => {
        throw new ApiError(404, 'não encontrado');
      },
      { suppressErrorToastStatuses: [404] },
    );

    expect(toastError).not.toHaveBeenCalled();
  });

  it('still toasts a status NOT in the suppression list', async () => {
    await runQuery(
      'unsuppressed-500',
      async () => {
        throw new ApiError(500, 'erro interno');
      },
      { suppressErrorToastStatuses: [404] },
    );

    expect(toastError).toHaveBeenCalledTimes(1);
  });

  it('still toasts a non-ApiError failure even when suppression meta is set', async () => {
    await runQuery(
      'network-drop',
      async () => {
        throw new Error('network');
      },
      { suppressErrorToastStatuses: [404] },
    );

    expect(toastError).toHaveBeenCalledTimes(1);
  });
});
