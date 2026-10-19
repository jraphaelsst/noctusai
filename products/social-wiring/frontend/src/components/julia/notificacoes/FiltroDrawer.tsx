import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FILTRO_VAZIO, TIPOS_NOTIFICACAO, type NotificacoesFiltro, type OperacaoFiltro } from "@/hooks/useLaisNotificacoes";

interface Props { aberto: boolean; filtro: NotificacoesFiltro; onClose: () => void; onAplicar: (f: NotificacoesFiltro) => void }

const OPERACOES: { value: OperacaoFiltro; label: string }[] = [
  { value: "", label: "Todas" }, { value: "aluguel", label: "Aluguel" }, { value: "compra", label: "Compra" },
];
const INPUT = "h-9 w-full rounded-md border bg-background px-2 text-sm";

export function FiltroDrawer({ aberto, filtro, onClose, onAplicar }: Props) {
  const [f, setF] = useState(filtro);
  return (
    <Dialog open={aberto} onOpenChange={(o) => { if (!o) onClose(); else setF(filtro); }}>
      <DialogContent className="max-w-md" aria-describedby={undefined}>
        <DialogHeader><DialogTitle>Filtro de notificações</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold text-muted-foreground">DATA</legend>
            <div className="flex gap-2">
              <input type="date" aria-label="Data inicial" className={INPUT} value={f.de} onChange={(e) => setF({ ...f, de: e.target.value })} />
              <input type="date" aria-label="Data final" className={INPUT} value={f.ate} onChange={(e) => setF({ ...f, ate: e.target.value })} />
            </div>
          </fieldset>
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold text-muted-foreground">OPERAÇÕES</legend>
            <div className="flex gap-3">
              {OPERACOES.map((o) => (
                <label key={o.value} className="flex items-center gap-1 text-sm">
                  <input type="radio" name="operacao" checked={f.operacao === o.value} onChange={() => setF({ ...f, operacao: o.value })} /> {o.label}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold text-muted-foreground">TIPO DE NOTIFICAÇÃO</legend>
            <div className="max-h-56 space-y-1 overflow-y-auto">
              {TIPOS_NOTIFICACAO.map((t) => (
                <label key={t.value} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="tipo" checked={f.tipo === t.value} onChange={() => setF({ ...f, tipo: t.value })} /> {t.label}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => { setF(FILTRO_VAZIO); onAplicar(FILTRO_VAZIO); }}>Limpar</Button>
          <Button onClick={() => onAplicar({ ...f, page: 1 })}>Filtrar</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
