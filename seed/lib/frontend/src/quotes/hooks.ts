/**
 * `createQuotesHooks(api)` — TanStack Query hooks for the staff quotes API (`/api/quotes`);
 * `createQuotesPublicHooks(api)` — the customer's hooks for the public accept link (`/api/public/quotes/{token}`).
 *
 * 🔴 Loading contract (`KB § PATTERNS/frontend/lying-loading-state.md`): every read hook returns
 * `showSkeleton = isPending && !data` (first load only) and `isRefreshing = isFetching && !!data` (indicator only).
 * Never `isLoading`, never a bare `isFetching` gate. The list keeps `placeholderData` across key changes
 * (page / filters / search); the by-id read does NOT (a quote belongs to one customer — never show the previous
 * quote under a new key).
 *
 * Mutations reject with `ApiError` (the caller renders it; `quotesErrorMessage` maps the stable codes) and
 * invalidate every read they can change. The public hooks use a plain-fetch transport (`createFetchTransport`):
 * the token in the URL IS the credential, there is no session.
 */
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { ApiError } from '../api';
import { apiErrorCode, createFetchTransport, errorMessage, keep, signals, type OrganApi } from '../organ-kit/query';
import { defaultQuotesT, type QuotesTranslate } from './i18n';
import type {
  QuoteAcceptance,
  QuoteCalculation,
  QuoteEnvelope,
  QuoteEventRecord,
  QuoteInput,
  QuoteListParams,
  QuotePaginated,
  QuotePatch,
  QuotePublicView,
  QuoteRecord,
  QuoteSendInput,
  QuoteSendResult,
} from './types';

export type QuotesApi = OrganApi;
export { apiErrorCode as quotesApiErrorCode, errorMessage };

const BASE = '/api/quotes';
const PUBLIC_BASE = '/api/public/quotes';

/** Namespaced query keys (exported so hosts can invalidate precisely). */
export const quotesKeys = {
  all: ['quotes'] as const,
  lists: ['quotes', 'list'] as const,
  list: (params: QuoteListParams) => ['quotes', 'list', params] as const,
  detail: (id: string) => ['quotes', 'detail', id] as const,
  events: (id: string) => ['quotes', 'events', id] as const,
  acceptance: (id: string) => ['quotes', 'acceptance', id] as const,
  public: (token: string) => ['quotes', 'public', token] as const,
};

/** pt-BR copy for the stable backend error codes; falls back to the server message. */
export function quotesErrorMessage(err: unknown, t: QuotesTranslate = defaultQuotesT): string {
  const code = apiErrorCode(err);
  if (code) {
    const mapped = t(`error.${code}`);
    if (mapped !== `error.${code}`) return mapped;
  }
  return errorMessage(err);
}

/** The query string of a list request (empty filters are not sent). */
export function listQuery(params: QuoteListParams): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  if (params.q?.trim()) out.q = params.q.trim();
  if (params.status) out.status = params.status;
  if (params.party_id) out.party_id = params.party_id;
  if (params.include_versions) out.include_versions = true;
  if (params.page) out.page = params.page;
  if (params.page_size) out.page_size = params.page_size;
  return out;
}

