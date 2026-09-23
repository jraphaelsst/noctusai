/**
 * Orçamentos — every orçamento of the agency as cards (roadmap R5; wave-2
 * contract Slice C).
 *
 *   • tabs Ativos (rascunho|enviado) · Aceitos · Recusados (recusado|expirado|
 *     substituido) — the server's `aba` param,
 *   • filters: status, lead, período (client-side over `created_at` — the
 *     contract's list endpoint has no date params), busca (`q`),
 *   • "Novo orçamento" picks the negócio first (an orçamento belongs to
 *     exactly one negócio/lead),
 *   • `?id=<orçamento>` deep link opens the modal — the reply-watcher
 *     notification links here (Slice B).
 *
 * Filter + tab state lives in the URL so a shared link reproduces the view.
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FilePlus2, Search } from "lucide-react";
import { Badge, Button, EmptyState, Field, Input, Select, Skeleton } from "@noctusai/lib/design-system";
import { cn } from "@noctusai/lib";

import { SheetDialog } from "@/components/common/SheetDialog";
import { OrcamentoModal } from "@/components/orcamento/OrcamentoModal";
import { MargemBadge } from "@/components/orcamento/TotaisPanel";
import { useLeads } from "@/hooks/useComercial";
import { useOrcamentos } from "@/hooks/useOrcamentos";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import { comercialPipeline } from "@/lib/pipelines";
import { useDebouncedValue } from "@/lib/useDebouncedValue";
import {
  ORCAMENTO_STATUS_LABEL,
  type Orcamento,
  type OrcamentoAba,
  type OrcamentoStatus,
} from "@/types/crm";

const ABAS: { valor: OrcamentoAba; rotulo: string; status: OrcamentoStatus[] }[] = [
  { valor: "ativos", rotulo: "Ativos", status: ["rascunho", "enviado"] },
  { valor: "aceitos", rotulo: "Aceitos", status: ["aceito"] },
  { valor: "recusados", rotulo: "Recusados", status: ["recusado", "expirado", "substituido"] },
];

/** Client-side period filter (inclusive, by `created_at` date). */
export function noPeriodo(o: Pick<Orcamento, "created_at">, de: string, ate: string): boolean {
  const d = (o.created_at ?? "").slice(0, 10);
  if (de && d < de) return false;
  if (ate && d > ate) return false;
  return true;
}

