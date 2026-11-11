/** The summary tab: model verdict vs the owner's label, as counts (agreement %, confusion matrix) per prompt_version/model. */
import type { UseQueryResult } from "@tanstack/react-query";

import { ROTULOS, type GrupoConcordancia, type Rotulo } from "./hooks";

const NOME_ROTULO: Record<Rotulo, string> = { agendamento: "Agendamento", nao_agendamento: "Não é agendamento", nao_sei: "Não sei" };
const NOME_VEREDITO = { agendamento: "Modelo: agendamento", outro: "Modelo: outro" } as const;

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1).replace(".", ",")}%`);

function Grupo({ g }: { g: GrupoConcordancia }) {
  return (
    <section className="space-y-2 rounded-lg border border-border bg-card p-4" data-testid="resumo-grupo">
      <h3 className="text-sm font-medium text-foreground">{g.prompt_version || "(sem versão)"} · {g.modelo || "(sem modelo)"}</h3>
      <p className="text-sm text-foreground" data-testid="resumo-concordancia">
        Concordância: <strong>{pct(g.concordancia)}</strong> ({g.concordam} de {g.decididos} decididas; {g.nao_sei} “não sei” fora da conta; {g.total} no total)
      </p>
      <table className="text-sm">
        <thead>
          <tr><th className="pr-4 text-left font-normal text-muted-foreground" />{ROTULOS.map((r) => <th key={r} className="px-3 text-right font-normal text-muted-foreground">{NOME_ROTULO[r]}</th>)}</tr>
        </thead>
        <tbody>
          {(["agendamento", "outro"] as const).map((v) => (
            <tr key={v}>
              <th scope="row" className="pr-4 text-left font-normal text-muted-foreground">{NOME_VEREDITO[v]}</th>
              {ROTULOS.map((r) => <td key={r} className="px-3 text-right tabular-nums">{g.matriz[v][r]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function Resumo({ query }: { query: UseQueryResult<{ grupos: GrupoConcordancia[] }, Error> }) {
  if (!query.data && query.isPending) {
    return <p className="text-sm text-muted-foreground" data-testid="resumo-carregando">Carregando o resumo…</p>;
  }
  if (query.isError && !query.data) {
    return (
      <div className="space-y-2" role="alert" data-testid="resumo-erro">
        <p className="text-sm text-destructive">Não foi possível carregar o resumo: {query.error.message || "erro desconhecido"}</p>
        <button type="button" className="text-sm underline" onClick={() => void query.refetch()}>Tentar de novo</button>
      </div>
    );
  }
  const grupos = query.data?.grupos ?? [];
  if (grupos.length === 0) {
    return <p className="text-sm text-muted-foreground" data-testid="resumo-vazio">Ainda não há rótulos. Rotule algumas mensagens para ver a concordância.</p>;
  }
  return <div className="space-y-4">{grupos.map((g) => <Grupo key={`${g.prompt_version}|${g.modelo}`} g={g} />)}</div>;
}
