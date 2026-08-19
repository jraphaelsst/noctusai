/**
 * AgendamentoPopover — books ONE appointment. Opening it again books another.
 *
 * Replaces `DatasPopover`, which edited three columns on `clientes` and so
 * could only ever hold one appointment: saving a second overwrote the first.
 * The user named it exactly — *"it doesnt add multiple schedules, it replaces
 * the last one with the nem set one."* Migration `061` gave appointments their
 * own table; this popover is the surface that adds to it.
 *
 * Fields are the four the user asked for and no more: when, type, note,
 * reminder. No assignee — *"It doesnt need an assignee, only those."*
 *
 * Presentational (S3): `onCreate` is the only callback out; the caller owns
 * the POST.
 */
import { useState } from "react";
import { CalendarPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import type { AgendamentoCreateBody, TipoAgendamento } from "@/types/cardHub";

export const TIPO_OPTIONS: { value: TipoAgendamento; label: string }[] = [
  { value: "visita", label: "Visita" },
  { value: "ligacao", label: "Ligação" },
  { value: "reuniao", label: "Reunião" },
  { value: "outro", label: "Outro" },
];

/** `null` = no reminder. Distinct from 0 ("na hora") on purpose. */
export const LEMBRETE_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: "Sem lembrete" },
  { value: 0, label: "Na hora" },
  { value: 15, label: "15 minutos antes" },
  { value: 30, label: "30 minutos antes" },
  { value: 60, label: "1 hora antes" },
  { value: 1440, label: "1 dia antes" },
  { value: 10080, label: "1 semana antes" },
];

export interface AgendamentoPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (body: AgendamentoCreateBody) => void;
  saving?: boolean;
}

export function AgendamentoPopover({
  open,
  onOpenChange,
  onCreate,
  saving,
}: AgendamentoPopoverProps) {
  const [quando, setQuando] = useState("");
  const [tipo, setTipo] = useState<TipoAgendamento>("visita");
  const [nota, setNota] = useState("");
  const [lembrete, setLembrete] = useState<number | null>(60);

  function submit() {
    if (!quando) return;
    onCreate({
      // `datetime-local` yields wall-clock with no zone. `new Date()` reads it
      // in the browser's zone — which is what the user typed — and toISOString
      // hands the API UTC. Sending the raw string would store 09:00 as if it
      // were UTC and show the appointment three hours late in São Paulo.
      quando: new Date(quando).toISOString(),
      tipo,
      nota: nota.trim() || null,
      lembrete_minutos_antes: lembrete,
    });
    setQuando("");
    setNota("");
    onOpenChange(false);
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange} modal>
      {/* `modal` — see MembrosPopover: portaled out of the card dialog, whose
          scroll lock otherwise swallows wheel events aimed in here. */}
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" data-testid="agendamento-trigger">
          <CalendarPlus className="mr-2 h-4 w-4" />
          Agendar
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80" data-testid="agendamento-popover">
        <p className="mb-3 text-sm font-semibold">Novo agendamento</p>

        <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="ag-quando">
          Quando
        </label>
        <Input
          id="ag-quando"
          type="datetime-local"
          value={quando}
          onChange={(e) => setQuando(e.target.value)}
          className="mb-3"
          data-testid="agendamento-quando"
        />

        <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="ag-tipo">
          Tipo
        </label>
        <select
          id="ag-tipo"
          value={tipo}
          onChange={(e) => setTipo(e.target.value as TipoAgendamento)}
          className="mb-3 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          data-testid="agendamento-tipo"
        >
          {TIPO_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="ag-lembrete">
          Lembrete
        </label>
        <select
          id="ag-lembrete"
          value={lembrete === null ? "" : String(lembrete)}
          onChange={(e) => setLembrete(e.target.value === "" ? null : Number(e.target.value))}
          className="mb-3 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          data-testid="agendamento-lembrete-select"
        >
          {LEMBRETE_OPTIONS.map((o) => (
            <option key={String(o.value)} value={o.value === null ? "" : String(o.value)}>
              {o.label}
            </option>
          ))}
        </select>

        <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="ag-nota">
          Nota
        </label>
        <Textarea
          id="ag-nota"
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          rows={2}
          className="mb-3"
          data-testid="agendamento-nota"
        />

        <Button
          size="sm"
          className="w-full"
          disabled={!quando || saving}
          onClick={submit}
          data-testid="agendamento-salvar"
        >
          Agendar
        </Button>
      </PopoverContent>
    </Popover>
  );
}
