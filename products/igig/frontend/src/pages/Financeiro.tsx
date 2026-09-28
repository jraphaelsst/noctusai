/**
 * Financeiro — Módulo 6: resumo + fechamento do mês, DRE, excedentes,
 * faturas e régua de cobrança; "Relatório" (comercial / financeiro, PDF/CSV).
 *
 * The DRE is the screen the agency makes decisions on, so two things are
 * deliberate:
 *   - `alertas` render as a visible row. When hours could not be costed the
 *     margin is OVERSTATED, and a number that looks precise while being
 *     optimistic is the worst possible output here.
 *   - negative margin is coloured, because "we lost money on this account" is
 *     the single most actionable thing this table can say.
 */
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileBarChart2,
  FilePlus2,
  Mail,
  MailCheck,
  Plus,
  XCircle,
} from "lucide-react";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { FechamentoMes } from "@/components/financeiro/FechamentoMes";
import { RelatorioSheet } from "@/components/financeiro/RelatorioSheet";

import { useClientes } from "@/hooks/useClientes";
import { useContratos } from "@/hooks/useContratos";
import {
  useAdicionarItem,
  useCancelarFatura,
  useCriarFatura,
  useDRE,
  useEnviarFatura,
  useExcedentes,
  useFaturaItens,
  useFaturas,
  useInadimplentes,
  useMarcarFaturaEnviada,
  useMarcarPaga,
  type Fatura,
  type StatusFatura,
  type TipoItem,
} from "@/hooks/useFinanceiro";
import { describeError } from "@/lib/errors";
import { dataBR, parseValorBR, pct } from "@/lib/format";
import { useIsOrgAdmin } from "@/lib/useIsOrgAdmin";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

const STATUS_VARIANT: Record<StatusFatura, BadgeVariant> = {
  aberta: "muted",
  enviada: "outline",
  paga: "default",
  vencida: "destructive",
  cancelada: "outline",
};

/** Current month as 'YYYY-MM'. */
function competenciaAtual(): string {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
}

