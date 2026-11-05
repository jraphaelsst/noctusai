/**
 * Divergências com o Vista — a human decides which side is true.
 *
 * TRANSITIONAL (owner, 2026-11-04): when the Vista mirror and OUR data
 * disagree about the same fact, the system flags it and a person resolves it;
 * the sync never overwrites. Detection lives in the backend's existing
 * `imovel_campo_conflitos` machinery; this file + `ImovelDivergenciasVista`
 * are the whole UI, kept removable on purpose (delete both, drop the mount in
 * `ImovelDetalhes`, the page is unchanged).
 *
 * Wire (built to the sync engineer's contract):
 *   GET  /api/imoveis/{codigo}/divergencias  → { items: Divergencia[] } (pending + history)
 *   POST /api/imoveis/{codigo}/divergencias/{id}/resolver { escolha, valor? } (org admin only)
 *
 * → KB § PATTERNS/frontend/mirror-owned-overlay.md § 2f
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@noctusai/seed/infra";

export type DivergenciaEscolha = "vista" | "nosso" | "manual";

export interface DivergenciaOrigem {
  /** e.g. "julia" (a conversation), "manual", "documento". */
  tipo: string;
  thread_id?: string | null;
  contato_id?: string | null;
  /** A SANITIZED excerpt of what was said — never raw PII. */
  trecho?: string | null;
}

export interface Divergencia {
  id: string;
  campo: string;
  status: "pendente" | "resolvido";
  valor_vista: unknown;
  vista_em: string | null;
  valor_nosso: unknown;
  nosso_em: string | null;
  nosso_por: { id: string; nome: string | null } | null;
  origem: DivergenciaOrigem | null;
  resolucao?: {
    escolha: DivergenciaEscolha;
    valor?: unknown;
    por?: { id: string; nome: string | null } | null;
    em?: string | null;
  } | null;
}

const KEY = (codigo: string) => ["sw", "imovel-dados", codigo, "divergencias"] as const;
const base = (codigo: string) => `/api/imoveis/${encodeURIComponent(codigo)}`;

export function useImovelDivergencias(codigo: string | null) {
  return useQuery({
    queryKey: KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ items?: Divergencia[] } | Divergencia[]>(
        `${base(codigo as string)}/divergencias`,
      );
      return Array.isArray(res) ? res : (res?.items ?? []);
    },
    enabled: !!codigo,
    placeholderData: (prev) => prev,
  });
}

export function useResolverDivergencia(codigo: string) {
  return useCacheWriteMutation<Divergencia, { id: string; escolha: DivergenciaEscolha; valor?: string }>({
    mutationFn: ({ id, escolha, valor }) =>
      api.post<Divergencia>(
        `${base(codigo)}/divergencias/${encodeURIComponent(id)}/resolver`,
        escolha === "manual" ? { escolha, valor } : { escolha },
      ),
    targets: [
      {
        queryKey: KEY(codigo),
        // Leaves "pending" on the click; the server's row (with its resolution) replaces it.
        optimistic: (old: Divergencia[] | undefined, { id, escolha, valor }) =>
          listOps.patch(old, id, {
            status: "resolvido",
            resolucao: { escolha, valor, por: null, em: new Date().toISOString() },
          }),
        commit: (old: Divergencia[] | undefined, saved) => listOps.replace(old, saved.id, saved),
      },
    ],
    // Choosing Vista / a manual value rewrites what the page shows.
    invalidate: [["sw", "imovel-dados", codigo], ["sw", "imoveis", "detail", codigo]],
  });
}

/** Pending divergences whose `campo` is one of `campos` (a field row's badge). */
export function pendentesDoCampo(items: Divergencia[] | undefined, campos: readonly string[]): number {
  return (items ?? []).filter((d) => d.status === "pendente" && campos.includes(d.campo)).length;
}
