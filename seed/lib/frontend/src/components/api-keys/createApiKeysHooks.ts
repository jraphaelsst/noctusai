/**
 * `createApiKeysHooks(api, options?)` — org-scoped, operator-settable API
 * keys (TanStack Query v5).
 *
 * Lifted from `products/social-wiring` (`Settings.tsx` "Chaves de API" tab +
 * `hooks/useSettings.ts:604-704`), which wraps its
 * `backend/app/routers/settings_router.py` `/api/settings/api-keys*` trio:
 *
 *   GET    {basePath}            → ApiKeysStatus (every managed key + state)
 *   PUT    {basePath}/{key}      → { value } → ApiKeyStatus (write, admin-gated backend-side)
 *   DELETE {basePath}/{key}      → ApiKeyStatus (drop this org's LOCAL override)
 *   POST   {basePath}/{key}/test → ApiKeyTestResult (live probe)
 *
 * `basePath` defaults to `/api/settings/api-keys` (the social-wiring route) —
 * override it if a product mounts the router elsewhere.
 *
 * A key never comes back over the wire: `hint` is the only display echo
 * (last-4 for a secret, full value for a non-secret), and `source` says
 * WHICH tier answered (`local` / `platform` / `env` / `null`) so a DELETE
 * that leaves the platform tier still answering can say so honestly instead
 * of claiming the key is gone.
 *
 * 🔴 A write path (PUT/DELETE) can 503 when the server has no
 * `ENCRYPTION_KEY` configured — that is a config gap, not a validation
 * error, and the caller should render it distinctly (`err.status === 503`
 * from `@noctusai/lib/api`'s `ApiError`) rather than a generic "failed to
 * save". `ApiKeysPanel` does this; a consumer building its own UI on top of
 * this factory should too.
 *
 * Same injection pattern as `createLLMHooks` / `createWhatsAppConnectionsHooks`:
 * the product passes its own authenticated `createApiClient()`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApiClient } from '../../api';

// ---------------------------------------------------------------------------
// Types — mirror app/schemas/settings.py (ApiKeyOptionOut / ApiKeyStatus /
// ApiKeysStatus / ApiKeyUpdate / ApiKeyTestResult) verbatim.
// ---------------------------------------------------------------------------

/** Which tier answered. `local` = this product's encrypted store. */
export type ApiKeySource = 'local' | 'platform' | 'env';

/** One allowed value of a CHOICE setting, as the UI should label it. */
export interface ApiKeyOption {
  value: string;
  label: string;
  description: string;
}

export interface ApiKeyStatus {
  key: string;
  label: string;
  description: string;
  is_secret: boolean;
  testable: boolean;
  input_type: string;
  placeholder: string;
  configured: boolean;
  /**
   * Non-empty makes this a CHOICE, not a free-text field: render a switch
   * over these instead of an input. Empty for every ordinary key.
   */
  options: ApiKeyOption[];
  /**
   * What the product behaves as when the setting was never saved — what a
   * CHOICE control should show as selected in that case.
   */
  default: string | null;
  /**
   * Display-only. Last 4 characters for a secret (`...b3f9`); the value in
   * full for a non-secret (an e-mail). NEVER the secret itself.
   */
  hint: string | null;
  /** `null` = configured nowhere. */
  source: ApiKeySource | null;
  /** Only ever set for the `local` tier. */
  updated_at: string | null;
}

export interface ApiKeysStatus {
  items: ApiKeyStatus[];
  total: number;
}

export interface ApiKeyTestResult {
  key: string;
  success: boolean;
  /** Operator-facing, render verbatim (pt-BR on the social-wiring backend). */
  message: string;
}

export interface ApiKeySave {
  key: string;
  value: string;
}

export interface CreateApiKeysHooksOptions {
  /** Default `/api/settings/api-keys`. */
  basePath?: string;
}

const DEFAULT_BASE_PATH = '/api/settings/api-keys';