export default function Orcamentos() {
  const [params, setParams] = useSearchParams();
  const aba = (params.get("aba") as OrcamentoAba | null) ?? "ativos";
  const status = (params.get("status") as OrcamentoStatus | null) ?? undefined;
  const leadId = params.get("lead") ?? undefined;
  const de = params.get("de") ?? "";
  const ate = params.get("ate") ?? "";
  const abertoId = params.get("id");

  const [busca, setBusca] = useState(params.get("q") ?? "");
  const q = useDebouncedValue(busca.trim(), 300);

  /**
   * ONE write per interaction: react-router's functional updater reads the
   * params as of the call, so two back-to-back `setParams` calls clobber each
   * other (switching tab AND clearing status lost the tab).
   */
  function setParam(k: string, v: string | null | undefined) {
    setMany({ [k]: v });
  }
  function setMany(changes: Record<string, string | null | undefined>) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [k, v] of Object.entries(changes)) {
          if (v) next.set(k, v);
          else next.delete(k);
        }
        return next;
      },
      { replace: true },
    );
  }

  const { orcamentos, showSkeleton, isRefreshing, isError, error } = useOrcamentos({
    aba,
    status,
    lead_id: leadId,
    q: q || undefined,
  });
  const visiveis = useMemo(() => orcamentos.filter((o) => noPeriodo(o, de, ate)), [orcamentos, de, ate]);
  const { leads } = useLeads();
  const abaAtual = ABAS.find((a) => a.valor === aba) ?? ABAS[0];

  const [novo, setNovo] = useState<{ negocioId: string } | null>(null);
  const [escolhendoNegocio, setEscolhendoNegocio] = useState(false);

  const filtrosAtivos = !!(status || leadId || de || ate || q);

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 overflow-x-hidden p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-foreground">Orçamentos</h1>
          <p className="text-sm text-muted-foreground">Propostas por lead — crie, envie e acompanhe o aceite.</p>
        </div>
        <Button onClick={() => setEscolhendoNegocio(true)} data-testid="orcamentos-novo">
          <FilePlus2 className="mr-1 h-4 w-4" /> Novo orçamento
        </Button>
      </header>

      {/* Tabs */}
      <div role="tablist" aria-label="Situação" className="flex gap-1 rounded-lg bg-muted p-1">
        {ABAS.map((a) => (
          <button
            key={a.valor}
            type="button"
            role="tab"
            aria-selected={aba === a.valor}
            onClick={() => setMany({ aba: a.valor === "ativos" ? null : a.valor, status: null })}
            className={cn(
              "h-9 flex-1 rounded-md text-sm font-medium transition-colors",
              aba === a.valor ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Buscar orçamentos"
            placeholder="Buscar por título, lead ou empresa…"
            value={busca}
            onChange={(e) => {
              setBusca(e.target.value);
              setParam("q", e.target.value.trim() || null);
            }}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Status"
          value={status ?? ""}
          onChange={(e) => setParam("status", e.target.value || null)}
          className="h-10"
        >
          <option value="">Todos os status</option>
          {abaAtual.status.map((s) => (
            <option key={s} value={s}>
              {ORCAMENTO_STATUS_LABEL[s]}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Lead"
          value={leadId ?? ""}
          onChange={(e) => setParam("lead", e.target.value || null)}
          className="h-10 sm:max-w-56"
        >
          <option value="">Todos os leads</option>
          {leads.map((l) => (
            <option key={l.id} value={l.id}>
              {l.empresa || l.nome}
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-2 gap-2 sm:col-span-3 sm:flex sm:items-end">
          <Field label="De">
            <Input type="date" aria-label="De" value={de} onChange={(e) => setParam("de", e.target.value || null)} />
          </Field>
          <Field label="Até">
            <Input type="date" aria-label="Até" value={ate} onChange={(e) => setParam("ate", e.target.value || null)} />
          </Field>
          {filtrosAtivos ? (
            <Button
              variant="ghost"
              size="sm"
              className="col-span-2 sm:col-span-1"
              onClick={() => {
                setBusca("");
                setParams(aba === "ativos" ? {} : { aba }, { replace: true });
              }}
            >
              Limpar filtros
            </Button>
          ) : null}
        </div>
      </div>

      {/* List */}
      {showSkeleton ? (
        <div className="grid gap-3 sm:grid-cols-2" data-testid="orcamentos-loading">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : isError ? (
        <p role="alert" className="py-8 text-center text-sm text-destructive">
          {describeError(error, "Não foi possível carregar os orçamentos.")}
        </p>
      ) : visiveis.length === 0 ? (
        <EmptyState
          message={
            filtrosAtivos
              ? "Nenhum orçamento com esses filtros."
              : aba === "ativos"
                ? "Nenhum orçamento em aberto. Crie um pelo botão acima ou pelo card do lead no Comercial."
                : aba === "aceitos"
                  ? "Nenhum orçamento aceito ainda."
                  : "Nenhum orçamento recusado."
          }
        />
      ) : (
        <ul className={cn("grid gap-3 sm:grid-cols-2", isRefreshing && "opacity-80 transition-opacity")} data-testid="orcamentos-lista">
          {visiveis.map((o) => (
            <li key={o.id}>
              <OrcamentoCard orcamento={o} onAbrir={() => setParam("id", o.id)} />
            </li>
          ))}
        </ul>
      )}

      <EscolherNegocioDialog
        open={escolhendoNegocio}
        onClose={() => setEscolhendoNegocio(false)}
        onEscolher={(negocioId) => {
          setEscolhendoNegocio(false);
          setNovo({ negocioId });
        }}
      />

      <OrcamentoModal
        open={!!abertoId || !!novo}
        onClose={() => {
          setNovo(null);
          setParam("id", null);
        }}
        orcamentoId={abertoId}
        negocioId={novo?.negocioId ?? null}
        onOrcamentoChange={(o) => {
          setNovo(null);
          setParam("id", o.id);
        }}
      />
    </div>
  );
}

function OrcamentoCard({ orcamento: o, onAbrir }: { orcamento: Orcamento; onAbrir: () => void }) {
  return (
    <button
      type="button"
      onClick={onAbrir}
      data-testid="orcamento-card"
      className="flex w-full flex-col gap-2 rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-colors hover:bg-muted/40"
    >
      <div className="flex w-full items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-foreground">{o.lead?.empresa || o.lead?.nome || o.titulo}</p>
          <p className="truncate text-xs text-muted-foreground">
            {o.titulo} · v{o.versao}
          </p>
        </div>
        <Badge variant={o.status === "aceito" ? "default" : o.status === "recusado" || o.status === "expirado" ? "destructive" : "outline"}>
          {ORCAMENTO_STATUS_LABEL[o.status]}
        </Badge>
      </div>
      <div className="flex w-full flex-wrap items-end justify-between gap-2">
        <p className="text-lg font-semibold tabular-nums text-foreground">
          {brl(o.total_mensal)}
          <span className="text-xs font-normal text-muted-foreground">/mês</span>
        </p>
        {o.total_mensal > 0 ? <MargemBadge margem={o.margem_estimada} /> : null}
      </div>
      <p className="text-xs text-muted-foreground">
        Criado em {dataBR(o.created_at)}
        {o.validade ? ` · válido até ${dataBR(o.validade)}` : ""}
        {o.respondido_em ? " · respondeu por e-mail" : o.enviado_em ? ` · enviado em ${dataBR(o.enviado_em)}` : ""}
      </p>
    </button>
  );
}

/** "Novo orçamento" — an orçamento belongs to exactly one negócio (and its lead). */
function EscolherNegocioDialog({
  open,
  onClose,
  onEscolher,
}: {
  open: boolean;
  onClose: () => void;
  onEscolher: (negocioId: string) => void;
}) {
  const { data: colunas, isPending, isError, error } = comercialPipeline.useBoard(undefined, { enabled: open });
  const [busca, setBusca] = useState("");
  const negocios = (colunas ?? [])
    .flatMap((c) => c.cards.map((n) => ({ n, etapa: c.stage.label })))
    .filter(({ n }) => n.status === "aberto")
    .filter(({ n }) => {
      const t = busca.trim().toLowerCase();
      if (!t) return true;
      return [n.titulo, n.lead?.nome, n.lead?.empresa].some((v) => v?.toLowerCase().includes(t));
    });

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="Novo orçamento"
      description="Para qual negócio?"
      widthClassName="sm:max-w-md"
      testId="escolher-negocio"
    >
      <Input
        aria-label="Buscar negócio"
        placeholder="Buscar lead ou empresa…"
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        className="mb-3"
      />
      {isPending && !colunas ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : isError ? (
        <p role="alert" className="text-sm text-destructive">{describeError(error, "Não foi possível carregar o funil.")}</p>
      ) : negocios.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Nenhum negócio em aberto. Crie um lead no Comercial primeiro.
        </p>
      ) : (
        <ul className="space-y-2">
          {negocios.map(({ n, etapa }) => (
            <li key={n.id}>
              <button
                type="button"
                onClick={() => onEscolher(n.id)}
                className="flex w-full items-center gap-3 rounded-lg border border-border p-3 text-left text-sm hover:bg-muted"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-foreground">{n.lead?.empresa || n.lead?.nome || n.titulo}</span>
                  <span className="text-xs text-muted-foreground">{etapa}</span>
                </span>
                {n.valor_estimado ? <span className="text-xs tabular-nums">{brl(n.valor_estimado)}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      )}
    </SheetDialog>
  );
}
