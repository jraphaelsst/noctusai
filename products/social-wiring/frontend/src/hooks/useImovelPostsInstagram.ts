/**
 * "Post do Instagram" of an imóvel — the Instagram posts/reels that advertise it, so Julia resolves a lead's pasted post
 * link to this listing. Backed by `/api/julia/post-instagram-imovel` (list by `codigo_imovel`, PUT upsert, DELETE).
 * Own file on purpose (`useImovelDados.ts` is a hot file).
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@noctusai/seed/infra";

const BASE = "/api/julia/post-instagram-imovel";
const KEY = (codigo: string) => ["sw", "imovel", codigo, "postsInstagram"] as const;

export interface ImovelPostInstagram {
  id: string;
  shortcode: string;
  codigo_imovel: string;
  permalink: string | null;
  created_at: string;
}

export function useImovelPostsInstagram(codigo: string | null) {
  return useQuery({
    queryKey: KEY(codigo ?? "__none__"),
    queryFn: async () => {
      const res = await api.get<{ data: ImovelPostInstagram[] }>(`${BASE}?codigo_imovel=${encodeURIComponent(codigo as string)}`);
      return res?.data ?? [];
    },
    enabled: !!codigo,
    placeholderData: (prev) => prev,
  });
}

export function useImovelPostInstagramMutations(codigo: string) {
  // A re-added shortcode comes back as the same row (PUT upserts by org + shortcode): `commit` drops any older copy first.
  const adicionar = useCacheWriteMutation<ImovelPostInstagram, { url: string }>({
    mutationFn: async ({ url }) => (await api.put<{ data: ImovelPostInstagram }>(BASE, { url, codigo_imovel: codigo })).data,
    targets: [
      {
        queryKey: KEY(codigo),
        optimistic: (old: ImovelPostInstagram[] | undefined, { url }, ctx) =>
          listOps.prepend(old, {
            id: ctx.tempId,
            shortcode: url.trim(),
            codigo_imovel: codigo,
            permalink: null,
            created_at: new Date().toISOString(),
          }),
        commit: (old: ImovelPostInstagram[] | undefined, saved, _vars, ctx) =>
          listOps.replace((old ?? []).filter((p) => p.id !== saved.id), ctx.tempId, saved, "prepend"),
      },
    ],
  });

  const remover = useCacheWriteMutation<unknown, { id: string }>({
    mutationFn: ({ id }) => api.delete(`${BASE}/${encodeURIComponent(id)}`),
    targets: [
      {
        queryKey: KEY(codigo),
        optimistic: (old: ImovelPostInstagram[] | undefined, { id }) => listOps.remove(old, id),
      },
    ],
  });
  return { adicionar, remover };
}
