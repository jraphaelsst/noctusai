/**
 * `/contexto` -- who Mônica is, in her own words. The seed `OrgSpecsForm` over `/api/contexto` (monica's proxy to
 * the agents org specs; the user's token is forwarded, so only an org admin reads or saves). What is written here
 * is what her future lead agent will know about her -- nothing is sent anywhere else.
 */
import { OrgSpecsForm } from "@noctusai/lib/components";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { CONTEXTO_AGENT_KEY, contextoHooks } from "@/lib/crm";

export default function Contexto() {
  const isAdmin = useIsOrgAdmin();
  return (
    <div className="space-y-4" data-testid="contexto-page">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Contexto</h1>
        <p className="text-sm text-muted-foreground">
          Conte aqui quem você é, como trabalha e como gosta de falar. É a base para o atendimento ser a sua cara.
        </p>
      </div>
      <OrgSpecsForm
        hooks={contextoHooks}
        agentKey={CONTEXTO_AGENT_KEY}
        canEdit={isAdmin}
        intro="Preencha só o que fizer sentido; nada aqui é obrigatório. Você pode voltar e ajustar quando quiser."
        emptyMessage="O contexto ainda não está disponível. Assim que for liberado, os campos aparecem aqui."
      />
    </div>
  );
}
