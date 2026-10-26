/**
 * Agent Studio — Julia v2 CONTENT API (CONTRACT §2.4, §2.6): the DB rows the model reads.
 *
 *   GET  /api/studio/agents/{key}/versions/{vid}/{textos|ferramentas|decisoes|specs}   platform admin
 *   PUT  /api/studio/agents/{key}/draft/{textos|ferramentas|decisoes|specs}            replace-set
 *   GET  /api/studio/agents/{key}/versions/{vid}/payload                               platform admin
 *   GET|PUT /api/studio/agents/{key}/specs · GET .../status                            org admin
 *   GET  /api/studio/agents/{key}/compilado?versao=ativa|rascunho                      platform admin
 *   GET|PUT /api/studio/plataforma/textos                                              platform admin
 *
 * Every write commits the server's answer into the read it feeds (cache-writes contract) and
 * settles the derived views by background refetch. The replace-set routes carry no `expected_hash`, so the
 * optimistic lock is a compare-before-write: the form passes the snapshot it was seeded from
 * and `useSaveDraftSet` refuses (`DraftConflictError`) when the server's rows moved since.
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { createOrgSpecsHooks } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import type {
  CompiladoOrg,
  ConteudoKind,
  ConteudoPayload,
  ConteudoRowByKind,
  ConteudoSetOut,
  OrgStatus,
  PlataformaTexto,
} from "@/api/studio/types-julia";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

const base = (key: string) => `/api/studio/agents/${seg(key)}`;

/** The draft moved on the server between loading the form and saving it. */
export class DraftConflictError extends Error {
  constructor() {
    super("Outra pessoa alterou este rascunho enquanto você editava. Recarregue para ver a versão do servidor.");
    this.name = "DraftConflictError";
  }
}

/** Content identity of a row set (server ids are not content; a replace may reissue them). */
export function snapshotOf<T extends { id?: string }>(itens: T[]): string {
  return JSON.stringify(itens.map(({ id: _id, ...rest }) => rest));
}

export function useVersionContent<K extends ConteudoKind>(key: string, kind: K, versionId: string | null | undefined) {
  const q = useQuery<ConteudoSetOut<ConteudoRowByKind[K]>>({
    queryKey: studioKeys.conteudo(key, kind, versionId ?? ""),
    queryFn: () => api.get<ConteudoSetOut<ConteudoRowByKind[K]>>(`${base(key)}/versions/${seg(versionId as string)}/${kind}`),
    enabled: !!key && !!versionId,
    placeholderData: keepWithinAgent<ConteudoSetOut<ConteudoRowByKind[K]>>(key),
  });
  return toView(q);
}

export function useSaveDraftSet<K extends ConteudoKind>(key: string, kind: K, versionId: string | null | undefined) {
  type Out = ConteudoSetOut<ConteudoRowByKind[K]>;
  // Commit-only: the replace-set may reissue row ids, so the server's set (not the form's) is what is cached.
  return useCacheWriteMutation<Out, { itens: Array<Omit<ConteudoRowByKind[K], "id">>; baseSnapshot: string }>({
    mutationFn: async ({ itens, baseSnapshot }) => {
      const fresh = await api.get<Out>(`${base(key)}/versions/${seg(versionId as string)}/${kind}`);
      if (snapshotOf(fresh.itens) !== baseSnapshot) throw new DraftConflictError();
      return api.put<Out>(`${base(key)}/draft/${kind}`, { itens });
    },
    targets: [
      {
        queryKey: ["studio", key, "conteudo", kind],
        match: "prefix",
        commit: (old: Out | undefined, saved: Out) => (old && old.version_id === saved.version_id ? saved : old),
      },
    ],
    // Everything the content feeds is derived: refreshed in the background.
    invalidate: [
      studioKeys.detail(key),
      studioKeys.compiledAll(key),
      ["studio", key, "payload"],
      ["studio", key, "compilado-org"],
    ],
  });
}

export function usePayload(key: string, versionId: string | null | undefined) {
  const q = useQuery<ConteudoPayload>({
    queryKey: studioKeys.payload(key, versionId ?? ""),
    queryFn: () => api.get<ConteudoPayload>(`${base(key)}/versions/${seg(versionId as string)}/payload`),
    enabled: !!key && !!versionId,
    retry: false,
    placeholderData: keepWithinAgent<ConteudoPayload>(key),
  });
  return toView(q);
}

// ── org side ────────────────────────────────────────────────────────────────

// The specs form is the seed organ's hooks (also used by other products); agents adds its derived views.
export const orgSpecsHooks = createOrgSpecsHooks(api, {
  path: (key) => `${base(key)}/specs`,
  queryKey: studioKeys.orgSpecs,
  // Completeness status, controls and the org compile are computed from the values.
  invalidate: (key) => [studioKeys.orgStatus(key), studioKeys.controle(key), ["studio", key, "compilado-org"]],
});
export const { useOrgSpecs, useUpdateOrgSpecs } = orgSpecsHooks;

export function useOrgStatus(key: string, enabled = true) {
  const q = useQuery<OrgStatus>({
    queryKey: studioKeys.orgStatus(key),
    queryFn: () => api.get<OrgStatus>(`${base(key)}/status`),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<OrgStatus>(key),
  });
  return toView(q);
}

export function useCompiladoOrg(key: string, versao: "ativa" | "rascunho", enabled = true) {
  const q = useQuery<CompiladoOrg>({
    queryKey: studioKeys.compiladoOrg(key, versao),
    queryFn: () => api.get<CompiladoOrg>(`${base(key)}/compilado`, { versao }),
    enabled: !!key && enabled,
    retry: false,
    placeholderData: keepWithinAgent<CompiladoOrg>(key),
  });
  return toView(q);
}

// ── platform texts ──────────────────────────────────────────────────────────

export function usePlataformaTextos() {
  const q = useQuery<{ itens: PlataformaTexto[] }>({
    queryKey: studioKeys.plataformaTextos(),
    queryFn: () => api.get<{ itens: PlataformaTexto[] }>("/api/studio/plataforma/textos"),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}

export function useSetPlataformaTextos() {
  return useCacheWriteMutation<{ itens: PlataformaTexto[] }, { itens: Record<string, string> }>({
    mutationFn: (payload) => api.put<{ itens: PlataformaTexto[] }>("/api/studio/plataforma/textos", payload),
    targets: [{ queryKey: studioKeys.plataformaTextos(), commit: (_old, saved) => saved }],
  });
}
