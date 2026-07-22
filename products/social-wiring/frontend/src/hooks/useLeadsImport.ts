/**
 * Leads import hooks — `/api/leads/import/*` ("Importação" subtab).
 *
 * `preview` / `commit` are multipart `.xlsx` uploads — the seed `api` client
 * (`@/lib/api`) is JSON-only, so (mirroring `useUpload.ts`'s established
 * pattern in this product) these two bypass it and do a raw `fetch` with a
 * `FormData` body + the Supabase session token, via `apiUrl()`. Wrapped in
 * `useMutation` so callers get the same isPending/isSuccess/isError surface
 * as every other Leads mutation.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, supabase } from "@noctusai/seed/infra";
import { apiUrl } from "@/lib/apiBase";
import type { ImportBatch, ImportPreview } from "@/pages/leads/types";
import type { PaginationMeta } from "./useContacts";

interface SuccessEnvelope<T> {
  data: T;
}

export interface ImportBatchesPage {
  data: ImportBatch[];
  pagination: PaginationMeta;
}

const BASE = "/api/leads/import";
const BATCHES_KEY = ["leads", "import", "batches"] as const;

// ─── Batch history ───────────────────────────────────────────────────────────

export interface ListImportBatchesParams {
  page?: number;
  pageSize?: number;
}

export function useLeadImportBatches(params?: ListImportBatchesParams) {
  const search = new URLSearchParams();
  if (params?.page != null) search.set("page", String(params.page));
  if (params?.pageSize != null) search.set("page_size", String(params.pageSize));
  const qs = search.toString();

  return useQuery<ImportBatchesPage>({
    queryKey: [...BATCHES_KEY, params],
    queryFn: () => api.get<ImportBatchesPage>(qs ? `${BASE}/batches?${qs}` : `${BASE}/batches`),
  });
}

// ─── Preview / commit (multipart) ───────────────────────────────────────────

async function getAuthHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postXlsx<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  const headers = await getAuthHeader();
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers, // do NOT set content-type — the browser sets the multipart boundary
    body: formData,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`[${response.status}] ${detail || "Falha ao processar planilha."}`);
  }
  return (await response.json()) as T;
}

/** Parses the `.xlsx` and returns the diff WITHOUT writing anything. */
export function useLeadImportPreview() {
  return useMutation<ImportPreview, unknown, File>({
    mutationFn: async (file) => {
      const res = await postXlsx<SuccessEnvelope<ImportPreview>>(`${BASE}/preview`, file);
      return res.data;
    },
  });
}

/** Parses + upserts; invalidates every leads/analytics query family on success. */
export function useLeadImportCommit() {
  const qc = useQueryClient();
  return useMutation<ImportBatch, unknown, File>({
    mutationFn: async (file) => {
      const res = await postXlsx<SuccessEnvelope<ImportBatch>>(`${BASE}/commit`, file);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["leads"] });
    },
  });
}
