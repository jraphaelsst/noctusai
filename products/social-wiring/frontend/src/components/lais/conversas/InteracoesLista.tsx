/** Interações timeline (Cliente column + history page): tipo, "Iniciada em …", chips, slots, resumo, intent flags. */
import { CreditoStatusChip } from "@/components/lais/credito/StatusChip";
import type { Interacao } from "@/hooks/useLaisConversas";

export function fmtData(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function InteracoesLista({ interacoes }: { interacoes: Interacao[] }) {
  if (interacoes.length === 0) {
    return <p className="text-xs text-muted-foreground" data-testid="interacoes-vazio">Nenhuma interação registrada.</p>;
  }
  return (
    <ol className="space-y-3" data-testid="interacoes-lista">
      {interacoes.map((i) => {
        const slots = Object.entries(i.slots ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
        return (
          <li key={i.id} className="rounded-md border p-2 text-xs">
            <p className="font-medium">{i.tipo ?? "Atendimento"}</p>
            <p className="text-muted-foreground">Iniciada em {fmtData(i.iniciada_em)}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {[i.canal, i.operacao, i.status].filter(Boolean).map((c) => (
                <span key={c} className="rounded-full bg-muted px-2 py-0.5">{c}</span>
              ))}
              {i.credito && <CreditoStatusChip status={typeof i.credito === "string" ? i.credito : i.credito.status} />}
            </div>
            {slots.length > 0 && (
              <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2">
                {slots.map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt><dd>{String(v)}</dd></div>
                ))}
              </dl>
            )}
            {i.resumo && <p className="mt-1">{i.resumo}</p>}
            {(i.intencoes ?? []).length > 0 && (
              <p className="mt-1 italic text-muted-foreground">{(i.intencoes ?? []).join(" · ")}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
