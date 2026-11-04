/**
 * Platform grants (Julia-line S3 routes, platform admin only): an agent wired to a product for an org.
 *
 *   GET    /api/studio/plataforma/grants              list `{items, total}`
 *   GET    /api/studio/plataforma/grants/opcoes       the pickers `{produtos, orgs}` (orgs searchable with `q`)
 *   POST   /api/studio/plataforma/grants              create = mint + deliver
 *   POST   /api/studio/plataforma/grants/{id}/rotate  overlapping rotation
 *   DELETE /api/studio/plataforma/grants/{id}         revoke (204, idempotent)
 *
 * No response carries a secret; nobody copies or pastes a token. Every write puts the server's answer in the list.
 */
import { useQuery } from "@tanstack/react-query";
import { listOps, useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import { seg, toView } from "@/hooks/studio/keys";

export type GrantStatus = "pendente" | "ativo" | "revogado" | "falhou";

export interface Grant {
  id: string;
  org_id: string;
  org_nome: string | null;
  agent_id: string;
  agent_key: string;
  product: string;
  status: GrantStatus;
  channel_token_id: string | null;
  product_token_id: string | null;
  expires_at: string | null;
  created_at: string | null;
  revoked_at: string | null;
  last_delivered_at: string | null;
  last_error: string | null;
}

export interface GrantList {
  items: Grant[];
  total: number;
}

export interface GrantProduto {
  slug: string;
  label: string;
  agent_keys: string[];
}

export interface GrantOrg {
  id: string;
  nome: string;
  slug: string | null;
}

export interface GrantOpcoes {
  produtos: GrantProduto[];
  orgs: GrantOrg[];
}

export interface GrantCreateInput {
  agent_key: string;
  product: string;
  org_id: string;
  /** `undefined` = never expires. */
  expira_em_dias?: number;
}

const BASE = "/api/studio/plataforma/grants";

export const grantKeys = {
  list: () => ["agents", "plataforma", "grants"] as const,
  opcoes: (q: string) => ["agents", "plataforma", "grants-opcoes", q] as const,
};

/** First 4 + last 4 of a token prefix, the middle masked. The API sends no secret; this masks what is shown. */
export function maskToken(value: string | null | undefined): string {
  if (!value) return "—";
  if (value.length <= 8) return `${value.slice(0, 4)}••••`;
  return `${value.slice(0, 4)}••••${value.slice(-4)}`;
}

export function useGrants() {
  const q = useQuery<GrantList>({
    queryKey: grantKeys.list(),
    queryFn: () => api.get<GrantList>(BASE),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}

export function useGrantOpcoes(search: string) {
  const q = useQuery<GrantOpcoes>({
    queryKey: grantKeys.opcoes(search),
    queryFn: () => api.get<GrantOpcoes>(search ? `${BASE}/opcoes?q=${encodeURIComponent(search)}` : `${BASE}/opcoes`),
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}

export function useCreateGrant() {
  return useCacheWriteMutation<Grant, GrantCreateInput>({
    mutationFn: (payload) => api.post<Grant>(BASE, payload),
    targets: [
      {
        queryKey: grantKeys.list(),
        commit: (old: GrantList | undefined, grant) => listOps.within(old, "items", (l) => listOps.replace<Grant>(l, grant.id, grant, "prepend")),
      },
    ],
  });
}

export function useRotateGrant() {
  return useCacheWriteMutation<Grant, string>({
    mutationFn: (id) => api.post<Grant>(`${BASE}/${seg(id)}/rotate`, {}),
    targets: (id) => [
      {
        queryKey: grantKeys.list(),
        commit: (old: GrantList | undefined, grant) => listOps.within(old, "items", (l) => listOps.replace<Grant>(l, id, grant)),
      },
    ],
  });
}

export function useRevokeGrant() {
  return useCacheWriteMutation<unknown, string>({
    mutationFn: (id) => api.delete(`${BASE}/${seg(id)}`),
    targets: (id) => [
      {
        queryKey: grantKeys.list(),
        optimistic: (old: GrantList | undefined) =>
          listOps.within(old, "items", (l: Grant[]) =>
            l.map((g) => (g.id === id ? { ...g, status: "revogado" as const, revoked_at: g.revoked_at ?? new Date().toISOString() } : g)),
          ),
      },
    ],
  });
}
