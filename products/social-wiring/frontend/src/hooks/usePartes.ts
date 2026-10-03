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
    onSuccess: () =>
      Promise.all([
        // The card family (compradores/vendedores lists, card summary,
        // qualificação) lives under the seed's `["sw","cardHub"]` root.
        qc.invalidateQueries({ queryKey: ["sw", "cardHub"] }),
        qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] }),
      ]),
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
  return useMutation({
    mutationFn: ({ parteId, patch }: { parteId: string; patch: ParteContratoPatch }) =>
      api.patch<ParteContratoOut>(
        `${clienteBase(clienteId)}/compradores/${encodeURIComponent(parteId)}/contrato`,
        patch,
      ),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["sw", "cardHub"] }),
        qc.invalidateQueries({ queryKey: ["sw", "clientes", clienteId] }),
      ]),
  });
}
