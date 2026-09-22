/**
 * Import bundle — Agent Studio CONTRACT.md §D5, §F.
 *
 * `POST /api/studio/agents/{key}/import?dry_run=true|false` (admin), body =
 * the §F bundle JSON. `key` is NOT bound to this hook — the target agent is
 * only known once the bundle itself is parsed (`bundle.agente.key`; the
 * import can CREATE a brand-new studio agent, so there is no "current
 * agent" on `/studio`), so every call site passes it explicitly per
 * mutation.
 *
 * Never publishes (§D5): a successful non-dry-run import replaces the
 * draft's sections/skills and upserts knowledge/evals/clients, so it
 * invalidates the same things a draft write does (`hooks/studio/useVersions.ts`'s
 * `afterDraftWrite`) plus the agent LIST (`tem_rascunho`, and — for a newly
 * created agent — a brand-new row).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { seg, studioKeys } from "./keys";

/** §D5 response shape — the import plan (dry run) or the applied result. */
export interface ImportBundleSummary {
  dry_run: boolean;
  agente: { criado: boolean };
  rascunho: { version_id: string; secoes: number; skills: number; arquivos: number };
  conhecimento: {
    colecoes_criadas: number;
    documentos_criados: number;
    documentos_atualizados: number;
    documentos_inalterados: number;
  };
  evals: { criados: number; atualizados: number };
  clientes: { criados: number };
  avisos: string[];
}

/** §F bundle envelope — only the fields the UI reads client-side before
 * sending; the backend is the strict-schema authority (§F: "Validated with
 * Pydantic; unknown keys rejected"). */
export interface ImportBundlePreview {
  formato: string;
  agente: { key: string; nome: string; descricao?: string };
  secoes?: unknown[];
  skills?: unknown[];
  conhecimento?: { documentos?: unknown[] }[];
  evals?: unknown[];
  clientes?: unknown[];
}

export function useImportBundle() {
  const qc = useQueryClient();
  return useMutation<ImportBundleSummary, unknown, { key: string; bundle: unknown; dryRun: boolean }>({
    mutationFn: ({ key, bundle, dryRun }) =>
      api.post<ImportBundleSummary>(`/api/studio/agents/${seg(key)}/import?dry_run=${dryRun ? "true" : "false"}`, bundle),
    onSuccess: (summary, { key }) => {
      if (summary.dry_run) return;
      void qc.invalidateQueries({ queryKey: studioKeys.list() });
      void qc.invalidateQueries({ queryKey: studioKeys.agent(key) });
      void qc.invalidateQueries({ queryKey: studioKeys.compiledAll(key) });
    },
  });
}
