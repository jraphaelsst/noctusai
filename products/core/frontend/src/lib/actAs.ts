/**
 * Core admin "Organizações" — act-as-org client + react-query hooks.
 *
 * Contract (Round 2): superadmin-only endpoints
 *   GET    /api/admin/orgs                 → OrgRow[]
 *   POST   /api/admin/act-as               → {session_id, redirect_url}
 *   GET    /api/admin/act-as/history?limit → audit list
 *
 * The HTTP client arrives through `ActAsApiContext` (default: the app `api`),
 * so tests render with a fake client instead of module mocks. Loading flags
 * follow the two-signal rule: `showSkeleton = isPending && !data`,
 * `isRefreshing = isFetching && !!data`.
 */
import { createContext, createElement, useContext, type ReactNode } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from './api';

export interface LicensedProduct {
  slug: string;
  nome: string;
  url_base: string;
}

export interface OrgRow {
  id: string;
  nome: string;
  slug: string;
  owner_email: string | null;
  licensed_products: LicensedProduct[];
}

export interface ActAsStartInput {
  org_id: string;
  product_slug: string;
  reason?: string;
}

export interface ActAsStartResult {
  session_id: string;
  redirect_url: string;
}

/** Normalised history row (the contract only says "audit list"). */
export interface ActAsHistoryRow {
  id: string;
  at: string | null;
  action: string;
  org: string | null;
  product: string | null;
  reason: string | null;
  actor: string | null;
}

export interface HttpClient {
  get: <T = unknown>(path: string, params?: Record<string, unknown>) => Promise<T>;
  post: <T = unknown>(path: string, body?: unknown) => Promise<T>;
}

function str(v: unknown): string | null {
  return typeof v === 'string' && v ? v : null;
}

/** Accept a bare array or an `{items|data|history}` envelope; tolerate field-name variants. */
export function normalizeHistory(raw: unknown): ActAsHistoryRow[] {
  const list: unknown[] = Array.isArray(raw)
    ? raw
    : Array.isArray((raw as any)?.items)
      ? (raw as any).items
      : Array.isArray((raw as any)?.data)
        ? (raw as any).data
        : Array.isArray((raw as any)?.history)
          ? (raw as any).history
          : [];
  return list.map((r, i) => {
    const o = (r ?? {}) as Record<string, any>;
    const d = (o.details ?? o.metadata ?? {}) as Record<string, any>;
    return {
      id: str(o.id) ?? str(o.session_id) ?? String(i),
      at: str(o.created_at) ?? str(o.started_at) ?? str(o.ts),
      action: str(o.action) ?? 'act_as.start',
      org: str(o.org_nome) ?? str(d.org_nome) ?? str(o.target_org_id) ?? str(d.target_org_id),
      product: str(o.entry_product_slug) ?? str(o.product_slug) ?? str(d.product_slug) ?? str(d.entry_product_slug),
      reason: str(o.reason) ?? str(d.reason),
      actor: str(o.actor_email) ?? str(o.superadmin_email) ?? str(o.user_email) ?? str(o.actor_id) ?? str(o.superadmin_id),
    };
  });
}

export interface ActAsApi {
  orgs: () => Promise<OrgRow[]>;
  start: (input: ActAsStartInput) => Promise<ActAsStartResult>;
  history: (limit?: number) => Promise<ActAsHistoryRow[]>;
}

export function createActAsApi(http: HttpClient): ActAsApi {
  return {
    orgs: () => http.get<OrgRow[]>('/api/admin/orgs'),
    start: (input) => http.post<ActAsStartResult>('/api/admin/act-as', input),
    history: async (limit = 50) =>
      normalizeHistory(await http.get('/api/admin/act-as/history', { limit })),
  };
}

const ActAsApiContext = createContext<ActAsApi>(createActAsApi(api as unknown as HttpClient));

export function ActAsApiProvider({ value, children }: { value: ActAsApi; children: ReactNode }) {
  return createElement(ActAsApiContext.Provider, { value }, children);
}

export function useActAsApi(): ActAsApi {
  return useContext(ActAsApiContext);
}

const KEY = ['core-act-as'] as const;

export function useAdminOrgs() {
  const a = useActAsApi();
  return useQuery({ queryKey: [...KEY, 'orgs'], queryFn: a.orgs });
}

export function useActAsHistory(enabled: boolean) {
  const a = useActAsApi();
  return useQuery({
    queryKey: [...KEY, 'history'],
    queryFn: () => a.history(),
    enabled,
    placeholderData: (previous) => previous,
  });
}

export function useStartActAs() {
  const a = useActAsApi();
  return useMutation({ mutationFn: (input: ActAsStartInput) => a.start(input) });
}
