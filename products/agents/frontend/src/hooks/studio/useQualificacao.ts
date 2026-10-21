/**
 * Agent Studio — the platform qualification STANDARD (CONTRACT §3; `qualificacao_router.py`).
 * Platform admin only (criteria, weights and rules are platform IP): every read/write answers 403
 * for anyone else and the tab renders the restricted state.
 *
 *   GET  /api/qualificacao/padroes · /padroes/{chave}/versoes · /versoes/{id}
 *   POST /api/qualificacao/padroes/{chave}/versoes          (new draft, optional `copiar_de`)
 *   PUT|DELETE .../versoes/{id}/criterios/{chave} · /estagios/{chave} · PUT .../parametros
 *   POST .../versoes/{id}/validar · /publicar               (422 `regras_invalidas` + `erros[]`)
 *
 * Every write returns the full version; it is committed into that version's cache entry the moment it
 * arrives (commit-only — the server owns validation + publishing) and the version list settles behind.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type {
  PadraoResumo,
  PadraoVersao,
  PadraoVersaoMeta,
  QualCriterioInput,
  QualEstagioInput,
  QualParametros,
  ValidarResposta,
} from "@/api/studio/types-julia";
import { seg, studioKeys, toView } from "./keys";

export function usePadroes() {
  const q = useQuery<{ items: PadraoResumo[] }>({
    queryKey: studioKeys.qual(),
    queryFn: () => api.get<{ items: PadraoResumo[] }>("/api/qualificacao/padroes"),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return { ...toView(q), data: q.data?.items };
}

export function usePadraoVersoes(chave: string | null | undefined) {
  const q = useQuery<{ items: PadraoVersaoMeta[] }>({
    queryKey: studioKeys.qualVersoes(chave ?? ""),
    queryFn: () => api.get<{ items: PadraoVersaoMeta[] }>(`/api/qualificacao/padroes/${seg(chave as string)}/versoes`),
    enabled: !!chave,
    retry: false,
    placeholderData: (prev) => prev,
  });
  return { ...toView(q), data: q.data?.items };
}

export function usePadraoVersao(versaoId: string | null | undefined) {
  const q = useQuery<PadraoVersao>({
    queryKey: studioKeys.qualVersao(versaoId ?? ""),
    queryFn: () => api.get<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId as string)}`),
    enabled: !!versaoId,
    retry: false,
    // A different version must never paint under the previous one's id.
    placeholderData: undefined,
  });
  return toView(q);
}

/** Commit the full version a write returned into its cache entry; the version list settles behind. */
function useVersionWrite<TVars>(chave: string, versaoId: string, mutationFn: (vars: TVars) => Promise<PadraoVersao>) {
  return useCacheWriteMutation<PadraoVersao, TVars>({
    mutationFn,
    targets: [{ queryKey: studioKeys.qualVersao(versaoId), commit: (_old, v) => v }],
    invalidate: [studioKeys.qualVersoes(chave)],
  });
}

export function useCriarRascunhoPadrao(chave: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<PadraoVersao, { copiar_de?: string; notas?: string }>({
    mutationFn: (body) => api.post<PadraoVersao>(`/api/qualificacao/padroes/${seg(chave)}/versoes`, body),
    targets: [],
    invalidate: [studioKeys.qualVersoes(chave)],
    // The new draft's id is only known from the answer: seed its entry so opening it is instant.
    onSuccess: (v) => {
      qc.setQueryData(studioKeys.qualVersao(v.id), v);
    },
  });
}

export function useDescartarRascunhoPadrao(chave: string) {
  const qc = useQueryClient();
  return useCacheWriteMutation<null, { versaoId: string }>({
    mutationFn: ({ versaoId }) => api.delete<null>(`/api/qualificacao/versoes/${seg(versaoId)}`),
    // A discarded draft leaves the version list on the click.
    targets: ({ versaoId }) => [
      {
        queryKey: studioKeys.qualVersoes(chave),
        optimistic: (old: { items: PadraoVersaoMeta[] } | undefined) =>
          listOps.within(old, "items", (l) => listOps.remove(l, versaoId)),
      },
    ],
    onSuccess: (_r, { versaoId }) => {
      qc.removeQueries({ queryKey: studioKeys.qualVersao(versaoId) });
    },
  });
}

export function useSalvarCriterio(chave: string, versaoId: string) {
  return useVersionWrite<{ chave: string; criterio: QualCriterioInput }>(chave, versaoId, ({ chave: c, criterio }) =>
    api.put<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/criterios/${seg(c)}`, criterio),
  );
}

export function useRemoverCriterio(chave: string, versaoId: string) {
  return useVersionWrite<{ chave: string }>(chave, versaoId, ({ chave: c }) =>
    api.delete<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/criterios/${seg(c)}`),
  );
}

export function useSalvarEstagio(chave: string, versaoId: string) {
  return useVersionWrite<{ chave: string; estagio: QualEstagioInput }>(chave, versaoId, ({ chave: c, estagio }) =>
    api.put<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/estagios/${seg(c)}`, estagio),
  );
}

export function useRemoverEstagio(chave: string, versaoId: string) {
  return useVersionWrite<{ chave: string }>(chave, versaoId, ({ chave: c }) =>
    api.delete<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/estagios/${seg(c)}`),
  );
}

export function useSalvarParametros(chave: string, versaoId: string) {
  return useVersionWrite<QualParametros>(chave, versaoId, (p) =>
    api.put<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/parametros`, p),
  );
}

export function useValidarPadrao(versaoId: string) {
  return useMutation<ValidarResposta, unknown, void>({ // noc-allow: invalidate-only — a dry validation: returns a one-off ValidarResposta, changes nothing and has no cached read
    mutationFn: () => api.post<ValidarResposta>(`/api/qualificacao/versoes/${seg(versaoId)}/validar`, {}),
  });
}

export function usePublicarPadrao(chave: string, versaoId: string) {
  return useVersionWrite<void>(chave, versaoId, () =>
    api.post<PadraoVersao>(`/api/qualificacao/versoes/${seg(versaoId)}/publicar`, {}),
  );
}
