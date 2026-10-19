import { Link } from "react-router-dom";

import type { RelImoveis } from "@/hooks/useJuliaRelatorios";
import { brl, opLabel, pct } from "./formato";

export function ImoveisTab({ data, operacao }: { data: RelImoveis; operacao: string }) {
  const op = opLabel(operacao);
  const vazio = data.tipos.length === 0 && data.top_imoveis.length === 0;
  if (vazio) {
    return (
      <p className="rounded-lg border border-dashed py-12 text-center text-sm text-muted-foreground" data-testid="rel-vazio">
        Sem dados de {op} neste mês.
      </p>
    );
  }
  return (
    <div className="space-y-8">
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Top tipo de imóveis</h2>
        <p className="text-sm text-muted-foreground">Compare a busca dos seus leads de {op} com sua prateleira de imóveis</p>
        <table className="w-full text-sm" data-testid="rel-tipos">
          <thead><tr className="border-b text-left text-muted-foreground">
            <th className="py-2">Ranking</th><th>Tipo de imóvel</th><th>Leads %</th><th>Prateleira %</th>
          </tr></thead>
          <tbody>{data.tipos.map((t, i) => (
            <tr key={t.tipo} className="border-b">
              <td className="py-2">{i + 1}º</td><td>{t.tipo}</td><td>{pct(t.pct_leads)}</td><td>{pct(t.pct_prateleira)}</td>
            </tr>))}</tbody>
        </table>
      </section>
      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Top 10 imóveis</h2>
        <p className="text-sm text-muted-foreground">Saiba quais imóveis de {op} da sua prateleira atraíram mais leads</p>
        <table className="w-full text-sm" data-testid="rel-imoveis">
          <thead><tr className="border-b text-left text-muted-foreground">
            <th className="py-2">Ranking</th><th>Imóvel</th><th>Tipo</th><th>Preço</th><th>Leads</th>
          </tr></thead>
          <tbody>{data.top_imoveis.map((m, i) => (
            <tr key={m.codigo} className="border-b">
              <td className="py-2">{i + 1}º</td>
              <td><Link className="text-primary underline" to={`/imoveis/${encodeURIComponent(m.codigo)}`}>{m.codigo}</Link></td>
              <td>{m.tipo}</td><td>{brl(m.preco)}</td><td>{m.leads}</td>
            </tr>))}</tbody>
        </table>
      </section>
    </div>
  );
}
