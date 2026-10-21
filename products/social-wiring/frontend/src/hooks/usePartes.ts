/**
 * Parties of an atendimento — list (§2.1), documento lookup (§2.5) and the
 * PF/PJ add mutation (§2.3, optionally chained to the §1.2 emission request).
 * `useCardHub.ts` is frozen for this project, so these live in their own file.
 *
 * Loading UI: callers read `showSkeleton` / `isRefreshing`, computed here off
 * `data` — never `isLoading`, never a bare `isFetching`.
 * → KB § PATTERNS/frontend/lying-loading-state.md
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import type {
  EmissaoCertidoesResponse,
  ParteContratoOut,
  ParteContratoPatch,
  ParteCreateBody,
  ParteItem,
  ParteLookup,
  PartesResponse,
} from "@/types/partes";

const clienteBase = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;

function qs(params: Record<string, string | null | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) sp.set(k, v);
  const out = sp.toString();
  return out ? `?${out}` : "";
}

export const PARTES_KEY = (clienteId: string, atendimentoId?: string | null) =>
  ["sw", "clientes", clienteId, "partes", atendimentoId ?? null] as const;

const PARTE_LOOKUP_KEY = (clienteId: string, documento: string, atendimentoId?: string | null) =>
  ["sw", "clientes", clienteId, "partes-lookup", documento, atendimentoId ?? null] as const;

/** `GET /api/clientes/{id}/partes` — both lados, titular included, PJ too. */
export function usePartes(clienteId: string | null, atendimentoId?: string | null) {
  const query = useQuery({
    queryKey: PARTES_KEY(clienteId ?? "__none__", atendimentoId),
    queryFn: () =>
      api.get<PartesResponse>(
        `${clienteBase(clienteId as string)}/partes${qs({ atendimento_id: atendimentoId })}`,
      ),
    enabled: !!clienteId,
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

/**
 * `GET /api/clientes/{id}/partes/lookup?documento=` — fired ONLY with a
 * complete, check-digit-valid documento (`null` keeps it off). A miss is a
 * 200 with `encontrado: null`, never an error.
 */
export function useParteLookup(
  clienteId: string | null,
  documento: string | null,
  atendimentoId?: string | null,
) {
  const query = useQuery({
    queryKey: PARTE_LOOKUP_KEY(clienteId ?? "__none__", documento ?? "", atendimentoId),
    queryFn: () =>
      api.get<ParteLookup>(
        `${clienteBase(clienteId as string)}/partes/lookup${qs({
          documento,
          atendimento_id: atendimentoId,
        })}`,
      ),
    enabled: !!clienteId && !!documento,
    // The lookup is keyed by the typed documento, so each keystroke that
    // completes a new one is a new key: keep the previous answer on screen
    // instead of flashing the form back to "nothing found".
    placeholderData: keepPreviousData,
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data && !!documento,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export interface AdicionarParteInput extends ParteCreateBody {
  /** Chain the §1.2 emission request for the party right after adding it —
   *  the "Re-emitir e re-analisar" path for stale certidões. */
  reemitirCertidoes?: boolean;
}

export interface AdicionarParteResultado {
  parte: ParteItem;
  /** `null` when not requested; set when the add succeeded but the emission
   *  request did not (surfaced by the caller — never swallowed). */
  emissao: EmissaoCertidoesResponse | null;
  emissaoErro: string | null;
}

/** `POST /api/clientes/{id}/compradores` with the PF-or-PJ body (§2.3). */
/** The `partes` answers of this card (every atendimento filter): rows are keyed by `parte_id`, not `id`. */
const partesDoCardKey = (clienteId: string) => ["sw", "clientes", clienteId, "partes"] as const;

export function useAdicionarParte(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      reemitirCertidoes,
      ...body
    }: AdicionarParteInput): Promise<AdicionarParteResultado> => {
      const parte = await api.post<ParteItem>(`${clienteBase(clienteId)}/compradores`, body);
      if (!reemitirCertidoes) return { parte, emissao: null, emissaoErro: null };

      const kind = parte.tipo_pessoa === "PJ" ? "empresa" : "pessoa";
      const alvoId = parte.tipo_pessoa === "PJ" ? parte.empresa_id : parte.cliente_id;
      if (!alvoId) {
        return { parte, emissao: null, emissaoErro: "Parte sem identificador para emissão." };
      }
      try {
        const emissao = await api.post<EmissaoCertidoesResponse>(
          `${clienteBase(clienteId)}/certidoes/partes/${kind}/${encodeURIComponent(alvoId)}/emissao`,
          { tipos: null, atendimento_id: body.atendimento_id ?? null },
        );
        return { parte, emissao, emissaoErro: null };
      } catch (err) {
        return {
          parte,
          emissao: null,
          emissaoErro: err instanceof Error ? err.message : "Falha ao solicitar emissão.",
        };
      }
    },
    // 🔴 NOT returned: react-query awaits an `onSuccess` promise before the mutation
    // settles, so returning the invalidations kept `isPending` true (and the add dialog
    // on "Adicionando…") for as long as the card family's refetches took (~10s in prod,
    // 2026-10-21) — long after the new row was already on screen. The create has
    // succeeded; the refetches are refresh work, not part of it.
    onSuccess: ({ parte }) => {
      // The created party goes into the card's partes lists at once (written here, not through
      // `useCacheWriteMutation`: its settle is awaited, and this mutation must resolve on the create).
      qc.setQueriesData<PartesResponse>({ queryKey: partesDoCardKey(clienteId) }, (old) =>
        old && Array.isArray(old.items) && !old.items.some((p) => p.parte_id === parte.parte_id)
          ? { ...old, items: [...old.items, parte], total: old.total + 1 }
          : old,
      );
      // The card family (compradores/vendedores lists, card summary,
      // qualificação) lives under the seed's `["sw","cardHub"]` root.
      void qc.invalidateQueries({ queryKey: ["sw", "cardHub"] });
      void qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] });
    },
  });
}

