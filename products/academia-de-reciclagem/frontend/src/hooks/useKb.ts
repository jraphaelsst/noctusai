/**
 * Knowledge-base data hooks — contract §A.1, §A.10, §B.1.
 *
 * TanStack Query over `@/lib/api`. Mutations invalidate the affected
 * queries (list + detail + revisions), matching the dispatch's "Mutations
 * invalidate the affected queries" rule.
 */
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Envelope } from "@/lib/types";

export interface KbEntrySummary {
  slug: string;
  categoria: string;
  subcategoria: string | null;
  titulo: string;
  resumo: string | null;
  tags: string[];
  updated_at: string;
}

export interface RevisionRef {
  rev_no: number;
  author_kind: "human" | "agent" | "import";
  created_at: string;
}

export interface KbEntry extends KbEntrySummary {
  corpo_md: string;
  frontmatter: Record<string, unknown>;
  arquivado: boolean;
  current_revision: RevisionRef;
}

export interface Revision {
  rev_no: number;
  op: "create" | "update" | "archive" | "supersede" | "import";
  author_kind: "human" | "agent" | "import";
  user_id: string | null;
  agent_id: string | null;
  approval_id: string | null;
  channel: string | null;
  conversation_id: string | null;
  motivo: string | null;
  git_sha: string | null;
  git_committed_at: string | null;
  created_at: string;
  snapshot: Record<string, unknown>;
}

export const KB_CATEGORIAS = [
  "contexto",
  "dominio",
  "instrucoes",
  "skills",
  "workflows",
  "mcp-servers",
  "historico",
  "marca",
  "evals",
  "geral",
] as const;

export interface KbListParams {
  consulta?: string;
  categoria?: string;
  subcategoria?: string;
  tag?: string;
  limite?: number;
  offset?: number;
}

const kbKeys = {
  all: ["kb"] as const,
  list: (params: KbListParams) => ["kb", "list", params] as const,
  detail: (slug: string) => ["kb", "detail", slug] as const,
  revisions: (slug: string) => ["kb", "revisions", slug] as const,
};

export function useKbList(params: KbListParams) {
  return useQuery({
    queryKey: kbKeys.list(params),
    queryFn: () => api.get<Envelope<KbEntrySummary>>("/api/kb", params as Record<string, unknown>),
    placeholderData: keepPreviousData,
  });
}

export function useKbEntry(slug: string | undefined) {
  return useQuery({
    queryKey: kbKeys.detail(slug ?? ""),
    queryFn: () => api.get<KbEntry>(`/api/kb/${slug}`),
    enabled: !!slug,
  });
}

export function useKbRevisions(slug: string | undefined) {
  return useQuery({
    queryKey: kbKeys.revisions(slug ?? ""),
    queryFn: () => api.get<Envelope<Revision>>(`/api/kb/${slug}/revisions`),
    enabled: !!slug,
  });
}

export interface KbCreateInput {
  slug?: string;
  categoria: string;
  subcategoria?: string;
  titulo: string;
  resumo?: string;
  tags?: string[];
  corpo_md: string;
  motivo: string;
}

export function useCreateKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: KbCreateInput) => api.post<KbEntry>("/api/kb", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: kbKeys.all });
    },
  });
}

export interface KbUpdateInput {
  titulo?: string;
  resumo?: string;
  tags?: string[];
  corpo_md?: string;
  categoria?: string;
  subcategoria?: string;
  novo_slug?: string;
  motivo: string;
}

export function useUpdateKb(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: KbUpdateInput) => api.put<KbEntry>(`/api/kb/${slug}`, data),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: kbKeys.all });
      qc.invalidateQueries({ queryKey: kbKeys.detail(slug) });
      qc.invalidateQueries({ queryKey: kbKeys.revisions(slug) });
      if (updated.slug !== slug) {
        qc.invalidateQueries({ queryKey: kbKeys.detail(updated.slug) });
        qc.invalidateQueries({ queryKey: kbKeys.revisions(updated.slug) });
      }
    },
  });
}

export function useArchiveKb(slug: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (motivo: string) => api.post<KbEntry>(`/api/kb/${slug}/archive`, { motivo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: kbKeys.all });
      qc.invalidateQueries({ queryKey: kbKeys.detail(slug) });
      qc.invalidateQueries({ queryKey: kbKeys.revisions(slug) });
    },
  });
}