export function createApiKeysHooks(
  api: ApiClient,
  options: CreateApiKeysHooksOptions = {},
) {
  const basePath = options.basePath ?? DEFAULT_BASE_PATH;
  const QUERY_KEY = ['api-keys', basePath] as const;

  /**
   * GET {basePath}. Read is intentionally ungated here — the SAME split
   * social-wiring's backend uses (read open to any authenticated org
   * member, only writes admin-gated); mount the panel behind the caller's
   * own admin/owner check if a stricter read gate is wanted.
   *
   * 🔴 TWO loading signals, never `isLoading` and never a bare `isFetching`:
   * `showSkeleton` is true only on the first load; `isRefreshing` is the
   * quiet indicator for a refetch over data already on screen (a save
   * invalidates this query, and gating on `isFetching` alone would blank a
   * populated list on every save).
   */
  function useApiKeys() {
    const query = useQuery({
      queryKey: QUERY_KEY,
      queryFn: () => api.get<ApiKeysStatus>(basePath),
    });
    return {
      ...query,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
    };
  }

  /**
   * PUT {basePath}/{key}. Write-only: the backend never echoes the value
   * back, so the caller must clear its own input on success rather than
   * re-populate from the response.
   */
  function useSaveApiKey() {
    const qc = useQueryClient();
    return useMutation<ApiKeyStatus, unknown, ApiKeySave>({
      mutationFn: ({ key, value }) =>
        api.put<ApiKeyStatus>(`${basePath}/${encodeURIComponent(key)}`, { value }),
      onSuccess: (data) => {
        toast.success(`${data.label} salva com sucesso.`);
        void qc.invalidateQueries({ queryKey: QUERY_KEY });
      },
      onError: (err: any) => {
        toast.error(
          err?.status === 503
            ? 'Servidor sem chave de criptografia configurada (ENCRYPTION_KEY ausente).'
            : err?.message ?? 'Falha ao salvar a chave.',
        );
      },
    });
  }

  /**
   * DELETE {basePath}/{key}. Drops this org's LOCAL override only — the
   * response is the RE-RESOLVED status, so when the platform/env tier
   * still answers the toast says the key is still active instead of
   * claiming it was removed.
   */
  function useRemoveApiKey() {
    const qc = useQueryClient();
    return useMutation<ApiKeyStatus, unknown, string>({
      mutationFn: (key) =>
        api.delete<ApiKeyStatus>(`${basePath}/${encodeURIComponent(key)}`),
      onSuccess: (data) => {
        if (data.configured) {
          toast.success(
            `${data.label}: override local removido — ainda configurada fora deste produto.`,
          );
        } else {
          toast.success(`${data.label} removida.`);
        }
        void qc.invalidateQueries({ queryKey: QUERY_KEY });
      },
      onError: (err: any) => {
        toast.error(
          err?.status === 503
            ? 'Servidor sem chave de criptografia configurada (ENCRYPTION_KEY ausente).'
            : err?.message ?? 'Falha ao remover a chave.',
        );
      },
    });
  }

  /**
   * POST {basePath}/{key}/test. Probes the value the WORKFLOWS would
   * resolve, so a green result means THIS org's real usage will work — not
   * that some key somewhere is valid. A failed probe is a normal outcome
   * (`success: false` + a message to render inline), not a thrown error.
   */
  function useTestApiKey() {
    return useMutation<ApiKeyTestResult, unknown, string>({
      mutationFn: (key) =>
        api.post<ApiKeyTestResult>(`${basePath}/${encodeURIComponent(key)}/test`, {}),
      onSuccess: (data) => {
        if (data.success) toast.success(data.message);
        else toast.error('Teste falhou', { description: data.message });
      },
      onError: (err: any) => {
        toast.error('Teste falhou', {
          description:
            err?.status === 503
              ? 'Servidor sem chave de criptografia configurada (ENCRYPTION_KEY ausente).'
              : err?.message ?? 'Erro desconhecido.',
        });
      },
    });
  }

  return { useApiKeys, useSaveApiKey, useRemoveApiKey, useTestApiKey };
}

export type ApiKeysHooks = ReturnType<typeof createApiKeysHooks>;
