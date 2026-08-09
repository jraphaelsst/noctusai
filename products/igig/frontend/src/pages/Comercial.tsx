/**
 * Comercial — Módulo 1: leads, calculadora de escopo, orçamentos e contratos.
 *
 * The calculator is the delicate part. Its `alertas` are rendered ABOVE the
 * price, not below it: with no custo/hora data the suggestion is R$0, and a
 * user who quotes that number loses money on the job. A warning under the
 * headline figure would be read after the decision, not before it.
 *
 * The dry-run flag on a generated contract is shown for the same reason — an
 * operator must not believe a contract reached the client when no signing
 * vendor was contacted.
 */
import { useState } from "react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { AlertTriangle, Calculator, FileSignature, Plus, UserPlus } from "lucide-react";

import { useClientes } from "@/hooks/useClientes";
import {
  FORMATOS_ESCOPO,
  useConverterLead,
  useCriarOrcamento,
  useDefinirPrecoFinal,
  useEstimar,
  useGerarContrato,
  useLeads,
  useOrcamentos,
  type FormatoEscopo,
  type ItemEscopo,
} from "@/hooks/useComercial";

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export default function Comercial() {
  const { leads, loading: carregandoLeads } = useLeads();
  const { orcamentos } = useOrcamentos();
  const { clientes } = useClientes();
  const converter = useConverterLead();
  const estimar = useEstimar();
  const criarOrcamento = useCriarOrcamento();
  const definirPreco = useDefinirPrecoFinal();
  const gerarContrato = useGerarContrato();

  const [itens, setItens] = useState<ItemEscopo[]>([{ formato: "feed", quantidade: 10 }]);
  const [margem, setMargem] = useState(50);
  const [titulo, setTitulo] = useState("Social media mensal");
  const [contratoCliente, setContratoCliente] = useState("");
  const [valorMensal, setValorMensal] = useState(5000);

  const estimativa = estimar.data ?? null;

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-foreground">Comercial</h1>
        <p className="text-sm text-muted-foreground">
          Leads, calculadora de escopo, orçamentos e contratos.
        </p>
      </header>

      {/* ── Leads ──────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 text-sm font-semibold text-foreground">Leads</h2>
        {carregandoLeads ? (
          <Skeleton className="h-20 w-full" />
        ) : leads.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum lead ainda. O formulário público publica em
            <code className="mx-1">/api/comercial/leads/publico</code>.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {leads.map((lead) => (
              <li key={lead.id} className="flex flex-wrap items-center gap-3 py-2">
                <Badge variant={lead.status === "convertido" ? "default" : "muted"}>
                  {lead.status}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">
                  {lead.empresa || lead.nome}
                  {lead.nicho && (
                    <span className="ml-2 text-xs text-muted-foreground">{lead.nicho}</span>
                  )}
                </span>
                {lead.orcamento_disponivel != null && (
                  <span className="text-xs text-muted-foreground">
                    {BRL.format(lead.orcamento_disponivel)}
                  </span>
                )}
                {!lead.cliente_id && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={converter.isPending}
                    onClick={() => converter.mutate(lead.id)}
                  >
                    <UserPlus className="mr-2 h-3 w-3" />
                    Converter
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Calculadora ────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Calculator className="h-4 w-4" />
          Calculadora de Escopo
        </h2>

        <div className="space-y-2">
          {itens.map((item, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2">
              <select
                aria-label="Formato"
                value={item.formato}
                onChange={(e) =>
                  setItens(itens.map((it, idx) =>
                    idx === i ? { ...it, formato: e.target.value as FormatoEscopo } : it))
                }
                className="h-10 rounded-md border border-border bg-background px-2 text-sm text-foreground"
              >
                {FORMATOS_ESCOPO.map((f) => (
                  <option key={f} value={f}>{f}</option>
                ))}
              </select>
              <Input
                type="number"
                min={1}
                aria-label="Quantidade"
                value={item.quantidade}
                onChange={(e) =>
                  setItens(itens.map((it, idx) =>
                    idx === i ? { ...it, quantidade: Number(e.target.value) } : it))
                }
                className="w-24"
              />
              <Button
                variant="ghost"
                size="sm"
                aria-label="Remover item"
                onClick={() => setItens(itens.filter((_, idx) => idx !== i))}
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setItens([...itens, { formato: "feed", quantidade: 1 }])}
          >
            <Plus className="mr-2 h-3 w-3" />
            Item
          </Button>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-xs text-muted-foreground">
            Margem alvo (%)
            <Input
              type="number"
              min={0}
              max={99}
              value={margem}
              onChange={(e) => setMargem(Number(e.target.value))}
              className="mt-1 w-24"
            />
          </label>
          <Button
            disabled={itens.length === 0 || estimar.isPending}
            onClick={() => estimar.mutate({ itens, margem_alvo: margem })}
          >
            Calcular
          </Button>
        </div>

        {estimativa && (
          <div className="mt-4 rounded border border-border p-3">
            {/* ABOVE the price, deliberately — a warning read after the number
                is read after the decision. */}
            {estimativa.alertas.length > 0 && (
              <p className="mb-2 flex items-start gap-1 text-xs text-destructive">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                {estimativa.alertas.join(" · ")}
              </p>
            )}
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
              <div><dt className="text-xs text-muted-foreground">Horas</dt>
                <dd className="text-foreground">{estimativa.horas}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Custo/hora médio</dt>
                <dd className="text-foreground">{BRL.format(estimativa.custo_hora_medio)}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Custo</dt>
                <dd className="text-foreground">{BRL.format(estimativa.custo)}</dd></div>
              <div><dt className="text-xs text-muted-foreground">Preço mínimo</dt>
                <dd className="font-semibold text-foreground">
                  {BRL.format(estimativa.preco_sugerido)}
                </dd></div>
            </dl>

            <div className="mt-3 flex flex-wrap items-end gap-2">
              <Input
                aria-label="Título do orçamento"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                className="min-w-[200px] flex-1"
              />
              <Button
                disabled={criarOrcamento.isPending}
                onClick={() => criarOrcamento.mutate({ titulo, itens, margem_alvo: margem })}
              >
                Salvar orçamento
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* ── Orçamentos ─────────────────────────────────────────────── */}
      {orcamentos.length > 0 && (
        <section className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-semibold text-foreground">Orçamentos</h2>
          <ul className="divide-y divide-border">
            {orcamentos.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm text-foreground">{o.titulo}</span>
                <span className="text-xs text-muted-foreground">
                  sugerido {BRL.format(o.preco_sugerido)}
                </span>
                <Input
                  type="number"
                  aria-label={`Preço final de ${o.titulo}`}
                  defaultValue={o.preco_final ?? o.preco_sugerido}
                  onBlur={(e) =>
                    definirPreco.mutate({ id: o.id, preco_final: Number(e.target.value) })
                  }
                  className="w-32"
                />
                {o.preco_final != null && o.preco_final < o.preco_sugerido && (
                  <Badge variant="destructive">abaixo do mínimo</Badge>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Contrato ───────────────────────────────────────────────── */}
      <section className="rounded-lg border border-border bg-card p-4">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
          <FileSignature className="h-4 w-4" />
          Gerar contrato
        </h2>
        <div className="flex flex-wrap items-end gap-2">
          <select
            aria-label="Cliente do contrato"
            value={contratoCliente}
            onChange={(e) => setContratoCliente(e.target.value)}
            className="h-10 rounded-md border border-border bg-background px-2 text-sm text-foreground"
          >
            <option value="">Cliente…</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>
          <label className="text-xs text-muted-foreground">
            Valor mensal
            <Input
              type="number"
              value={valorMensal}
              onChange={(e) => setValorMensal(Number(e.target.value))}
              className="mt-1 w-32"
            />
          </label>
          <Button
            disabled={!contratoCliente || gerarContrato.isPending}
            onClick={() =>
              gerarContrato.mutate({ cliente_id: contratoCliente, valor_mensal: valorMensal })
            }
          >
            Gerar PDF e enviar
          </Button>
        </div>

        {gerarContrato.data && (
          <div className="mt-3 rounded border border-border p-3 text-sm">
            {gerarContrato.data.dry_run && (
              <p className="mb-2 flex items-start gap-1 text-xs text-destructive">
                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                Simulação: nenhum provedor de assinatura foi contatado. Configure
                as credenciais antes de enviar ao cliente.
              </p>
            )}
            <p className="text-foreground">
              Contrato gerado · <code className="text-xs">{gerarContrato.data.documento_key}</code>
            </p>
            <p className="text-xs text-muted-foreground">
              Link: {gerarContrato.data.link_assinatura}
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
