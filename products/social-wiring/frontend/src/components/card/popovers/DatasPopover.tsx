/**
 * DatasPopover — screenshot 06: Data de início, Data de entrega (date +
 * time), Recorrente, Definir lembrete, with the reminder note verbatim from
 * the shot ("Lembretes serão enviados a todos os membros e seguidores deste
 * cartão"), Salvar / Remover. PROJECT.md §3/§4.
 *
 * TRADEOFF, said plainly: the shot shows a full month calendar grid; this
 * uses native `<input type="date">`/`type="time">` instead of hand-rolling
 * a calendar widget — same data captured (start/due date, time, recurrence,
 * reminder), materially less surface to build and test this slice. Flagged
 * as a `scoped-improvement:` candidate, not silently substituted.
 *
 * Presentational (S3): `onSave`/`onRemove` are the only callbacks out; the
 * caller (`useDatasMutation`) owns the PATCH.
 */
import { useEffect, useState } from "react";
import { Calendar } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CardDatas, DatasPatchBody, Recorrencia } from "@/types/cardHub";

export interface DatasPopoverProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  datas: CardDatas | null;
  onSave: (body: DatasPatchBody) => void;
  onRemove: () => void;
  saving?: boolean;
}

const RECORRENCIA_OPTIONS: { value: string; label: string }[] = [
  { value: "nunca", label: "Nunca" },
  { value: "diaria", label: "Diariamente" },
  { value: "semanal", label: "Semanalmente" },
  { value: "mensal", label: "Mensalmente" },
  { value: "anual", label: "Anualmente" },
];

const LEMBRETE_OPTIONS: { value: string; label: string }[] = [
  { value: "0", label: "Nenhum" },
  { value: "60", label: "1 hora antes" },
  { value: "1440", label: "1 dia antes" },
  { value: "2880", label: "2 dias antes" },
];

function splitDateTime(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { date: "", time: "" };
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

function joinDateTime(date: string, time: string): string | null {
  if (!date) return null;
  return new Date(`${date}T${time || "00:00"}:00`).toISOString();
}

export function DatasPopover({ open, onOpenChange, datas, onSave, onRemove, saving }: DatasPopoverProps) {
  const inicioParts = splitDateTime(datas?.data_inicio ?? null);
  const entregaParts = splitDateTime(datas?.data_entrega ?? null);

  const [inicioAtivo, setInicioAtivo] = useState(!!datas?.data_inicio);
  const [inicioData, setInicioData] = useState(inicioParts.date);
  const [entregaAtivo, setEntregaAtivo] = useState(!!datas?.data_entrega);
  const [entregaData, setEntregaData] = useState(entregaParts.date);
  const [entregaHora, setEntregaHora] = useState(entregaParts.time || "09:00");
  const [recorrencia, setRecorrencia] = useState<string>(datas?.recorrencia ?? "nunca");
  const [lembrete, setLembrete] = useState<string>(String(datas?.lembrete_minutos_antes ?? 0));

  // Re-sync local draft state whenever the popover is (re)opened against
  // fresh server data — otherwise a second open would show the FIRST
  // open's stale draft.
  useEffect(() => {
    if (!open) return;
    const i = splitDateTime(datas?.data_inicio ?? null);
    const e = splitDateTime(datas?.data_entrega ?? null);
    setInicioAtivo(!!datas?.data_inicio);
    setInicioData(i.date);
    setEntregaAtivo(!!datas?.data_entrega);
    setEntregaData(e.date);
    setEntregaHora(e.time || "09:00");
    setRecorrencia(datas?.recorrencia ?? "nunca");
    setLembrete(String(datas?.lembrete_minutos_antes ?? 0));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function submit() {
    const body: DatasPatchBody = {
      data_inicio: inicioAtivo ? joinDateTime(inicioData, "00:00") : null,
      data_entrega: entregaAtivo ? joinDateTime(entregaData, entregaHora) : null,
      recorrencia: recorrencia === "nunca" ? null : (recorrencia as Recorrencia),
      lembrete_minutos_antes: Number(lembrete) > 0 ? Number(lembrete) : null,
    };
    onSave(body);
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange} modal>
      {/* `modal` — see MembrosPopover: portaled out of the card dialog, whose
          scroll lock otherwise swallows wheel events aimed in here. */}
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" data-testid="datas-trigger">
          <Calendar className="mr-2 h-4 w-4" />
          Datas
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 space-y-3" data-testid="datas-popover">
        <p className="text-sm font-semibold">Datas</p>

        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <Checkbox
              checked={inicioAtivo}
              onCheckedChange={(v) => setInicioAtivo(!!v)}
              data-testid="datas-inicio-checkbox"
            />
            Data de início
          </label>
          <Input
            type="date"
            disabled={!inicioAtivo}
            value={inicioData}
            onChange={(e) => setInicioData(e.target.value)}
            data-testid="datas-inicio-input"
          />
        </div>

        <div className="space-y-1.5">
          <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <Checkbox
              checked={entregaAtivo}
              onCheckedChange={(v) => setEntregaAtivo(!!v)}
              data-testid="datas-entrega-checkbox"
            />
            Data de entrega
          </label>
          <div className="flex gap-2">
            <Input
              type="date"
              disabled={!entregaAtivo}
              value={entregaData}
              onChange={(e) => setEntregaData(e.target.value)}
              data-testid="datas-entrega-data-input"
            />
            <Input
              type="time"
              disabled={!entregaAtivo}
              value={entregaHora}
              onChange={(e) => setEntregaHora(e.target.value)}
              data-testid="datas-entrega-hora-input"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Recorrente</label>
          <Select value={recorrencia} onValueChange={setRecorrencia}>
            <SelectTrigger data-testid="datas-recorrencia-trigger">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RECORRENCIA_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value} data-testid={`datas-recorrencia-option-${o.value}`}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Definir lembrete</label>
          <Select value={lembrete} onValueChange={setLembrete}>
            <SelectTrigger data-testid="datas-lembrete-trigger">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LEMBRETE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value} data-testid={`datas-lembrete-option-${o.value}`}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <p className="text-xs text-muted-foreground">
          Lembretes serão enviados a todos os membros e seguidores deste cartão.
        </p>

        <div className="space-y-2 pt-1">
          <Button className="w-full" disabled={saving} onClick={submit} data-testid="datas-salvar">
            Salvar
          </Button>
          <Button
            variant="outline"
            className="w-full"
            disabled={saving}
            onClick={onRemove}
            data-testid="datas-remover"
          >
            Remover
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
