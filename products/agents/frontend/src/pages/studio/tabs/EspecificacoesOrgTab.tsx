/**
 * Agent Studio — "Especificações da org" (Julia v2 CONTRACT §2.6, Q2): the ORG's own values for the
 * placeholders the platform definition declares. The form is the seed organ `OrgSpecsForm`
 * (`@noctusai/lib/components`); what stays here is agents' own copy: the admin gate, the locked-rules
 * notice and the names of the locked blocks. A text that contradicts a platform-locked rule is refused by
 * the server (422 `spec_conflita_com_regra_fixa`) and the organ shows the refusal on the offending field.
 */
import { Lock } from "lucide-react";
import { OrgSpecsForm } from "@noctusai/lib/components";
import { orgSpecsHooks } from "@/hooks/studio/useConteudo";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";

/** Labels of the platform-locked blocks. Names only: the rule text is never sent to an org. */
export const REGRA_FIXA_ROTULO: Record<string, string> = {
  divulgacao_ia: "Aviso de que é um assistente virtual",
  opt_out: "Pedido do lead para parar de receber mensagens",
  escalonamento_humano: "Passagem da conversa para uma pessoa",
  escopo_imobiliario: "Atendimento restrito a assuntos imobiliários",
};

const NOTICE = (
  <p className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="specs-bloco-travado">
    <Lock className="h-3.5 w-3.5" /> As regras da plataforma (aviso de assistente virtual, parar de receber mensagens, passagem para uma pessoa, escopo imobiliário) são fixas e não podem ser alteradas aqui.
  </p>
);

export default function EspecificacoesOrgTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  return (
    <OrgSpecsForm
      hooks={orgSpecsHooks}
      agentKey={agentKey}
      canEdit={isAdmin}
      intro="Preencha como o agente deve falar da sua empresa."
      emptyMessage="A plataforma ainda não pediu nenhuma especificação para a sua organização."
      notice={NOTICE}
      conflictLabels={REGRA_FIXA_ROTULO}
      formatError={errorMessage}
    />
  );
}
