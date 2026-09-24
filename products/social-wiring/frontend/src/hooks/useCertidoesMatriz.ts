/**
 * Certidões matriz — the "Certidões" card tab's own read (`GET /api/clientes/
 * {cliente_id}/certidoes/matriz`). Mirrors `useEmpresas.ts`'s conventions
 * (bare-payload `api.get<T>` off `@noctusai/seed/infra`, manual query key) —
 * this IS a card_hub route (mounted alongside `/{cliente_id}/empresas`,
 * `card_hub/router.py`), keyed by `cliente_id` the same way.
 */
import { useQuery } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";

import type { CertidoesMatrizResponse } from "@/types/certidoesMatriz";

const CERTIDOES_MATRIZ_KEY = (clienteId: string) =>
  ["sw", "clientes", clienteId, "certidoes", "matriz"] as const;

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
