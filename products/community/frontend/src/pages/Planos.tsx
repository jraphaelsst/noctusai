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
 * Ninho Vazio (CONTRACT.md §Tiers, FE-A): the form gains the
 * `entitlements.grupoterapia` level select (nenhum/ouvir/falar), and a
 * "Criar planos padrão" banner (`POST /api/planos/padrao`, idempotent by
 * `nome`) shows while any of Gratuito/Ouvinte/Premium is missing.
 *
 * `ativo` is NOT a form field: the DELETE endpoint already soft-deletes
 * (`ativo=false`, 204) — the "ativo toggle" the contract asks for — and a
 * per-row action reactivates (`PATCH {ativo:true}`), since a soft-deleted
 * plano needs a way back that a delete button alone doesn't give it.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { ResourceManager } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatBRLFromCents, centsToReais, reaisToCents } from "@/lib/money";
import {
  NIVEL_GRUPOTERAPIA_LABELS,
  PLANOS_PADRAO,
  useCriarPlanosPadrao,
  usePlanos,
  type NivelGrupoterapia,
  type Plano,
} from "@/hooks/usePlanos";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { PlanoGruposDialog } from "@/pages/planos/PlanoGruposDialog";
import { GatewayRefsBadges, GatewayRefsDialog } from "@/pages/planos/GatewayRefsDialog";

// NOC-REMEDIATE[community-entitlements-modules]: the Feed / Fórum / Chat /
// Eventos / "Todo o conteúdo" toggles were removed from the form because
// those modules do not exist in the product yet (no routes, no pages) — a
// toggle for a non-existent module lies. They return when the modules ship.
// Stored values of those keys are NOT wiped: the full entitlements object is
// round-tripped through `_entitlements_raw` and spread back on save.

function toForm(row: Plano): Record<string, any> {
  const form: Record<string, any> = {
    nome: row.nome,
    descricao: row.descricao ?? "",
    preco_reais: centsToReais(row.preco_centavos),
    ciclo: row.ciclo,
    ordem: row.ordem,
    // Carried through untouched: every stored key (incl. removed module
    // toggles + conteudo_ids + grupos_whatsapp, edited via its own dialog).
    _entitlements_raw: row.entitlements ?? {},
    grupoterapia: row.entitlements?.grupoterapia ?? "nenhum",
  };
  return form;
}

function toPayload(form: Record<string, any>): Record<string, any> {
  const raw: Record<string, any> = form._entitlements_raw ?? {};
  const entitlements: Record<string, any> = {
    conteudo_ids: [],
    grupos_whatsapp: [],
    ...raw,
    grupoterapia: (form.grupoterapia || "nenhum") as NivelGrupoterapia,
  };
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
  // ResourceManager has no custom-field seam (flat text/select/checkbox only),
  // so the grupos multi-select lives in a row-action dialog like Gateways.
  const [gruposDialogFor, setGruposDialogFor] = useState<Plano | null>(null);
  const isAdmin = useIsAdmin();
  const planos = usePlanos({ page_size: 100 });
  const criarPadrao = useCriarPlanosPadrao();
  const nomesExistentes = new Set((planos.data?.items ?? []).map((p) => p.nome.trim().toLowerCase()));
  // Only once the list has really loaded — never flash the banner over an
  // unknown state.
  const faltantes = planos.data ? PLANOS_PADRAO.filter((n) => !nomesExistentes.has(n.toLowerCase())) : [];

  async function handleCriarPadrao() {
    try {
      const res = await criarPadrao.mutateAsync();
      toast.success(
        res.criados.length ? `Planos criados: ${res.criados.join(", ")}.` : "Os planos padrão já existiam.",
      );
      setReloadTick((n) => n + 1);
    } catch (err) {
      toast.error("Erro ao criar planos padrão", { description: errorMessage(err) });
    }
  }

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
    {isAdmin && faltantes.length > 0 && (
      <div
        className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 p-4"
        data-testid="planos-padrao-banner"
      >
        <p className="text-sm text-foreground">
          Faltam os planos padrão do Ninho Vazio: <strong>{faltantes.join(", ")}</strong>.
        </p>
        <Button variant="primary" size="sm" onClick={() => void handleCriarPadrao()} disabled={criarPadrao.isPending}>
          {criarPadrao.isPending ? "Criando..." : "Criar planos padrão"}
        </Button>
      </div>
    )}
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
      onMutate={() => void planos.refetch()}
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
        {
          key: "grupoterapia",
          header: "Grupoterapia",
          render: (row) => NIVEL_GRUPOTERAPIA_LABELS[row.entitlements?.grupoterapia ?? "nenhum"],
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
          render: (row) => <GatewayRefsBadges planoId={row.id} gratuito={row.preco_centavos === 0} />,
        },
        {
          key: "grupos_whatsapp",
          header: "Grupos WhatsApp",
          render: (row) => (row.entitlements?.grupos_whatsapp ?? []).length,
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
        {
          name: "grupoterapia",
          label: "Grupoterapia",
          type: "select",
          required: true,
          defaultValue: "nenhum",
          options: (Object.keys(NIVEL_GRUPOTERAPIA_LABELS) as NivelGrupoterapia[]).map((n) => ({
            value: n,
            label: NIVEL_GRUPOTERAPIA_LABELS[n],
          })),
        },
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
          <button
            type="button"
            className="text-sm border border-border bg-card text-foreground rounded-md px-3 py-1.5 hover:bg-accent transition-colors"
            onClick={() => setGruposDialogFor(row)}
          >
            Grupos WhatsApp
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
      {gruposDialogFor && (
        <PlanoGruposDialog
          plano={gruposDialogFor}
          onClose={() => setGruposDialogFor(null)}
          onSaved={() => {
            setGruposDialogFor(null);
            setReloadTick((n) => n + 1);
          }}
        />
      )}
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
