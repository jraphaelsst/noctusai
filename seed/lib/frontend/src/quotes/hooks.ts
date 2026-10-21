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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCacheWriteMutation } from '../cache-writes';
import { ApiError } from '../api';
import { apiErrorCode, createFetchTransport, errorMessage, keep, signals, type OrganApi } from '../organ-kit/query';
import { pageOps } from '../organ-kit/page-ops';
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

  /**
   * Quote writes (KB § PATTERNS/frontend/mutation-cache-writes.md). The server answers with the whole quote, so a
   * write on quote `id` puts that record into its detail and into its row on every cached list page (`pageOps`,
   * prefix match) the moment it arrives. The quote's events and acceptance are server-derived and refresh in the
   * background; a NEW quote (create) is seeded into its detail and the lists converge on the settle, because which
   * page / filter / sort position it lands on is the server's call.
   */
  function useQuoteMutations() {
    const qc = useQueryClient();
    const derived = (id: string) => [quotesKeys.events(id), quotesKeys.acceptance(id)];
    const record = (id: string) => [
      { queryKey: quotesKeys.detail(id), commit: (_old: QuoteRecord | undefined, saved: QuoteRecord) => saved },
      { queryKey: quotesKeys.lists, match: 'prefix' as const, commit: (old: unknown, saved: QuoteRecord) => pageOps.replace(old, id, saved) },
    ];
    /** A transition of quote `id` that answers with the updated quote. */
    const transition = <V extends { id: string }>(post: (vars: V) => Promise<QuoteRecord>) =>
      useCacheWriteMutation<QuoteRecord, V>({ mutationFn: post, targets: ({ id }) => record(id), invalidate: ({ id }) => derived(id) });
    return {
      create: useCacheWriteMutation<QuoteRecord, QuoteInput>({
        mutationFn: (body) => unwrap<QuoteRecord>(api.post(BASE, body)),
        targets: [{ queryKey: quotesKeys.lists }],
        onSuccess: (saved) => {
          qc.setQueryData(quotesKeys.detail(saved.id), saved);
        },
      }),
      update: transition<{ id: string } & QuotePatch>(({ id, ...body }) => unwrap<QuoteRecord>(api.patch(`${BASE}/${id}`, body))),
      remove: useCacheWriteMutation<unknown, string>({
        mutationFn: (id) => api.delete(`${BASE}/${id}`),
        targets: (id) => [
          { queryKey: quotesKeys.lists, match: 'prefix', optimistic: (old: unknown) => pageOps.remove(old, id) },
          { queryKey: quotesKeys.detail(id) },
        ],
      }),
      // the new version is a different record: its detail is seeded, the version it was cut from is re-read
      newVersion: useCacheWriteMutation<QuoteRecord, { id: string; valid_until?: string }>({
        mutationFn: ({ id, valid_until }) => unwrap<QuoteRecord>(api.post(`${BASE}/${id}/versions`, valid_until ? { valid_until } : {})),
        targets: ({ id }) => [{ queryKey: quotesKeys.lists }, { queryKey: quotesKeys.detail(id) }],
        invalidate: ({ id }) => derived(id),
        onSuccess: (saved) => {
          qc.setQueryData(quotesKeys.detail(saved.id), saved);
        },
      }),
      send: useCacheWriteMutation<QuoteSendResult, { id: string } & QuoteSendInput>({
        mutationFn: ({ id, ...body }) => unwrap<QuoteSendResult>(api.post(`${BASE}/${id}/send`, body)),
        targets: ({ id }) => [
          { queryKey: quotesKeys.detail(id), commit: (_old: QuoteRecord | undefined, res: QuoteSendResult) => res.quote },
          { queryKey: quotesKeys.lists, match: 'prefix', commit: (old: unknown, res: QuoteSendResult) => pageOps.replace(old, id, res.quote) },
        ],
        invalidate: ({ id }) => derived(id),
      }),
      accept: transition<{ id: string; signer_name: string; note?: string }>(({ id, signer_name, note }) =>
        unwrap<QuoteRecord>(api.post(`${BASE}/${id}/accept`, { signer_name, ...(note ? { note } : {}) })),
      ),
      reject: transition<{ id: string; reason: string; signer_name?: string }>(({ id, reason, signer_name }) =>
        unwrap<QuoteRecord>(api.post(`${BASE}/${id}/reject`, { reason, ...(signer_name ? { signer_name } : {}) })),
      ),
      convert: useCacheWriteMutation<QuoteRecord, string>({
        mutationFn: (id) => unwrap<QuoteRecord>(api.post(`${BASE}/${id}/convert`, {})),
        targets: (id) => record(id),
        invalidate: (id) => derived(id),
      }),
      /** Server preview of a draft's totals (nothing is written). */
      calculate: useMutation({ // noc-allow: invalidate-only — a preview: it writes nothing on the server and reads/changes no cached query
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

  /** The server answers a decision with the refreshed public view: it replaces the cached one at once. */
  function usePublicDecision(token: string) {
    const targets = [{ queryKey: quotesKeys.public(token), commit: (_old: QuotePublicView | undefined, view: QuotePublicView) => view }];
    return {
      accept: useCacheWriteMutation<QuotePublicView, { name: string; agree: boolean }>({
        mutationFn: (body) => unwrap<QuotePublicView>(api.post(`${PUBLIC_BASE}/${token}/accept`, body)),
        targets,
      }),
      reject: useCacheWriteMutation<QuotePublicView, { name?: string; reason?: string }>({
        mutationFn: (body) => unwrap<QuotePublicView>(api.post(`${PUBLIC_BASE}/${token}/reject`, body)),
        targets,
      }),
    };
  }

  const pdfUrl = (token: string) => `${base}${PUBLIC_BASE}/${token}/pdf`;
  return { usePublicQuote, usePublicDecision, pdfUrl };
}
export type QuotesPublicHooks = ReturnType<typeof createQuotesPublicHooks>;
