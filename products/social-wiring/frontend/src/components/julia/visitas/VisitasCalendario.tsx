/**
 * Week / day calendar. There is deliberately NO month view (Julia rejects it).
 */
import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Visita, VisitasView } from "@/hooks/useJuliaVisitas";
import { chaveData, dataDe, diasDaJanela, hhmm, paraData, somarDias } from "./calendario";

export const STATUS_LABEL: Record<Visita["status"], string> = {
  solicitada: "Solicitada", confirmada: "Confirmada", remarcada: "Remarcada", cancelada: "Cancelada",
};
export const STATUS_CLASSE: Record<Visita["status"], string> = {
  solicitada: "bg-warning-light text-warning-foreground", confirmada: "bg-success-light text-success",
  remarcada: "bg-info-light text-info", cancelada: "bg-muted text-muted-foreground line-through",
};
const SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

interface Props {
  view: VisitasView;
  data: string;
  visitas: Visita[];
  onView: (v: VisitasView) => void;
  onData: (d: string) => void;
  onAbrir: (v: Visita) => void;
}

export function VisitasCalendario({ view, data, visitas, onView, onData, onAbrir }: Props) {
  const dias = diasDaJanela(view, data);
  const passo = view === "dia" ? 1 : 7;
  const titulo = view === "dia"
    ? paraData(data).toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })
    : `${paraData(dias[0]).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} – ${paraData(dias[6]).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}`;

  return (
    <section data-testid="visitas-calendario" data-view={view} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Anterior" onClick={() => onData(somarDias(data, -passo))}><ChevronLeft className="h-4 w-4" /></Button>
        <Button variant="outline" size="sm" onClick={() => onData(chaveData(new Date()))}>Hoje</Button>
        <Button variant="outline" size="icon" aria-label="Próximo" onClick={() => onData(somarDias(data, passo))}><ChevronRight className="h-4 w-4" /></Button>
        <h2 className="ml-2 text-sm font-medium capitalize" data-testid="visitas-titulo">{titulo}</h2>
        <div className="ml-auto flex gap-1" role="group" aria-label="Visualização">
          {(["semana", "dia"] as const).map((v) => (
            <Button key={v} size="sm" variant={view === v ? "default" : "outline"} aria-pressed={view === v} onClick={() => onView(v)}>
              {v === "semana" ? "Semana" : "Dia"}
            </Button>
          ))}
        </div>
      </div>
      <div className={`grid gap-2 ${view === "semana" ? "md:grid-cols-7" : "grid-cols-1"}`}>
        {dias.map((d) => {
          const doDia = visitas.filter((v) => dataDe(v.inicio) === d).sort((a, b) => a.inicio.localeCompare(b.inicio));
          const dt = paraData(d);
          return (
            <div key={d} data-testid={`dia-${d}`} className="min-h-24 rounded-md border p-2">
              <div className="mb-1 text-xs font-medium text-muted-foreground">{SEMANA[(dt.getDay() + 6) % 7]} {dt.getDate()}</div>
              {doDia.length === 0 ? <p className="text-xs text-muted-foreground">Sem visitas</p> : (
                <ul className="space-y-1">
                  {doDia.map((v) => (
                    <li key={v.id}>
                      <button type="button" onClick={() => onAbrir(v)}
                        className={`w-full rounded px-2 py-1 text-left text-xs ${STATUS_CLASSE[v.status]}`}>
                        {hhmm(v.inicio)}–{hhmm(v.fim)} · {v.contato_nome ?? "Lead"}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
