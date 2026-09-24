/**
 * Certidões matriz — the "Certidões" card tab's own read (`GET /api/clientes/
 * {cliente_id}/certidoes/matriz`) plus the "+ Adicionar certidão" CRUD on
 * per-card custom rows (migration 170). Mirrors `useEmpresas.ts`'s
 * conventions (bare-payload `api.get/post/patch/delete<T>` off `@noctusai/
 * seed/infra`, manual query key) — these ARE card_hub routes (mounted
 * alongside `/{cliente_id}/empresas`, `card_hub/router.py`), keyed by
 * `cliente_id` the same way.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type {
  CertidaoMatrizLinhaCustomizada,
  CertidoesMatrizResponse,
} from "@/types/certidoesMatriz";

const CERTIDOES_MATRIZ_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "certidoes", "matriz"] as const;

const linhasBase = (clienteId: string) =>
  `/api/clientes/${encodeURIComponent(clienteId)}/certidoes/matriz/linhas`;

/** `GET /api/clientes/{cliente_id}/certidoes/matriz` — every certidão type
 *  crossed with every vendedor party + their PJ-requiring empresas, already
 *  aggregated (colors, totals) so the panel never pivots per-column reads
 *  client-side. Empty (never a 409) when there is no open atendimento or it
 *  is ambiguous — same posture `useEmpresasDoCard` takes. */
export function useCertidoesMatriz(clienteId: string | null) {
  return useQuery({
    queryKey: CERTIDOES_MATRIZ_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<CertidoesMatrizResponse>(
        `/api/clientes/${encodeURIComponent(clienteId as string)}/certidoes/matriz`,
      ),
    enabled: !!clienteId,
  });
}

/** `POST .../certidoes/matriz/linhas` — "+ Adicionar certidão". Fans out a
 *  `pendente` placeholder across every column already on the card
 *  server-side; refetching the matriz is enough to show the new row AND
 *  its (Pendente-by-default) cells. */
export function useCriarLinhaMatriz(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (nome: string) =>
      api.post<CertidaoMatrizLinhaCustomizada>(linhasBase(clienteId), { nome }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: CERTIDOES_MATRIZ_KEY(clienteId) }),
  });
}

/** `PATCH .../certidoes/matriz/linhas/{linha_id}` — rename. */
export function useRenomearLinhaMatriz(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ linhaId, nome }: { linhaId: string; nome: string }) =>
      api.patch<CertidaoMatrizLinhaCustomizada>(`${linhasBase(clienteId)}/${linhaId}`, { nome }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: CERTIDOES_MATRIZ_KEY(clienteId) }),
  });
}

/** `DELETE .../certidoes/matriz/linhas/{linha_id}` — soft-delete the ROW
 *  DEFINITION only; already-recorded results are never touched server-side
 *  (see the backend's own docstring). */
export function useRemoverLinhaMatriz(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (linhaId: string) => api.delete(`${linhasBase(clienteId)}/${linhaId}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: CERTIDOES_MATRIZ_KEY(clienteId) }),
  });
}
