/**
 * Conversation + document request/triage hooks (CONTRACT §2).
 *
 * Keys nest under the card's family key so any card-wide invalidation (an
 * upload, a merge, an extraction landing) refreshes them too.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { pageOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";

import { cardFamilyKey } from "@/hooks/useCardHub";
import type {
  Conversa,
  DocumentoAClassificar,
  PedirDocumentosResposta,
} from "@/types/conversa";

const base = (clienteId: string) => `/api/clientes/${encodeURIComponent(clienteId)}`;
const CONVERSA_KEY = (clienteId: string) => [...cardFamilyKey(clienteId), "conversa"] as const;
const A_CLASSIFICAR_KEY = (clienteId: string) =>
  [...cardFamilyKey(clienteId), "documentos-a-classificar"] as const;

export function useConversa(clienteId: string | null | undefined) {
  return useQuery({
    queryKey: CONVERSA_KEY(clienteId ?? "__none__"),
    queryFn: () => api.get<Conversa>(`${base(clienteId as string)}/conversa`),
    enabled: !!clienteId,
  });
}

export function usePedirDocumentos(clienteId: string) {
  const qc = useQueryClient();
  return useMutation({ // noc-allow: invalidate-only — the answer is only the sent message's id + requested items; the full message (body, status) and the timeline event are server-built
    mutationFn: (texto?: string) =>
      api.post<PedirDocumentosResposta>(
        `${base(clienteId)}/conversa/pedir-documentos`,
        texto ? { texto } : {},
      ),
    onSuccess: () => {
      // The conversation grows by one message and the timeline by one event.
      void qc.invalidateQueries({ queryKey: cardFamilyKey(clienteId) });
    },
  });
}

export function useDocumentosAClassificar(clienteId: string | null | undefined) {
  return useQuery({
    queryKey: A_CLASSIFICAR_KEY(clienteId ?? "__none__"),
    queryFn: () =>
      api.get<{ items: DocumentoAClassificar[]; total: number }>(
        `${base(clienteId as string)}/documentos/a-classificar`,
      ),
    enabled: !!clienteId,
  });
}

export function useClassificarDocumento(clienteId: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<
    { id: string; tipo_documento: string; extracao_status: string },
    { documentoId: string; tipo: string }
  >({
    mutationFn: ({ documentoId, tipo }) =>
      api.post<{ id: string; tipo_documento: string; extracao_status: string }>(
        `${base(clienteId)}/documentos/${documentoId}/classificar`,
        { tipo_documento: tipo },
      ),
    // A classified document leaves the triage list.
    targets: ({ documentoId }) => [
      {
        queryKey: A_CLASSIFICAR_KEY(clienteId),
        optimistic: (old: { items: DocumentoAClassificar[]; total: number } | undefined) =>
          pageOps.remove(old, documentoId),
      },
    ],
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: cardFamilyKey(clienteId) });
    },
  });
}
