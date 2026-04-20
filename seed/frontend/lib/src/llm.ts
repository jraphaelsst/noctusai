/**
 * LLM provider hooks for NoctusAI products.
 *
 * Wraps the seed-framework's `/api/llm/*` router (created by
 * `create_standard_routers()` in every product) and Core's
 * `/api/platform/credentials` endpoint. Products get the whole LLM UX
 * surface — provider/model selection, preferences, credential management —
 * by importing these hooks.
 *
 * `api` is injected so each product can use its own `createApiClient()`
 * (authenticated, configured for its backend). Same pattern as
 * `createCrudHooks`.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApiClient } from './api';

// ---------------------------------------------------------------------------
// Types — mirror the backend response shapes
// ---------------------------------------------------------------------------

export interface LLMProviderInfo {
  provider: string;          // "openai" | "anthropic" | "gemini"
  configured: boolean;       // key present for this caller's org / platform
  stub: boolean;             // provider body is a stub, not a real SDK call
}

export interface LLMModelInfo {
  id: string;                // e.g. "gpt-4o-mini"
  label?: string;            // human label (optional — defaults to id)
  stub: boolean;
  kind?: string;             // "chat" | "embedding" | "audio" | "vision"
}

export interface LLMPreferences {
  provider: string | null;
  chat_model: string | null;
  embedding_model: string | null;
}

export interface CredentialStatus {
  masked: string | null;
  scope: 'org' | 'platform' | null;
}

export type CredentialsState = Record<string, CredentialStatus>;

export interface SetCredentialsBody {
  openai?: string | null;
  anthropic?: string | null;
  gemini?: string | null;
}

// ---------------------------------------------------------------------------
// Hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export function createLLMHooks(api: ApiClient) {
  function useLLMProviders() {
    return useQuery<LLMProviderInfo[]>({
      queryKey: ['llm', 'providers'],
      queryFn: () => api.get('/api/llm/providers'),
      staleTime: 60 * 1000,
    });
  }

  function useLLMModels(provider?: string | null, kind?: string) {
    return useQuery<LLMModelInfo[]>({
      queryKey: ['llm', 'models', provider, kind],
      queryFn: () =>
        api.get('/api/llm/models', {
          ...(provider ? { provider } : {}),
          ...(kind ? { kind } : {}),
        }),
      enabled: !!provider,
      staleTime: 5 * 60 * 1000,
    });
  }

  function useLLMPreferences() {
    return useQuery<LLMPreferences>({
      queryKey: ['llm', 'preferences'],
      queryFn: () => api.get('/api/llm/preferences'),
      staleTime: 30 * 1000,
    });
  }

  function useUpdateLLMPreferences() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: LLMPreferences) => api.put('/api/llm/preferences', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['llm', 'preferences'] });
      },
    });
  }

  return {
    useLLMProviders,
    useLLMModels,
    useLLMPreferences,
    useUpdateLLMPreferences,
  };
}

/**
 * Core-only hooks for the `/api/platform/credentials` endpoint.
 *
 * The `api` client here must point at Core (not a product) since only Core
 * exposes the credential CRUD surface. Products deep-link into Core for
 * key management rather than duplicating the UI.
 */
export function createLLMCredentialsHooks(coreApi: ApiClient) {
  function useLLMCredentials() {
    return useQuery<CredentialsState>({
      queryKey: ['llm', 'credentials'],
      queryFn: () => coreApi.get('/api/platform/credentials'),
      staleTime: 60 * 1000,
    });
  }

  function useUpdateLLMCredentials() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: SetCredentialsBody) =>
        coreApi.put('/api/platform/credentials', body),
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['llm', 'credentials'] });
        queryClient.invalidateQueries({ queryKey: ['llm', 'providers'] });
      },
    });
  }

  return { useLLMCredentials, useUpdateLLMCredentials };
}