export function createQuotesHooks(api: QuotesApi) {
  const unwrap = async <T,>(p: Promise<QuoteEnvelope<T>>): Promise<T> => (await p).data;

  function useInvalidate() {
    const qc = useQueryClient();
    return (...keys: QueryKey[]) => Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));
  }

  function useQuotes(params: QuoteListParams = {}) {
    const q = useQuery<QuotePaginated<QuoteRecord>>({
      queryKey: quotesKeys.list(params),
      queryFn: () => api.get(BASE, listQuery(params)),
      placeholderData: keep,
    });
    return signals(q);
  }

  function useQuote(id: string | null | undefined) {
    const q = useQuery<QuoteRecord>({
      queryKey: quotesKeys.detail(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}`)),
      enabled: !!id,
    });
    return signals(q);
  }

  function useQuoteEvents(id: string | null | undefined) {
    const q = useQuery<QuoteEventRecord[]>({
      queryKey: quotesKeys.events(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/events`)),
      enabled: !!id,
    });
    return signals(q);
  }

  function useQuoteAcceptance(id: string | null | undefined, enabled = true) {
    const q = useQuery<QuoteAcceptance | null>({
      queryKey: quotesKeys.acceptance(id ?? ''),
      queryFn: () => unwrap(api.get(`${BASE}/${id}/acceptance`)),
      enabled: !!id && enabled,
    });
    return signals(q);
  }

  /** Every mutation that changes a quote refreshes the lists and that quote's detail / events / acceptance. */
  function useQuoteMutations() {
    const inv = useInvalidate();
    const refresh = (id: string) => inv(quotesKeys.lists, quotesKeys.detail(id), quotesKeys.events(id), quotesKeys.acceptance(id));
    return {
      create: useMutation({
        mutationFn: (body: QuoteInput) => unwrap<QuoteRecord>(api.post(BASE, body)),
        onSuccess: () => inv(quotesKeys.lists),
      }),
      update: useMutation({
        mutationFn: ({ id, ...body }: { id: string } & QuotePatch) => unwrap<QuoteRecord>(api.patch(`${BASE}/${id}`, body)),
        onSuccess: (_q, vars) => refresh(vars.id),
      }),
      remove: useMutation({
        mutationFn: (id: string) => api.delete(`${BASE}/${id}`),
        onSuccess: (_r, id) => inv(quotesKeys.lists, quotesKeys.detail(id)),
      }),
      newVersion: useMutation({
        mutationFn: ({ id, valid_until }: { id: string; valid_until?: string }) =>
          unwrap<QuoteRecord>(api.post(`${BASE}/${id}/versions`, valid_until ? { valid_until } : {})),
        onSuccess: (_q, vars) => refresh(vars.id),
      }),
      send: useMutation({
        mutationFn: ({ id, ...body }: { id: string } & QuoteSendInput) => unwrap<QuoteSendResult>(api.post(`${BASE}/${id}/send`, body)),
        onSuccess: (_r, vars) => refresh(vars.id),
      }),
      accept: useMutation({
        mutationFn: ({ id, signer_name, note }: { id: string; signer_name: string; note?: string }) =>
          unwrap<QuoteRecord>(api.post(`${BASE}/${id}/accept`, { signer_name, ...(note ? { note } : {}) })),
        onSuccess: (_q, vars) => refresh(vars.id),
      }),
      reject: useMutation({
        mutationFn: ({ id, reason, signer_name }: { id: string; reason: string; signer_name?: string }) =>
          unwrap<QuoteRecord>(api.post(`${BASE}/${id}/reject`, { reason, ...(signer_name ? { signer_name } : {}) })),
        onSuccess: (_q, vars) => refresh(vars.id),
      }),
      convert: useMutation({
        mutationFn: (id: string) => unwrap<QuoteRecord>(api.post(`${BASE}/${id}/convert`, {})),
        onSuccess: (_q, id) => refresh(id),
      }),
      /** Server preview of a draft's totals (nothing is written). */
      calculate: useMutation({
        mutationFn: (body: Pick<QuoteInput, 'lines' | 'discount_cents'>) => unwrap<QuoteCalculation>(api.post(`${BASE}/calculate`, body)),
      }),
    };
  }

  /** The authenticated PDF URL (the host's `<a href download>` carries the session). */
  const pdfUrl = (id: string) => `${BASE}/${id}/pdf`;

  return { useQuotes, useQuote, useQuoteEvents, useQuoteAcceptance, useQuoteMutations, pdfUrl };
}
export type QuotesHooks = ReturnType<typeof createQuotesHooks>;

/** The customer's side. `apiBase` is the backend origin (the page is public: no auth header, no session). */
export function createQuotesPublicHooks(apiOrBase: OrganApi | string, opts: { apiBase?: string } = {}) {
  const api: OrganApi = typeof apiOrBase === 'string' ? createFetchTransport(apiOrBase) : apiOrBase;
  const base = (typeof apiOrBase === 'string' ? apiOrBase : opts.apiBase ?? '').replace(/\/+$/, '');
  const unwrap = async <T,>(p: Promise<QuoteEnvelope<T>>): Promise<T> => (await p).data;

  function usePublicQuote(token: string | null | undefined) {
    const q = useQuery<QuotePublicView>({
      queryKey: quotesKeys.public(token ?? ''),
      queryFn: () => unwrap(api.get(`${PUBLIC_BASE}/${token}`)),
      enabled: !!token,
      // A bad / expired link is an answer, not a transient fault: do not hammer the endpoint.
      retry: (count, err) => !(err instanceof ApiError && (err.status ?? 0) >= 400 && (err.status ?? 0) < 500) && count < 2,
    });
    return signals(q);
  }

  function usePublicDecision(token: string) {
    const qc = useQueryClient();
    const settle = (view: QuotePublicView) => qc.setQueryData(quotesKeys.public(token), view);
    return {
      accept: useMutation({
        mutationFn: (body: { name: string; agree: boolean }) => unwrap<QuotePublicView>(api.post(`${PUBLIC_BASE}/${token}/accept`, body)),
        onSuccess: settle,
      }),
      reject: useMutation({
        mutationFn: (body: { name?: string; reason?: string }) => unwrap<QuotePublicView>(api.post(`${PUBLIC_BASE}/${token}/reject`, body)),
        onSuccess: settle,
      }),
    };
  }

  const pdfUrl = (token: string) => `${base}${PUBLIC_BASE}/${token}/pdf`;
  return { usePublicQuote, usePublicDecision, pdfUrl };
}
export type QuotesPublicHooks = ReturnType<typeof createQuotesPublicHooks>;