/**
 * `PATCH /api/clientes/{id}/compradores/{parte_id}/contrato` (migration 193)
 * — a company party's NIRE + sede, or a representante's link to the company
 * party it signs for. Invalidates the parties lists (both shapes) and the
 * contratos family: the generator's readiness (`partes.pj.*`,
 * `PJ_MAIS_DE_UM_REPRESENTANTE`, …) reads exactly these columns.
 */
export function useAtualizarContratoParte(clienteId: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<ParteContratoOut, { parteId: string; patch: ParteContratoPatch }>({
    mutationFn: ({ parteId, patch }) =>
      api.patch<ParteContratoOut>(
        `${clienteBase(clienteId)}/compradores/${encodeURIComponent(parteId)}/contrato`,
        patch,
      ),
    // The PATCH answer carries the party's company qualification: it is merged into the party row.
    targets: ({ parteId }) => [
      {
        queryKey: partesDoCardKey(clienteId),
        match: "prefix",
        commit: (old: PartesResponse | undefined, saved) =>
          old && Array.isArray(old.items)
            ? {
                ...old,
                items: old.items.map((p) =>
                  p.parte_id !== parteId
                    ? p
                    : {
                        ...p,
                        ...(saved.pj_nire !== undefined ? { pj_nire: saved.pj_nire } : {}),
                        ...(saved.representa_parte_id !== undefined
                          ? { representa_parte_id: saved.representa_parte_id }
                          : {}),
                        pj_sede: {
                          logradouro: saved.pj_sede_logradouro ?? p.pj_sede?.logradouro ?? null,
                          numero: saved.pj_sede_numero ?? p.pj_sede?.numero ?? null,
                          complemento: saved.pj_sede_complemento ?? p.pj_sede?.complemento ?? null,
                          bairro: saved.pj_sede_bairro ?? p.pj_sede?.bairro ?? null,
                          cidade: saved.pj_sede_cidade ?? p.pj_sede?.cidade ?? null,
                          uf: saved.pj_sede_uf ?? p.pj_sede?.uf ?? null,
                          cep: saved.pj_sede_cep ?? p.pj_sede?.cep ?? null,
                        },
                      },
                ),
              }
            : old,
      },
    ],
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["sw", "cardHub"] }),
        qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] }),
      ]),
  });
}
