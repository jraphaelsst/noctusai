/**
 * Julia › Opt-outs (`/julia/opt-outs`): per org, the history of leads who asked not to be contacted (and of their
 * reactivation), plus the data-subject requests Julia registered for a human. Reads come from AGENTS (the opt-out is its
 * record); admins can resend a failed notice, reactivate a lead (reason required) and decide a data request.
 *
 *   ?evento=<id>       highlights an opt-out record (the in-app notice links here)
 *   ?aba=solicitacoes&solicitacao=<id>   the data requests tab, request highlighted
 *
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useSearchParams } from "react-router-dom";

import { OptOutHistorico } from "@/components/julia/optouts/OptOutHistorico";
import { SolicitacoesTitular } from "@/components/julia/optouts/SolicitacoesTitular";

const ABAS = [
  { key: "historico", label: "Histórico" },
  { key: "solicitacoes", label: "Solicitações de dados" },
] as const;

export default function JuliaOptOuts() {
  const [params, setParams] = useSearchParams();
  const aba = params.get("aba") === "solicitacoes" ? "solicitacoes" : "historico";

  function trocar(key: string) {
    const next = new URLSearchParams(params);
    if (key === "historico") next.delete("aba"); else next.set("aba", key);
    next.delete("evento");
    next.delete("solicitacao");
    setParams(next, { replace: true });
  }

  return (
    <div className="container max-w-4xl space-y-5 py-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Opt-outs</h1>
        <p className="text-sm text-muted-foreground">
          Leads que pediram para não ser contatados e solicitações de dados pessoais. Os leads são da organização: cada
          imobiliária tem seu próprio histórico.
        </p>
      </header>
      <div role="tablist" className="inline-flex rounded-md border p-0.5">
        {ABAS.map((a) => (
          <button
            key={a.key} role="tab" type="button" aria-selected={aba === a.key} data-testid={`aba-${a.key}`}
            className={`rounded px-3 py-1 text-sm ${aba === a.key ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            onClick={() => trocar(a.key)}
          >
            {a.label}
          </button>
        ))}
      </div>
      {aba === "historico"
        ? <OptOutHistorico eventoDestaque={params.get("evento")} />
        : <SolicitacoesTitular destaque={params.get("solicitacao")} />}
    </div>
  );
}
