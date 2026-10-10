import { Badge } from "@/components/ui/badge";
import type { ExtractionJob } from "@/hooks/usePesquisaExtracao";
import { formatData, STATUS_ROTULO, TIPO_ROTULO } from "./format";

export function ExtracoesRecentes({ jobs }: { jobs: ExtractionJob[] }) {
  return (
    <section aria-label="Extrações recentes" className="flex flex-col gap-2">
      <h2 className="text-sm font-medium">Extrações recentes</h2>
      {jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhuma extração ainda.</p>
      ) : (
        <ul className="divide-y rounded-lg border text-sm">
          {jobs.map((j) => (
            <li key={j.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
              <span>{formatData(j.created_at)}</span>
              <span>{j.tipos.map((t) => TIPO_ROTULO[t]).join(" + ")}</span>
              <span>{j.total_tarefas} post(s)</span>
              <Badge variant="secondary">{STATUS_ROTULO[j.status]}</Badge>
              <span className="text-muted-foreground">
                {j.itens_salvos} item(ns) · {j.assuntos_salvos} assunto(s)
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
