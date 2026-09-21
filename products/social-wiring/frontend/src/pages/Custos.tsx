/**
 * Custos — quanto esta organização gasta em integrações pagas.
 *
 * Duas fontes reais, agregadas no backend (`GET /api/custos`):
 *  - `llm_usage` (chat/visão/embedding/áudio) — custo em USD convertido pela
 *    última cotação PTAX armazenada; sem cotação, o cartão mostra "cotação
 *    pendente" em vez de inventar uma taxa.
 *  - `cost_ledger` (InfoSimples — certidões) — já nativo em BRL.
 *
 * D4Sign e Google Maps aparecem como cartões "não instrumentado ainda" —
 * NUNCA como custo zero, que pareceria "confirmado grátis" quando na
 * verdade é apenas "não medido" (ver `CLAUDE/backend.md`, proibição de
 * custo inventado).
 */
import { useState } from "react";
import { AlertTriangle, Wallet } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageSkeleton } from "@noctusai/lib/design-system";

import { useCustos, type CustosIntegracao, type CustosPeriodo } from "@/hooks/useCustos";

const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 2,
});

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const PERIODOS: { value: CustosPeriodo; label: string }[] = [
  { value: "este_mes", label: "Este mês" },
  { value: "ultimos_30_dias", label: "Últimos 30 dias" },
  { value: "mes_anterior", label: "Mês anterior" },
];

const NOME_LABEL: Record<string, string> = {
  llm: "LLM (IA)",
  infosimples: "InfoSimples (certidões)",
  d4sign: "D4Sign (assinaturas)",
  google_maps: "Google Maps",
};

function IntegracaoCard({ integracao }: { integracao: CustosIntegracao }) {
  const rotulo = NOME_LABEL[integracao.nome] ?? integracao.nome;
  return (
    <Card data-testid={`custos-card-${integracao.nome}`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{rotulo}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">
          {integracao.custo_brl != null ? BRL.format(integracao.custo_brl) : "—"}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          {integracao.chamadas} chamada{integracao.chamadas === 1 ? "" : "s"}
        </div>
        {integracao.fx_pendente && (
          <div className="mt-2 flex items-start gap-1 text-xs text-amber-600">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
            <span>Cotação PTAX pendente</span>
          </div>
        )}
        {integracao.observacao && !integracao.fx_pendente && (
          <div className="mt-2 text-xs text-muted-foreground">{integracao.observacao}</div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Custos() {
  const [periodo, setPeriodo] = useState<CustosPeriodo>("este_mes");
  const { data, error, showSkeleton, isRefreshing } = useCustos(periodo);

  return (
    <div className="space-y-6 p-6" data-testid="custos-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Wallet className="h-6 w-6" />
            Custos
          </h1>
          <p className="text-sm text-muted-foreground">
            Quanto esta organização gasta em integrações pagas.
            {isRefreshing && " Atualizando…"}
          </p>
        </div>
        <Select value={periodo} onValueChange={(v) => setPeriodo(v as CustosPeriodo)}>
          <SelectTrigger className="w-48" data-testid="custos-periodo-select">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIODOS.map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {showSkeleton && <PageSkeleton />}

      {!showSkeleton && error && (
        <div className="flex h-40 items-center justify-center rounded-md border border-dashed text-sm text-destructive">
          Não foi possível carregar os custos. Tente novamente em instantes.
        </div>
      )}

      {!showSkeleton && !error && data && (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total no período
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold" data-testid="custos-total">
                {BRL.format(data.total_brl)}
              </div>
              {data.fx_pendente && (
                <div className="mt-1 flex items-center gap-1 text-xs text-amber-600">
                  <AlertTriangle className="h-3 w-3" />
                  Alguns valores aguardam cotação PTAX — o total pode subir quando resolvidos.
                </div>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.integracoes.map((i) => (
              <IntegracaoCard key={i.nome} integracao={i} />
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Gasto diário</CardTitle>
            </CardHeader>
            <CardContent>
              {data.serie_diaria.length === 0 ? (
                <div className="flex h-48 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                  Nenhum custo registrado neste período.
                </div>
              ) : (
                <div className="h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.serie_diaria} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                      <XAxis dataKey="data" fontSize={11} stroke="currentColor" opacity={0.6} />
                      <YAxis
                        tickFormatter={(v: number) => BRL.format(v)}
                        fontSize={11}
                        stroke="currentColor"
                        opacity={0.6}
                        width={80}
                      />
                      <Tooltip
                        formatter={(value: number) => [BRL.format(value), "Custo"]}
                        labelStyle={{ color: "var(--foreground)" }}
                        contentStyle={{
                          background: "var(--background)",
                          border: "1px solid var(--border)",
                          borderRadius: 6,
                        }}
                      />
                      <Bar dataKey="custo_brl" fill="hsl(var(--primary, 220 90% 56%))" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Detalhamento por modelo (LLM)</CardTitle>
            </CardHeader>
            <CardContent>
              {data.llm_por_modelo.length === 0 ? (
                <div className="flex h-24 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                  Nenhuma chamada de IA neste período.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-muted-foreground">
                        <th className="py-2 pr-4 font-medium">Provider</th>
                        <th className="py-2 pr-4 font-medium">Modelo</th>
                        <th className="py-2 pr-4 font-medium text-right">Chamadas</th>
                        <th className="py-2 pr-4 font-medium text-right">Tokens</th>
                        <th className="py-2 pr-4 font-medium text-right">Custo (USD)</th>
                        <th className="py-2 font-medium text-right">Custo (BRL)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.llm_por_modelo.map((m) => (
                        <tr key={`${m.provider}-${m.model}`} className="border-b last:border-0">
                          <td className="py-2 pr-4">{m.provider}</td>
                          <td className="py-2 pr-4">{m.model}</td>
                          <td className="py-2 pr-4 text-right">{m.chamadas}</td>
                          <td className="py-2 pr-4 text-right">{m.total_tokens.toLocaleString("pt-BR")}</td>
                          <td className="py-2 pr-4 text-right">{USD.format(m.custo_usd)}</td>
                          <td className="py-2 text-right">
                            {m.custo_brl != null ? BRL.format(m.custo_brl) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
