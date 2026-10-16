/** "Ver resumo" panel — the Julia summary + collected slots of one lead. */
import { Skeleton } from "@/components/ui/skeleton";
import { useResumoLead, type LeadLais } from "@/hooks/useLaisLeads";
import { SidePanel } from "../SidePanel";

export function ResumoPanel({ lead, onClose }: { lead: LeadLais; onClose: () => void }) {
  const q = useResumoLead(lead.id);
  const slots = Object.entries(q.data?.slots ?? {}).filter(([, v]) => v !== null && v !== "");
  return (
    <SidePanel title={`Resumo — ${lead.nome ?? "Lead"}`} testId="leads-resumo" onClose={onClose}>
      {q.isPending && !q.data ? (
        <div data-testid="resumo-skeleton" className="space-y-2"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-2/3" /></div>
      ) : q.isError && !q.data ? (
        <p role="alert" className="text-sm text-destructive" data-testid="resumo-erro">Não foi possível carregar o resumo.</p>
      ) : (
        <>
          {q.data?.resumo ? <p className="whitespace-pre-wrap text-sm" data-testid="resumo-texto">{q.data.resumo}</p>
            : <p className="text-sm text-muted-foreground" data-testid="resumo-vazio">A Julia ainda não gerou um resumo para este lead.</p>}
          {slots.length > 0 && (
            <dl className="grid grid-cols-2 gap-2 text-sm" data-testid="resumo-slots">
              {slots.map(([k, v]) => (<div key={k}><dt className="text-xs text-muted-foreground">{k}</dt><dd>{String(v)}</dd></div>))}
            </dl>
          )}
          {!!q.data?.intencoes?.length && (
            <ul className="list-disc pl-5 text-sm italic">{q.data.intencoes.map((i) => <li key={i}>{i}</li>)}</ul>
          )}
        </>
      )}
    </SidePanel>
  );
}
