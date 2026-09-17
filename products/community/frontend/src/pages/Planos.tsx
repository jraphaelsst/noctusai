/**
 * Planos — `/planos` (community-m1-contract.md §Frontend).
 *
 * A flat, manager-configured CRUD entity (nome/preço/ciclo/entitlements) —
 * exactly the shape `<ResourceManager/>` (`@noctusai/lib/components`) was
 * formalized for, so this page CONSUMES it rather than hand-rolling a
 * table+modal shell (product-internal-wiring rule). Money is entered in
 * reais and converted to `preco_centavos` on submit via `toPayload`;
 * `entitlements` is a nested jsonb object flattened into individual
 * checkbox fields via `toForm`/`toPayload` (ResourceManager fields are
 * flat by name) — the two array-valued keys (`conteudo_ids`,
 * `grupos_whatsapp`) have no v1 UI yet, so they round-trip untouched
 * through hidden form keys rather than being silently dropped on edit.
 *
 * `ativo` is NOT a form field: the DELETE endpoint already soft-deletes
 * (`ativo=false`, 204) — the "ativo toggle" the contract asks for — and a
 * per-row action reactivates (`PATCH {ativo:true}`), since a soft-deleted
 * plano needs a way back that a delete button alone doesn't give it.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@noctusai/lib/design-system";
import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents, centsToReais, reaisToCents } from "@/lib/money";
import type { Plano } from "@/hooks/usePlanos";
import { GatewayRefsBadges, GatewayRefsDialog } from "@/pages/planos/GatewayRefsDialog";

const ENTITLEMENT_FIELDS = [
  { key: "ent_feed", entKey: "feed", label: "Feed" },
  { key: "ent_forum", entKey: "forum", label: "Fórum" },
  { key: "ent_chat", entKey: "chat", label: "Chat" },
  { key: "ent_eventos", entKey: "eventos", label: "Eventos" },
  { key: "ent_conteudo_todos", entKey: "conteudo_todos", label: "Todo o conteúdo" },
] as const;

function toForm(row: Plano): Record<string, any> {
  const form: Record<string, any> = {
    nome: row.nome,
    descricao: row.descricao ?? "",
    preco_reais: centsToReais(row.preco_centavos),
    ciclo: row.ciclo,
    ordem: row.ordem,
    // Carried through untouched — no v1 UI for these two array keys.
    _conteudo_ids: row.entitlements?.conteudo_ids ?? [],
    _grupos_whatsapp: row.entitlements?.grupos_whatsapp ?? [],
  };
  for (const f of ENTITLEMENT_FIELDS) {
    form[f.key] = !!row.entitlements?.[f.entKey as keyof typeof row.entitlements];
  }
  return form;
}

function toPayload(form: Record<string, any>): Record<string, any> {
  const entitlements: Record<string, any> = {
    conteudo_ids: form._conteudo_ids ?? [],
    grupos_whatsapp: form._grupos_whatsapp ?? [],
  };
  for (const f of ENTITLEMENT_FIELDS) {
    entitlements[f.entKey] = !!form[f.key];
  }
  return {
    nome: form.nome,
    descricao: form.descricao || null,
    preco_centavos: reaisToCents(form.preco_reais ?? 0),
    ciclo: form.ciclo,
    ordem: Number(form.ordem) || 0,
    entitlements,
  };
}

export default function Planos() {
  // Bumped after a reactivate side-channel mutation to force ResourceManager
  // to refetch (it owns its own fetch/reload cycle internally).
  const [reloadTick, setReloadTick] = useState(0);
  // community-m2-contract.md: per-tier gateway reference dialog (Stripe
  // Price id / Asaas ref) — a sub-resource on its own endpoint, so it opens
  // from a row action rather than living inside ResourceManager's own
  // create/edit form (which has no seam for a different backend call).
  const [gatewayDialogFor, setGatewayDialogFor] = useState<Plano | null>(null);

  async function handleReativar(row: Plano) {
    try {
      await api.patch(`/api/planos/${row.id}`, { ativo: true });
      toast.success("Plano reativado");
      setReloadTick((n) => n + 1);
    } catch (err) {
      toast.error("Erro ao reativar plano", { description: errorMessage(err) });
    }
  }

  return (
    <>
    <ResourceManager<Plano>
      key={reloadTick}
      title="Planos"
      description="Tiers pagos da comunidade — nome, preço, ciclo e permissões."
      api={api}
      apiPath="/api/planos"
      singularName="Plano"
      deleteLabel="Desativar"
      toForm={toForm}
      toPayload={toPayload}
      emptyMessage="Nenhum plano cadastrado. Crie o primeiro!"
      columns={[
        { key: "nome", header: "Nome" },
        {
          key: "preco_centavos",
          header: "Preço",
          render: (row) => formatBRLFromCents(row.preco_centavos),
        },
        {
          key: "ciclo",
          header: "Ciclo",
          render: (row) => (row.ciclo === "mensal" ? "Mensal" : "Anual"),
        },
        { key: "membros_ativos", header: "Membros ativos" },
        {
          key: "ativo",
          header: "Status",
          render: (row) => (
            <Badge variant={row.ativo ? "default" : "muted"}>{row.ativo ? "Ativo" : "Inativo"}</Badge>
          ),
        },
        {
          key: "gateways",
          header: "Gateways",
          render: (row) => <GatewayRefsBadges planoId={row.id} />,
        },
      ]}
      fields={[
        { name: "nome", label: "Nome", required: true, placeholder: "Ex: Círculo" },
        { name: "descricao", label: "Descrição", type: "textarea", placeholder: "Descrição opcional" },
        {
          name: "preco_reais",
          label: "Preço (R$)",
          type: "number",
          required: true,
          min: 0,
          step: 0.01,
        },
        {
          name: "ciclo",
          label: "Ciclo",
          type: "select",
          required: true,
          options: [
            { value: "mensal", label: "Mensal" },
            { value: "anual", label: "Anual" },
          ],
        },
        { name: "ordem", label: "Ordem", type: "number", defaultValue: 0 },
        ...ENTITLEMENT_FIELDS.map((f) => ({
          name: f.key,
          label: f.label,
          type: "checkbox" as const,
        })),
      ]}
      rowActions={(row) => (
        <>
          <button
            type="button"
            className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
            onClick={() => setGatewayDialogFor(row)}
          >
            Gateways
          </button>
          {!row.ativo && (
            <button
              type="button"
              className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
              onClick={() => void handleReativar(row)}
            >
              Reativar
            </button>
          )}
        </>
      )}
    />
      {gatewayDialogFor && (
        <GatewayRefsDialog
          planoId={gatewayDialogFor.id}
          planoNome={gatewayDialogFor.nome}
          onClose={() => setGatewayDialogFor(null)}
        />
      )}
    </>
  );
}