export default function Financeiro() {
  const [competencia, setCompetencia] = useState(competenciaAtual);
  const { linhas, loading: carregandoDRE, isError: erroDRE } = useDRE(competencia);
  const { excedentes, loading: carregandoExc, isError: erroExc } = useExcedentes(competencia);
  const { faturas, loading: carregandoFat, isError: erroFat } = useFaturas();
  const { atrasadas, isError: erroAtrasadas, error: erroAtrasadasDetalhe } = useInadimplentes();
  const marcarPaga = useMarcarPaga();
  const cancelarFatura = useCancelarFatura();
  const enviarFatura = useEnviarFatura();
  const marcarFaturaEnviada = useMarcarFaturaEnviada();
  const isAdmin = useIsOrgAdmin();
  const { clientes } = useClientes();
  const nomeCliente = (id: string) => clientes.find((c) => c.id === id)?.nome ?? null;
  /** Which invoice has its lines expanded, if any. */
  const [faturaAberta, setFaturaAberta] = useState<string | null>(null);
  const [relatorioAberto, setRelatorioAberto] = useState(false);
  const [cancelandoFaturaId, setCancelandoFaturaId] = useState<string | null>(null);
  const [marcandoPagaId, setMarcandoPagaId] = useState<string | null>(null);
  const [enviandoFaturaId, setEnviandoFaturaId] = useState<string | null>(null);
  const [marcandoEnviadaId, setMarcandoEnviadaId] = useState<string | null>(null);

  return (
    <div className="min-w-0 max-w-full space-y-6 p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-foreground sm:text-2xl">Financeiro</h1>
          <p className="text-sm text-muted-foreground">
            Margem por conta, excedentes e cobrança.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-muted-foreground">
            Competência
            <input
              type="month"
              aria-label="Competência"
              value={competencia}
              onChange={(e) => setCompetencia(e.target.value)}
              className="ml-2 h-10 rounded border border-border bg-card px-2 text-sm text-foreground sm:h-9"
            />
          </label>
          <Button variant="outline" className="max-sm:h-10" onClick={() => setRelatorioAberto(true)} data-testid="abrir-relatorio">
            <FileBarChart2 className="mr-1 h-4 w-4" /> Relatório
          </Button>
        </div>
      </header>

      <FechamentoMes competencia={competencia} />
      <RelatorioSheet open={relatorioAberto} onClose={() => setRelatorioAberto(false)} />

      {erroAtrasadas ? (
        <p role="alert" className="rounded-lg border border-destructive/40 bg-card p-4 text-sm text-destructive">
          {describeError(erroAtrasadasDetalhe, "Não foi possível carregar as faturas em atraso.")}
        </p>
      ) : (
        atrasadas.length > 0 && (
          <div className="rounded-lg border border-destructive/40 bg-card p-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-destructive">
              <AlertTriangle className="h-4 w-4" />
              {atrasadas.length} fatura(s) em atraso
            </h2>
            <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
              {atrasadas.slice(0, 5).map((f) => (
                <li key={f.fatura_id}>
                  {nomeCliente(f.cliente_id) && (
                    <span className="font-medium text-foreground">{nomeCliente(f.cliente_id)} · </span>
                  )}
                  {f.competencia} · {BRL.format(f.valor_total)} ·{" "}
                  <span className="text-destructive">{f.dias_atraso} dias</span>
                </li>
              ))}
            </ul>
          </div>
        )
      )}

      {/* ── DRE ────────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-1 text-sm font-semibold text-foreground">DRE por conta — {competencia}</h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Receita da competência selecionada; custo real é sempre o histórico completo.
        </p>
        {erroDRE ? (
          <p role="alert" className="text-sm text-destructive">Não foi possível carregar o DRE.</p>
        ) : carregandoDRE ? (
          <Skeleton className="h-24 w-full" />
        ) : linhas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum cliente ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2">Cliente</th>
                  <th className="py-2 text-right">Receita</th>
                  <th className="py-2 text-right">Custo real</th>
                  <th className="py-2 text-right">Margem</th>
                  <th className="py-2 text-right">%</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {linhas.map((l) => (
                  <Fragment key={l.cliente_id}>
                    <tr>
                      <td className="py-2 text-foreground">{l.cliente_nome}</td>
                      <td className="py-2 text-right text-foreground">{BRL.format(l.receita)}</td>
                      <td className="py-2 text-right text-foreground">{BRL.format(l.custo)}</td>
                      <td
                        className={`py-2 text-right ${
                          l.margem < 0 ? "text-destructive" : "text-foreground"
                        }`}
                      >
                        {BRL.format(l.margem)}
                      </td>
                      <td
                        className={`py-2 text-right ${
                          l.margem < 0 ? "text-destructive" : "text-foreground"
                        }`}
                      >
                        {pct(l.margem_percentual)}
                      </td>
                    </tr>
                    {l.alertas.length > 0 && (
                      <tr>
                        <td colSpan={5} className="pb-2 text-xs text-destructive">
                          <AlertTriangle className="mr-1 inline h-3 w-3" />
                          {l.alertas.join(" · ")}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Excedentes ─────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-1 text-sm font-semibold text-foreground">
          Itens excedentes — {competencia}
        </h2>
        <p className="mb-3 text-xs text-muted-foreground">
          Cobrados na fatura do mês seguinte. As peças do plano recorrente nunca
          contam como excedente, mesmo em meses com mais publicações previstas
          no calendário — mas elas ocupam a capacidade do pacote. Peças avulsas
          (fora do plano) só geram cobrança extra pela parte do pacote que o
          plano ainda não usou nesta competência.
        </p>
        {erroExc ? (
          <p role="alert" className="text-sm text-destructive">Não foi possível carregar os excedentes.</p>
        ) : carregandoExc ? (
          <Skeleton className="h-20 w-full" />
        ) : excedentes.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum contrato ativo com pacote definido nesta competência.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {excedentes.map((e) => (
              <li key={e.contrato_id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                  {e.cliente_nome}
                </span>
                <span className="text-xs text-muted-foreground">
                  {e.entregues} / {e.contratados} entregues
                </span>
                {e.excedentes > 0 ? (
                  <>
                    <Badge variant="destructive">+{e.excedentes}</Badge>
                    <span className="text-sm text-foreground">{BRL.format(e.valor_total)}</span>
                    <span className="text-xs text-muted-foreground">
                      → {e.competencia_cobranca}
                    </span>
                  </>
                ) : (
                  <Badge variant="muted">dentro do pacote</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Faturas ────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Faturas</h2>
        <NovaFatura competenciaPadrao={competencia} />
        {erroFat ? (
          <p role="alert" className="text-sm text-destructive">Não foi possível carregar as faturas.</p>
        ) : carregandoFat ? (
          <Skeleton className="h-20 w-full" />
        ) : faturas.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhuma fatura emitida.</p>
        ) : (
          <ul className="divide-y divide-border">
            {faturas.map((f) => (
              <LinhaFatura
                key={f.id}
                fatura={f}
                clienteNome={nomeCliente(f.cliente_id)}
                aberta={faturaAberta === f.id}
                isAdmin={isAdmin}
                onAlternar={() => setFaturaAberta(faturaAberta === f.id ? null : f.id)}
                onPedirMarcarPaga={() => setMarcandoPagaId(f.id)}
                marcandoPaga={marcarPaga.isPending}
                onPedirCancelamento={() => setCancelandoFaturaId(f.id)}
                onPedirEnvio={() => setEnviandoFaturaId(f.id)}
                onPedirMarcarEnviada={() => setMarcandoEnviadaId(f.id)}
              />
            ))}
          </ul>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          Baixa manual: o webhook do gateway (Asaas/Iugu) e a emissão de NFS-e
          dependem de credenciais e homologação ainda não configuradas.
        </p>
      </section>

      <ConfirmDialog
        open={marcandoPagaId !== null}
        title="Marcar fatura como paga"
        description={<p>Marcar esta fatura como paga? Registra a data de agora; não há como desfazer pela tela.</p>}
        confirmLabel={marcarPaga.isPending ? "Marcando…" : "Marcar paga"}
        destructive={false}
        busy={marcarPaga.isPending}
        onCancel={() => setMarcandoPagaId(null)}
        onConfirm={() => {
          if (!marcandoPagaId) return;
          marcarPaga.mutate(marcandoPagaId, {
            onSuccess: () => {
              setMarcandoPagaId(null);
              toast.success("Fatura marcada como paga.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível marcar como paga.")),
          });
        }}
      />

      <ConfirmDialog
        open={cancelandoFaturaId !== null}
        title="Cancelar fatura"
        description={<p>Cancelar esta fatura? Uma fatura cancelada não pode ser reaberta nem marcada como paga.</p>}
        confirmLabel={cancelarFatura.isPending ? "Cancelando…" : "Cancelar fatura"}
        busy={cancelarFatura.isPending}
        onCancel={() => setCancelandoFaturaId(null)}
        onConfirm={() => {
          if (!cancelandoFaturaId) return;
          cancelarFatura.mutate(cancelandoFaturaId, {
            onSuccess: () => {
              setCancelandoFaturaId(null);
              toast.success("Fatura cancelada.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível cancelar a fatura.")),
          });
        }}
      />

      <ConfirmDialog
        open={enviandoFaturaId !== null}
        title="Enviar fatura"
        description={<p>Enviar esta fatura por e-mail para o cliente, com o PDF em anexo?</p>}
        confirmLabel={enviarFatura.isPending ? "Enviando…" : "Enviar fatura"}
        destructive={false}
        busy={enviarFatura.isPending}
        onCancel={() => setEnviandoFaturaId(null)}
        onConfirm={() => {
          if (!enviandoFaturaId) return;
          enviarFatura.mutate(enviandoFaturaId, {
            onSuccess: () => {
              setEnviandoFaturaId(null);
              toast.success("Fatura enviada por e-mail.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível enviar a fatura.")),
          });
        }}
      />

      <ConfirmDialog
        open={marcandoEnviadaId !== null}
        title="Marcar fatura como enviada"
        description={
          <p>
            Marcar esta fatura como enviada sem enviar nenhum e-mail? Use quando a fatura já foi
            entregue ao cliente por outro meio.
          </p>
        }
        confirmLabel={marcarFaturaEnviada.isPending ? "Marcando…" : "Marcar como enviada"}
        destructive={false}
        busy={marcarFaturaEnviada.isPending}
        onCancel={() => setMarcandoEnviadaId(null)}
        onConfirm={() => {
          if (!marcandoEnviadaId) return;
          marcarFaturaEnviada.mutate(marcandoEnviadaId, {
            onSuccess: () => {
              setMarcandoEnviadaId(null);
              toast.success("Fatura marcada como enviada.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível marcar como enviada.")),
          });
        }}
      />
    </div>
  );
}

/**
 * One invoice row, expandable to its lines.
 *
 * `GET /faturas/{id}/itens` had no consumer, so an invoice showed a total with
 * no way to see what produced it — and the excedentes flow exists precisely to
 * add lines a client will ask about. Fetched lazily (`enabled` on the id) so
 * opening the page does not issue one request per invoice.
 */
function LinhaFatura({
  fatura,
  clienteNome,
  aberta,
  isAdmin,
  onAlternar,
  onPedirMarcarPaga,
  marcandoPaga,
  onPedirCancelamento,
  onPedirEnvio,
  onPedirMarcarEnviada,
}: {
  fatura: Fatura;
  clienteNome: string | null;
  aberta: boolean;
  isAdmin: boolean;
  onAlternar: () => void;
  onPedirMarcarPaga: () => void;
  marcandoPaga: boolean;
  onPedirCancelamento: () => void;
  onPedirEnvio: () => void;
  onPedirMarcarEnviada: () => void;
}) {
  const { itens, loading, isError: erroItens, error: erroItensDetalhe } = useFaturaItens(
    aberta ? fatura.id : undefined,
  );

  return (
    <li className="py-2">
      <div className="flex flex-wrap items-center gap-3">
        <Badge variant={STATUS_VARIANT[fatura.status]}>{fatura.status}</Badge>
        {fatura.status === "vencida" && fatura.enviada_em && (
          <span className="text-xs text-muted-foreground">
            · enviada em {dataBR(fatura.enviada_em)}
          </span>
        )}
        {clienteNome && (
          <span className="min-w-0 max-w-[12rem] truncate text-sm font-medium text-foreground">
            {clienteNome}
          </span>
        )}
        <span className="text-sm text-foreground">{fatura.competencia}</span>
        <span className="min-w-0 flex-1 text-sm text-foreground">
          {BRL.format(fatura.valor_total)}
        </span>
        {fatura.vencimento && (
          <span className="text-xs text-muted-foreground">vence {dataBR(fatura.vencimento)}</span>
        )}

        <Button
          size="sm"
          variant="ghost"
          onClick={onAlternar}
          aria-expanded={aberta}
          aria-label={`${aberta ? "Ocultar" : "Ver"} itens da fatura ${fatura.competencia}`}
        >
          {aberta ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          Itens
        </Button>

        {/* Ações são admin-only no servidor — a tela só oferece o que o
            servidor permitiria, em vez de deixar o membro tentar e receber
            um 403. Enviar/marcar-enviada só fazem sentido ANTES da fatura
            estar paga/cancelada — depois disso o "envio" já não é relevante. */}
        {isAdmin && fatura.status !== "paga" && fatura.status !== "cancelada" && (
          <>
            <Button size="sm" variant="outline" onClick={onPedirEnvio}>
              <Mail className="mr-2 h-3 w-3" />
              Enviar fatura
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Marcar fatura ${fatura.competencia} como enviada`}
              onClick={onPedirMarcarEnviada}
            >
              <MailCheck className="h-4 w-4" />
            </Button>
            <Button size="sm" variant="outline" disabled={marcandoPaga} onClick={onPedirMarcarPaga}>
              <CheckCircle2 className="mr-2 h-3 w-3" />
              Marcar paga
            </Button>
            <Button
              size="sm"
              variant="ghost"
              aria-label={`Cancelar fatura ${fatura.competencia}`}
              onClick={onPedirCancelamento}
            >
              <XCircle className="h-4 w-4 text-destructive" />
            </Button>
          </>
        )}
      </div>

      {aberta && (
        <div className="mt-2 rounded-md border border-border bg-background p-3">
          {erroItens ? (
            <p role="alert" className="text-xs text-destructive">
              {describeError(erroItensDetalhe, "Não foi possível carregar os itens desta fatura.")}
            </p>
          ) : loading ? (
            <Skeleton className="h-12 w-full" />
          ) : itens.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Nenhum item lançado nesta fatura.
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="pb-1 font-medium">Descrição</th>
                  <th className="pb-1 font-medium">Tipo</th>
                  <th className="pb-1 text-right font-medium">Qtd</th>
                  <th className="pb-1 text-right font-medium">Valor un.</th>
                  <th className="pb-1 text-right font-medium">Total</th>
                </tr>
              </thead>
              <tbody className="text-foreground">
                {itens.map((i) => {
                  const bruto = i.quantidade * i.valor_unit;
                  const contribuicao = i.tipo === "desconto" ? -bruto : bruto;
                  return (
                    <tr key={i.id} className="border-t border-border">
                      <td className="py-1">{i.descricao}</td>
                      <td className="py-1 text-muted-foreground">{i.tipo}</td>
                      <td className="py-1 text-right">{i.quantidade}</td>
                      <td className="py-1 text-right">{BRL.format(i.valor_unit)}</td>
                      <td className={`py-1 text-right ${contribuicao < 0 ? "text-destructive" : ""}`}>
                        {contribuicao < 0 ? "− " : ""}
                        {BRL.format(Math.abs(contribuicao))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {/* Lines only go on an invoice that can still change. */}
          {(fatura.status === "aberta" || fatura.status === "enviada" || fatura.status === "vencida") && (
            <AdicionarItem faturaId={fatura.id} />
          )}
        </div>
      )}
    </li>
  );
}

const TIPOS_ITEM: { valor: TipoItem; rotulo: string }[] = [
  { valor: "mensalidade", rotulo: "Mensalidade" },
  { valor: "excedente", rotulo: "Excedente" },
  { valor: "avulso", rotulo: "Avulso" },
  { valor: "desconto", rotulo: "Desconto" },
];

const CAMPO = "h-11 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground";

/**
 * Open an invoice by hand (`POST /api/financeiro/faturas` had no consumer).
 * One invoice per contrato × competência is enforced server-side (409) — the
 * message comes back verbatim. Picking a contrato is OPTIONAL (an avulsa
 * charge has none), but when picked it shares the SAME idempotency guard
 * `gerar_competencia` relies on — the double-bill finding #4 exists to close.
 */
function NovaFatura({ competenciaPadrao }: { competenciaPadrao: string }) {
  const { clientes, loading } = useClientes();
  const criar = useCriarFatura();
  const [aberto, setAberto] = useState(false);
  const [clienteId, setClienteId] = useState("");
  const [contratoId, setContratoId] = useState("");
  const [competencia, setCompetencia] = useState(competenciaPadrao);
  const [vencimento, setVencimento] = useState("");
  const { contratos } = useContratos(clienteId || null);
  const contratosAtivos = contratos.filter((c) => c.status === "ativo");

  if (!aberto) {
    return (
      <Button
        size="sm"
        variant="outline"
        className="mb-3 min-h-10"
        onClick={() => {
          // Re-sync to the header's current competência EACH time the form
          // is (re)opened — it previously captured `competenciaPadrao` once,
          // at the page's first render, and never again (finding #24,
          // 2026-09 audit).
          setCompetencia(competenciaPadrao);
          setAberto(true);
        }}
      >
        <FilePlus2 className="mr-2 h-4 w-4" />
        Nova fatura
      </Button>
    );
  }

  function submeter(e: React.FormEvent) {
    e.preventDefault();
    if (!clienteId || !competencia) return;
    criar.mutate(
      {
        cliente_id: clienteId, competencia,
        ...(contratoId ? { contrato_id: contratoId } : {}),
        ...(vencimento ? { vencimento } : {}),
      },
      {
        onSuccess: () => {
          toast.success("Fatura aberta — adicione os itens");
          setClienteId("");
          setContratoId("");
          setVencimento("");
          setAberto(false);
        },
        onError: (erro) => toast.error(describeError(erro, "Não foi possível abrir a fatura.")),
      },
    );
  }

  return (
    <form
      onSubmit={submeter}
      className="mb-4 grid grid-cols-1 gap-3 rounded-md border border-border bg-background p-3 sm:grid-cols-[2fr_2fr_1fr_1fr_auto_auto] sm:items-end"
    >
      <label className="text-xs text-muted-foreground">
        Cliente
        <select
          className={`mt-1 ${CAMPO}`}
          value={clienteId}
          onChange={(e) => {
            setClienteId(e.target.value);
            setContratoId("");
          }}
          disabled={loading}
        >
          <option value="">{loading ? "Carregando…" : "Selecione…"}</option>
          {clientes.map((c) => (
            <option key={c.id} value={c.id}>{c.nome}</option>
          ))}
        </select>
      </label>
      <label className="text-xs text-muted-foreground">
        Contrato (opcional)
        <select
          className={`mt-1 ${CAMPO}`}
          value={contratoId}
          onChange={(e) => setContratoId(e.target.value)}
          disabled={!clienteId || contratosAtivos.length === 0}
        >
          <option value="">Avulsa — sem contrato</option>
          {contratosAtivos.map((c) => (
            <option key={c.id} value={c.id}>
              {c.numero ?? c.id.slice(0, 8)} — {BRL.format(c.valor_mensal ?? 0)}/mês
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-muted-foreground">
        Competência
        <Input
          type="month"
          className="mt-1 h-11"
          value={competencia}
          onChange={(e) => setCompetencia(e.target.value)}
        />
      </label>
      <label className="text-xs text-muted-foreground">
        Vencimento
        <Input
          type="date"
          className="mt-1 h-11"
          value={vencimento}
          onChange={(e) => setVencimento(e.target.value)}
        />
      </label>
      <Button type="submit" className="min-h-11" disabled={!clienteId || !competencia || criar.isPending}>
        {criar.isPending ? "Abrindo…" : "Abrir fatura"}
      </Button>
      <Button type="button" variant="ghost" className="min-h-11" onClick={() => setAberto(false)}>
        Cancelar
      </Button>
    </form>
  );
}

/** Add a line to an invoice; the server returns the invoice with its new total. */
function AdicionarItem({ faturaId }: { faturaId: string }) {
  const adicionar = useAdicionarItem();
  const [descricao, setDescricao] = useState("");
  const [tipo, setTipo] = useState<TipoItem>("avulso");
  const [quantidade, setQuantidade] = useState("1");
  const [valor, setValor] = useState("");
  const [erroValor, setErroValor] = useState<string | null>(null);

  function submeter(e: React.FormEvent) {
    e.preventDefault();
    const d = descricao.trim();
    if (!d) return;
    // pt-BR ("1.500,00") OR plain-decimal ("1500.00") — never silently 0 on
    // an unparseable value (finding #5, 2026-09 audit).
    const valorNumerico = parseValorBR(valor);
    if (valorNumerico === null || valorNumerico < 0) {
      setErroValor("Valor inválido. Use, por exemplo, 1500,00 ou 1.500,00.");
      return;
    }
    setErroValor(null);
    adicionar.mutate(
      {
        faturaId,
        descricao: d,
        tipo,
        quantidade: Math.max(1, Number(quantidade) || 1),
        valor_unit: valorNumerico,
      },
      {
        onSuccess: (fatura) => {
          toast.success(`Item adicionado — total ${BRL.format(fatura.valor_total)}`);
          setDescricao("");
          setQuantidade("1");
          setValor("");
        },
        onError: (erro) => toast.error(describeError(erro, "Não foi possível adicionar o item.")),
      },
    );
  }

  return (
    <form
      onSubmit={submeter}
      className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-3 sm:grid-cols-[2fr_1fr_5rem_7rem_auto] sm:items-end"
      aria-label="Adicionar item à fatura"
    >
      <label className="col-span-2 text-xs text-muted-foreground sm:col-span-1">
        Descrição
        <Input
          className="mt-1 h-11"
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Post extra — outubro"
          maxLength={200}
        />
      </label>
      <label className="col-span-2 text-xs text-muted-foreground sm:col-span-1">
        Tipo
        <select className={`mt-1 ${CAMPO}`} value={tipo} onChange={(e) => setTipo(e.target.value as TipoItem)}>
          {TIPOS_ITEM.map((t) => (
            <option key={t.valor} value={t.valor}>{t.rotulo}</option>
          ))}
        </select>
      </label>
      <label className="text-xs text-muted-foreground">
        Qtd
        <Input
          type="number"
          min={1}
          className="mt-1 h-11"
          value={quantidade}
          onChange={(e) => setQuantidade(e.target.value)}
        />
      </label>
      <label className="text-xs text-muted-foreground">
        Valor un. (R$)
        <Input
          inputMode="decimal"
          className="mt-1 h-11"
          value={valor}
          onChange={(e) => {
            setValor(e.target.value);
            setErroValor(null);
          }}
          placeholder="0,00"
        />
      </label>
      <Button
        type="submit"
        size="sm"
        className="col-span-2 min-h-11 sm:col-span-1"
        disabled={!descricao.trim() || adicionar.isPending}
      >
        <Plus className="mr-1 h-4 w-4" />
        {adicionar.isPending ? "Adicionando…" : "Adicionar item"}
      </Button>
      {erroValor && (
        <p role="alert" className="col-span-2 text-xs text-destructive sm:col-span-5">
          {erroValor}
        </p>
      )}
      {tipo === "desconto" && !erroValor && (
        <p className="col-span-2 text-xs text-muted-foreground sm:col-span-5">
          Este valor será SUBTRAÍDO do total da fatura.
        </p>
      )}
    </form>
  );
}
