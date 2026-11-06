/**
 * Agent Studio — STAFF-only org specs, authorised by the GRANT (owner decision 2026-11-05): a NoctusAI platform admin
 * fills a company's specs when that company has a live (agent, product, org) grant whose editor is `plataforma`.
 *
 *   GET      /api/studio/plataforma/agents/{key}/products/{product}/orgs                   orgs with a live grant (+ status)
 *   GET|PUT  /api/studio/plataforma/agents/{key}/products/{product}/orgs/{org_id}/specs    that org's form + values
 *
 * The form is the seed organ `OrgSpecsForm`; its hooks are bound to ONE (agent, product, org) through a composite key,
 * so company A's cache entry is never shown under company B. A save commits the server's answer into that entry.
 */
import { useQuery } from "@tanstack/react-query";
import { createOrgSpecsHooks } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { keepWithinAgent, seg, studioKeys, toView } from "./keys";

export interface OrgComConcessao {
  org_id: string;
  nome: string | null;
  grant_id: string;
  /** "pendente" | "ativo" | "expirado" (an `ativo` row past its expiry). */
  status: string;
  expires_at: string | null;
  especificacoes_editor: string;
  /** True only when the staff may edit NOW (live grant, editor = plataforma). */
  editavel: boolean;
}
export interface OrgsComConcessao {
  agent_key: string;
  product: string;
  items: OrgComConcessao[];
}

const SEP = "::";
export const staffSpecsKey = (agentKey: string, product: string, orgId: string) =>
  [agentKey, product, orgId].join(SEP);
const split = (composite: string): [string, string, string] => {
  const [key, product, orgId] = composite.split(SEP);
  return [key, product, orgId];
};

export const staffOrgSpecsHooks = createOrgSpecsHooks(api, {
  path: (composite) => {
    const [key, product, orgId] = split(composite);
    return `/api/studio/plataforma/agents/${seg(key)}/products/${seg(product)}/orgs/${seg(orgId)}/specs`;
  },
  queryKey: (composite) => {
    const [key, product, orgId] = split(composite);
    return studioKeys.staffOrgSpecs(key, product, orgId);
  },
});

export function useOrgsComConcessao(agentKey: string, product: string) {
  const q = useQuery<OrgsComConcessao>({
    queryKey: studioKeys.staffOrgs(agentKey, product),
    queryFn: () =>
      api.get<OrgsComConcessao>(`/api/studio/plataforma/agents/${seg(agentKey)}/products/${seg(product)}/orgs`),
    enabled: !!agentKey && !!product,
    retry: false,
    placeholderData: keepWithinAgent<OrgsComConcessao>(agentKey),
  });
  return toView(q);
}
