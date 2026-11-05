/**
 * `createApiTokensHooks(api, options?)` — machine-to-machine (`noc_`) API tokens (TanStack Query v5).
 *
 * The client side of the seed token routes (`noctusai_seed.auth_router`):
 *
 *   GET    {basePath}              → ApiTokenItem[]   (the org's tokens, revoked included; never a secret)
 *   GET    {basePath}/scopes       → { scopes, strict } (the SERVER allow-list — the only scopes a mint may name)
 *   POST   {basePath}              → MintedApiToken   (the raw secret, shown ONCE)
 *   POST   {basePath}/{id}/rotate  → MintedApiToken   (successor; the old token is revoked server-side)
 *   DELETE {basePath}/{id}         → 204              (soft revoke)
 *
 * Writes go into the list cache the moment the server answers (skill noc-cache-writes): a mint lands on top,
 * a rotation revokes the old row and adds the new one, a revoke stamps `revoked_at` at once.
 *
 * The raw secret exists only in the mutation result — it is never cached or put in a query key.
 *
 * `mfa_required` (403) is a NAMED refusal: {@link tokenRefusalMessage} turns it, and the other known refusals,
 * into pt-BR copy so a screen never shows a bare status code.
 */
import { useQuery } from '@tanstack/react-query';
import { listOps, useCacheWriteMutation } from '../../cache-writes';
import { ApiError, type ApiClient } from '../../api';

export interface ApiTokenItem {
  id: string;
  label: string;
  /** First 12 characters of the secret (`noc_` + 8 hex) — the only part the server keeps. */
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  /** `null` = never expires. */
  expires_at: string | null;
  service_account_id: string | null;
}

export interface MintedApiToken {
  id: string;
  label: string;
  /** The raw secret. Shown once; the server keeps only its hash. */
  token: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  service_account_id?: string | null;
}

export interface TokenScopes {
  scopes: string[];
  strict: boolean;
}

export interface MintTokenInput {
  label: string;
  scopes: string[];
  /** Days until expiry (server cap: 90). `null` = no expiry (explicit, audited choice). */
  expiresInDays: number | null;
  serviceAccountId?: string | null;
}

export interface CreateApiTokensHooksOptions {
  /** Default `/api/settings/api-tokens`. */
  basePath?: string;
}

const DEFAULT_BASE_PATH = '/api/settings/api-tokens';

/** `noc_` + 8 hex → first 4 + last 4 of what the server stores, e.g. `noc_••••3a4f`. */
export function maskTokenPrefix(prefix: string): string {
  if (prefix.length <= 8) return prefix;
  return `${prefix.slice(0, 4)}••••${prefix.slice(-4)}`;
}

/** pt-BR copy for a token write that the server refused (or that failed). */
export function tokenRefusalMessage(err: unknown, fallback = 'Não foi possível concluir a operação.'): string {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: unknown } | undefined)?.detail;
    if (detail === 'mfa_required') {
      return 'Gerar tokens exige verificação em duas etapas (MFA) e esta sessão não passou por ela. Verifique sua identidade e tente de novo.';
    }
    if (err.code === 'platform_admin_required') return 'Apenas administradores da plataforma gerenciam tokens.';
    if (detail === 'service_account_not_found') return 'A conta de serviço escolhida não existe ou está desativada.';
    if (detail === 'service_accounts_unsupported') return 'Este produto não usa contas de serviço.';
    if (err.status === 422 && typeof detail === 'string' && detail.startsWith('unknown token scopes')) {
      return `Escopo não permitido: ${detail.replace('unknown token scopes: ', '')}.`;
    }
    if (err.status === 403) return 'Você não tem permissão para gerenciar tokens.';
    if (err.status === 404) return 'Token não encontrado — talvez já tenha sido revogado.';
    return err.message || fallback;
  }
  return err instanceof Error && err.message ? err.message : fallback;
}

const toItem = (m: MintedApiToken): ApiTokenItem => ({
  id: m.id,
  label: m.label,
  prefix: m.prefix,
  scopes: m.scopes,
  created_at: m.created_at,
  last_used_at: null,
  revoked_at: null,
  expires_at: m.expires_at,
  service_account_id: m.service_account_id ?? null,
});

export function createApiTokensHooks(api: ApiClient, options: CreateApiTokensHooksOptions = {}) {
  const basePath = options.basePath ?? DEFAULT_BASE_PATH;
  const LIST_KEY = ['api-tokens', basePath] as const;
  const SCOPES_KEY = ['api-tokens', basePath, 'scopes'] as const;

  /**
   * 🔴 Two loading signals, never `isLoading`: `showSkeleton` only before the first data; `isRefreshing` is the
   * quiet indicator for a refetch over a list already on screen.
   */
  function useApiTokens() {
    const query = useQuery({
      queryKey: LIST_KEY,
      queryFn: () => api.get<ApiTokenItem[]>(basePath),
    });
    return {
      ...query,
      showSkeleton: query.isPending && !query.data,
      isRefreshing: query.isFetching && !!query.data,
    };
  }

  /** The scope choices for the mint form — from the server's allow-list, never free text. */
  function useTokenScopes() {
    return useQuery({
      queryKey: SCOPES_KEY,
      queryFn: () => api.get<TokenScopes>(`${basePath}/scopes`),
      staleTime: 5 * 60_000,
    });
  }

  function useMintToken() {
    return useCacheWriteMutation<MintedApiToken, MintTokenInput>({
      mutationFn: (input) =>
        api.post<MintedApiToken>(basePath, {
          label: input.label,
          scopes: input.scopes,
          ...(input.expiresInDays === null
            ? { no_expiry: true }
            : { expires_at: new Date(Date.now() + input.expiresInDays * 86_400_000).toISOString() }),
          ...(input.serviceAccountId ? { service_account_id: input.serviceAccountId } : {}),
        }),
      // Newest first, like the server's list.
      targets: [{ queryKey: LIST_KEY, commit: (old: ApiTokenItem[] | undefined, saved) => listOps.replace(old, saved.id, toItem(saved), 'prepend') }],
    });
  }

  function useRotateToken() {
    return useCacheWriteMutation<MintedApiToken, string>({
      mutationFn: (id) => api.post<MintedApiToken>(`${basePath}/${encodeURIComponent(id)}/rotate`, {}),
      targets: (id) => [
        {
          queryKey: LIST_KEY,
          commit: (old: ApiTokenItem[] | undefined, saved) =>
            listOps.replace(
              listOps.patch(old, id, { revoked_at: new Date().toISOString() }),
              saved.id,
              toItem(saved),
              'prepend',
            ),
        },
      ],
    });
  }

  function useRevokeToken() {
    return useCacheWriteMutation<unknown, string>({
      mutationFn: (id) => api.delete(`${basePath}/${encodeURIComponent(id)}`),
      targets: [
        {
          queryKey: LIST_KEY,
          optimistic: (old: ApiTokenItem[] | undefined, id) =>
            listOps.patch(old, id, { revoked_at: new Date().toISOString() }),
        },
      ],
    });
  }

  return { useApiTokens, useTokenScopes, useMintToken, useRotateToken, useRevokeToken };
}

export type ApiTokensHooks = ReturnType<typeof createApiTokensHooks>;
