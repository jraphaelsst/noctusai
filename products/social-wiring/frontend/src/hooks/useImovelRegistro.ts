/**
 * Manual property registration — `POST /api/imoveis/{codigo}/registrar`
 * (migration 149; a required address body since migration 159) and its
 * paired near-duplicate check, `GET /api/imoveis/busca/duplicatas`.
 *
 * 🔴 OWN FILE, DELIBERATELY. Both `useCardHub.ts` (query-invalidation work
 * in flight from a peer engineer) and `pages/ImovelDetalhes.tsx` /
 * `hooks/useImovelDados.ts` (document rows / 404 toast / Matrículas
 * prefill, also in flight from a peer engineer) are hot files right now —
 * this feature's only consumer is `components/card/ImovelCodigoPicker.tsx`,
 * so it gets its own hook file rather than adding surface to either. The
 * query-key literal `["sw", "cardHub", "imoveisBusca"]` below matches
 * `useCardHub.ts`'s `ROOT_KEY`/`IMOVEIS_BUSCA_KEY` BY VALUE (not by import)
 * so this mutation can still invalidate `useImoveisBusca`'s cache entries
 * without importing anything from that file.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { ImovelBusca } from "@/types/cardHub";

const SW_CARD_HUB_ROOT_KEY = ["sw", "cardHub"] as const;
const IMOVEIS_DUPLICATAS_KEY = (termo: string) =>
  [...SW_CARD_HUB_ROOT_KEY, "imoveisPossiveisDuplicatas", termo] as const;

/**
 * `GET /api/imoveis/busca/duplicatas` — "did you mean one of these?" for
 * the "cadastrar como imóvel novo" step, checked ONLY when the exact search
 * for the same term already came back empty (the moment a genuine
 * duplicate gets hand-registered — see `busca_service.
 * sugestoes_para_cadastro`'s header for the EUROVILLE-535/ONE7515
 * incident). `enabled` composes with the caller's own gate.
 */
export function useImoveisPossiveisDuplicatas(termo: string, habilitado: boolean) {
  const limpo = termo.trim();
  return useQuery({
    queryKey: IMOVEIS_DUPLICATAS_KEY(limpo),
    queryFn: () =>
      api.get<{ items: ImovelBusca[] }>(
        `/api/imoveis/busca/duplicatas?q=${encodeURIComponent(limpo)}&limit=5`,
      ),
    enabled: habilitado && limpo.length >= 2,
    staleTime: 30_000,
  });
}

/** `POST /{codigo}/registrar`'s body (migration 159, `RegistrarImovelBody`
 *  on the backend) — every field REQUIRED except `complemento` (a house/lot
 *  has no unit number). Owner rule, verbatim, 2026-09-23: "The address
 *  doesn't come from the matrícula. The address comes from the property
 *  table; it will be mandatory upon property registration that it has the
 *  address in it." */
export interface RegistrarImovelManualBody {
  logradouro: string;
  numero: string;
  complemento?: string | null;
  bairro: string;
  cidade: string;
  uf: string;
  cep: string;
}

/**
 * `POST /api/imoveis/{codigo}/registrar` — give a código neither the Vista
 * mirror nor the registry has ever seen a registry identity AND its
 * address, in one request. Idempotent on the server — a retry after a
 * partial failure re-applies the same address; invalidates every
 * `imoveisBusca`/`imoveisPossiveisDuplicatas` query so a subsequent search
 * (or the SAME search, re-typed) finds it.
 */
export function useRegistrarImovelManual() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      codigo,
      endereco,
    }: {
      codigo: string;
      endereco: RegistrarImovelManualBody;
    }) =>
      api.post<{ codigo: string }>(
        `/api/imoveis/${encodeURIComponent(codigo)}/registrar`,
        endereco,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...SW_CARD_HUB_ROOT_KEY, "imoveisBusca"] });
      qc.invalidateQueries({ queryKey: [...SW_CARD_HUB_ROOT_KEY, "imoveisPossiveisDuplicatas"] });
    },
  });
}
