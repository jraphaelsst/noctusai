/**
 * Platform token settings (core `/api/admin/tokens/*`, migration 099) — typed hooks.
 *
 * `mfa_required` is the platform switch "MFA para gerar tokens" (`platform_settings.exigir_mfa_para_tokens`,
 * OFF by default: the owner does not use MFA yet). The write follows noc-cache-writes: the server's answer is
 * committed into the settings entry the moment it arrives.
 */
import { useQuery } from '@tanstack/react-query';
import { useCacheWriteMutation } from '@noctusai/lib/cache-writes';
import type { ApiClient } from '@noctusai/lib/api';

export interface TokenSettings {
  mfa_required: boolean;
}

export interface ServiceAccount {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
}

export const tokenSettingsKeys = {
  settings: ['core', 'tokens', 'settings'] as const,
  serviceAccounts: ['core', 'tokens', 'service-accounts'] as const,
};

export function createTokenSettingsHooks(http: Pick<ApiClient, 'get' | 'put'>) {
  function useTokenSettings() {
    const query = useQuery<TokenSettings>({
      queryKey: tokenSettingsKeys.settings,
      queryFn: async () => (await http.get<{ data: TokenSettings }>('/api/admin/tokens/settings')).data,
      retry: false,
    });
    return { ...query, showSkeleton: query.isPending && !query.data };
  }

  function useSetMfaRequired() {
    return useCacheWriteMutation<TokenSettings, boolean>({
      mutationFn: async (mfa_required) =>
        (await http.put<{ data: TokenSettings }>('/api/admin/tokens/settings', { mfa_required })).data,
      targets: [{ queryKey: tokenSettingsKeys.settings, commit: (_old: TokenSettings | undefined, saved) => saved }],
    });
  }

  function useServiceAccounts() {
    return useQuery<ServiceAccount[]>({
      queryKey: tokenSettingsKeys.serviceAccounts,
      queryFn: async () =>
        (await http.get<{ data: ServiceAccount[] }>('/api/admin/tokens/service-accounts')).data ?? [],
      staleTime: 5 * 60_000,
      retry: false,
    });
  }

  return { useTokenSettings, useSetMfaRequired, useServiceAccounts };
}

export type TokenSettingsHooks = ReturnType<typeof createTokenSettingsHooks>;
