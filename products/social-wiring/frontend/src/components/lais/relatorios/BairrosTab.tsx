import { Link } from "react-router-dom";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { RelBairros } from "@/hooks/useLaisRelatorios";
import { brl, opLabel, pct } from "./formato";

const SELECT = "h-9 rounded-md border bg-background px-2 text-sm";

export function BairrosTab({ data, operacao, bairro, onBairro }: {
  data: RelBairros; operacao: string; bairro: string; onBairro: (b: string) => void;
}) {
  const op = opLabel(operacao);
  if (data.top_bairros.length === 0 && data.bairros_disponiveis.length === 0) {
    return (
      <p className="rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground" data-testid="rel-vazio">
        Sem dados de {op} neste mês.
      </p>
    );
  }
  const d = data.desempenho;
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Top 10 bairros</h2>
        <p className="text-sm text-muted-foreground">Os bairros mais interessantes para os seus leads de {op}</p>
        <div style={{ height: Math.max(120, data.top_bairros.length * 32) }} data-testid="rel-bairros-chart">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.top_bairros} layout="vertical" margin={{ left: 24 }}>
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="bairro" width={140} />
              <Tooltip />
              <Bar dataKey="leads" fill="hsl(var(--primary))" />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <ul className="sr-only" data-testid="rel-bairros-lista">
          {data.top_bairros.map((b) => <li key={b.bairro}>{b.bairro}: {b.leads} leads</li>)}
        </ul>
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Desempenho por bairro</h2>
        <select aria-label="Bairro" className={SELECT} value={bairro} onChange={(e) => onBairro(e.target.value)}>
          <option value="">Selecione um bairro</option>
          {data.bairros_disponiveis.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        {!d ? (
          <p className="text-sm text-muted-foreground" data-testid="rel-bairro-vazio">Selecione um bairro para ver o desempenho.</p>
        ) : (
          <div className="space-y-3 text-sm" data-testid="rel-desempenho">
            <p>A mediana de preço dos imóveis de {op} pesquisada em {d.bairro} pelos seus leads foi <strong>{brl(d.mediana_preco)}</strong>.</p>
            {d.pct_por_tipo.map((t) => (
              <p key={t.tipo}><strong>{pct(t.pct)}</strong> dos leads de {op} buscaram por {t.tipo}.</p>
            ))}
            {d.melhor_quartos != null && (
              <p>Imóveis com <strong>{d.melhor_quartos}</strong> quartos são os que fizeram mais sucesso.</p>
            )}
            <h3 className="pt-2 text-xs font-semibold uppercase text-muted-foreground">Imóveis mais buscados neste bairro</h3>
            <table className="w-full" data-testid="rel-mais-buscados">
              <thead><tr className="border-b text-left text-muted-foreground">
                <th className="py-2">Ranking</th><th>Imóvel</th><th>Tipo</th><th>Preço</th><th>Leads</th>
              </tr></thead>
              <tbody>{d.mais_buscados.map((m, i) => (
                <tr key={m.codigo} className="border-b">
                  <td className="py-2">{i + 1}º</td>
                  <td><Link className="text-primary underline" to={`/imoveis/${encodeURIComponent(m.codigo)}`}>{m.codigo}</Link></td>
                  <td>{m.tipo}</td><td>{brl(m.preco)}</td><td>{m.leads}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
