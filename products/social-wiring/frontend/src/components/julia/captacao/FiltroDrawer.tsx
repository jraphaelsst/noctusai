/** "Filtros" drawer (Julia Captação): status + date range. Draft applies only on Filtrar. */
import { useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { FILTRO_VAZIO, type CaptacaoFiltro, type StatusFiltro } from "@/hooks/useJuliaCaptacao";

interface Props { filtro: CaptacaoFiltro; onClose: () => void; onAplicar: (f: CaptacaoFiltro) => void }

const STATUS: { value: StatusFiltro; label: string }[] = [
  { value: "", label: "Todas" },
  { value: "nova", label: "Novas" },
  { value: "registrada", label: "Registradas" },
  { value: "descartada", label: "Descartadas" },
];
const INPUT = "h-9 w-full rounded-md border bg-background px-2 text-sm";

export function FiltroDrawer({ filtro, onClose, onAplicar }: Props) {
  const [f, setF] = useState(filtro);
  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Filtros"
      width="sm"
      testId="captacao-filtro-drawer"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => onAplicar({ ...FILTRO_VAZIO, pageSize: filtro.pageSize })}>Limpar</Button>
          <Button onClick={() => onAplicar({ ...f, page: 1 })}>Filtrar</Button>
        </div>
      }
    >
      <div className="space-y-5">
        <fieldset className="space-y-1">
          <legend className="text-xs font-semibold text-muted-foreground">STATUS</legend>
          {STATUS.map((s) => (
            <label key={s.value || "todas"} className="flex items-center gap-2 text-sm">
              <input type="radio" name="status" checked={f.status === s.value} onChange={() => setF({ ...f, status: s.value })} /> {s.label}
            </label>
          ))}
        </fieldset>
        <fieldset className="space-y-1">
          <legend className="text-xs font-semibold text-muted-foreground">DATA</legend>
          <div className="flex gap-2">
            <input type="date" aria-label="Data inicial" className={INPUT} value={f.de} onChange={(e) => setF({ ...f, de: e.target.value })} />
            <input type="date" aria-label="Data final" className={INPUT} value={f.ate} onChange={(e) => setF({ ...f, ate: e.target.value })} />
          </div>
        </fieldset>
      </div>
    </SideDrawer>
  );
}
