/**
 * PerderAtendimentoDialog — mark a funil card as LOST, with a reason.
 *
 * The reason is a CLOSED set (`MOTIVOS_PERDA`) because lost deals are a data
 * signal (e.g. "preço acima do mercado" is evidence an asking price sits above
 * market); the free note is optional except for "Outro". Sibling of
 * `ClienteCardDialog`'s own Dialog, never nested in it (focus trap) — same
 * mounting rule as `ArquivarAtendimentoConfirmDialog`. Presentational: the
 * owner (`ClienteDetailModal`) owns the mutation and closes on success.
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { MOTIVOS_PERDA, exigeObservacao, type MotivoPerdaCategoria } from "@/lib/motivoPerda";

export interface PerderAtendimentoDialogProps {
  open: boolean;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (input: { categoria: MotivoPerdaCategoria; motivo?: string }) => void;
}

export function PerderAtendimentoDialog({
  open,
  pending,
  onOpenChange,
  onConfirm,
}: PerderAtendimentoDialogProps) {
  const [categoria, setCategoria] = useState<MotivoPerdaCategoria | "">("");
  const [observacao, setObservacao] = useState("");

  // A reopened dialog starts blank — a stale reason from the previous card
  // must never be one click from being submitted for the next.
  useEffect(() => {
    if (!open) {
      setCategoria("");
      setObservacao("");
    }
  }, [open]);

  const obrigatoria = exigeObservacao(categoria);
  const nota = observacao.trim();
  const podeConfirmar = categoria !== "" && (!obrigatoria || nota.length > 0);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="perder-atendimento-dialog">
        <DialogHeader>
          <DialogTitle>Marcar como perdida</DialogTitle>
          <DialogDescription>
            O card sai do funil como negócio perdido. O motivo fica registrado
            e ajuda a entender por que as vendas não fecham.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="perder-categoria">Motivo</Label>
            <Select
              value={categoria}
              onValueChange={(v) => setCategoria(v as MotivoPerdaCategoria)}
              disabled={pending}
            >
              <SelectTrigger id="perder-categoria" data-testid="perder-categoria">
                <SelectValue placeholder="Selecione o motivo" />
              </SelectTrigger>
              <SelectContent>
                {MOTIVOS_PERDA.map((m) => (
                  <SelectItem key={m.value} value={m.value}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="perder-observacao">
              Observação{obrigatoria ? "" : " (opcional)"}
            </Label>
            <Textarea
              id="perder-observacao"
              data-testid="perder-observacao"
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              placeholder={obrigatoria ? "Descreva o motivo" : "Algo mais que valha registrar"}
              rows={3}
              disabled={pending}
            />
            {obrigatoria && nota.length === 0 && (
              <p className="text-xs text-muted-foreground">
                Para o motivo &quot;Outro&quot; a observação é obrigatória.
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            data-testid="perder-atendimento-confirm"
            disabled={!podeConfirmar || pending}
            onClick={() => {
              if (categoria === "") return;
              onConfirm({ categoria, motivo: nota || undefined });
            }}
          >
            {pending ? "Salvando…" : "Marcar como perdida"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
