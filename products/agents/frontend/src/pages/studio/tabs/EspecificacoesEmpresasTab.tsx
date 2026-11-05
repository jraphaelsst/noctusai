/**
 * Agent Studio — "Especificações por empresa" (owner decision 2026-11-05): the NoctusAI operator fills the details the
 * agent needs about a company that has the agent GRANTED to a product (name, CRECI, ...) — the company itself gets no
 * agents access. The permission is the grant (live + editor `plataforma`) AND the operator's login; the server enforces
 * both (409 `sem_concessao_ativa`, 403 `platform_admin_required`). The form is the same seed organ the org tab uses,
 * bound to the chosen company; every save is audited server-side with the real person.
 */
import { useState } from "react";
import { OrgSpecsForm } from "@noctusai/lib/components";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useGrantOpcoes } from "@/hooks/useGrants";
import { staffOrgSpecsHooks, staffSpecsKey, useOrgsComConcessao } from "@/hooks/studio/useStaffOrgSpecs";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";
import { errorMessage } from "@/lib/errors";
import { REGRA_FIXA_ROTULO } from "./EspecificacoesOrgTab";

const STATUS_ROTULO: Record<string, string> = {
  ativo: "concessão ativa",
  pendente: "concessão em andamento",
  expirado: "concessão expirada",
};

export default function EspecificacoesEmpresasTab({ agentKey }: { agentKey: string }) {
  const admin = useIsPlatformAdmin();
  const opcoes = useGrantOpcoes("");
  const produtos = (opcoes.data?.produtos ?? []).filter((p) => p.agent_keys.includes(agentKey));
  const [produtoEscolhido, setProduto] = useState("");
  const product = produtoEscolhido || (produtos.length === 1 ? produtos[0].slug : "");
  const orgs = useOrgsComConcessao(agentKey, product);
  const [orgId, setOrgId] = useState("");

  if (!admin) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="empresas-restrito">
        Restrito à equipe da NoctusAI.
      </p>
    );
  }
  if (opcoes.showSkeleton) return <StudioLoading rows={2} testId="empresas-skeleton" />;
  if (opcoes.isError && !opcoes.data) return <StudioError error={opcoes.error} onRetry={opcoes.refetch} />;
  if (produtos.length === 0) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="empresas-sem-produto">
        Este agente ainda não pode ser concedido a nenhum produto.
      </p>
    );
  }
  const seletorProduto =
    produtos.length > 1 ? (
      <div className="space-y-1">
        <label htmlFor="empresa-produto" className="text-sm font-medium">
          Produto
        </label>
        <select
          id="empresa-produto"
          data-testid="empresa-produto"
          className="h-9 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm"
          value={product}
          onChange={(e) => {
            setProduto(e.target.value);
            setOrgId("");
          }}
        >
          <option value="">Selecione um produto…</option>
          {produtos.map((p) => (
            <option key={p.slug} value={p.slug}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
    ) : null;
  if (!product) return <div className="space-y-4">{seletorProduto}</div>;
  if (orgs.showSkeleton) return <StudioLoading rows={2} testId="empresas-skeleton" />;
  if (orgs.isError && !orgs.data) return <StudioError error={orgs.error} onRetry={orgs.refetch} />;
  const items = orgs.data?.items ?? [];
  if (items.length === 0) {
    return (
      <div className="space-y-4">
        {seletorProduto}
        <p className="text-sm text-muted-foreground" data-testid="empresas-vazio">
          Nenhuma empresa tem este agente concedido a este produto ainda.
        </p>
      </div>
    );
  }
  const escolhida = items.find((o) => o.org_id === orgId);

  return (
    <div className="space-y-4" data-testid="empresas-tab">
      {seletorProduto}
      <div className="space-y-1">
        <label htmlFor="empresa-picker" className="text-sm font-medium">
          Empresa
        </label>
        <select
          id="empresa-picker"
          data-testid="empresa-picker"
          className="h-9 w-full max-w-md rounded-md border border-input bg-background px-3 text-sm"
          value={orgId}
          onChange={(e) => setOrgId(e.target.value)}
        >
          <option value="">Selecione uma empresa…</option>
          {items.map((o) => (
            <option key={o.org_id} value={o.org_id}>
              {(o.nome ?? o.org_id) + " — " + (STATUS_ROTULO[o.status] ?? o.status)}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">
          Você está preenchendo os dados desta empresa como equipe NoctusAI. Cada alteração fica registrada com o seu nome.
          {orgs.isRefreshing ? " Atualizando a lista…" : ""}
        </p>
      </div>
      {!escolhida ? (
        <p className="text-sm text-muted-foreground" data-testid="empresas-escolha">
          Escolha uma empresa para ver e preencher as especificações.
        </p>
      ) : !escolhida.editavel ? (
        <p className="text-sm text-amber-700" data-testid="empresas-bloqueada">
          {escolhida.especificacoes_editor !== "plataforma"
            ? "As especificações desta empresa não são editadas pela equipe NoctusAI."
            : `Não é possível editar agora: ${STATUS_ROTULO[escolhida.status] ?? escolhida.status}.`}
        </p>
      ) : (
        <OrgSpecsForm
          key={escolhida.org_id}
          hooks={staffOrgSpecsHooks}
          agentKey={staffSpecsKey(agentKey, product, escolhida.org_id)}
          canEdit
          intro={`Dados de ${escolhida.nome ?? "da empresa"} para o agente.`}
          emptyMessage="A plataforma ainda não pediu nenhuma especificação para este agente."
          conflictLabels={REGRA_FIXA_ROTULO}
          formatError={errorMessage}
          data-testid="empresas-form"
        />
      )}
    </div>
  );
}
