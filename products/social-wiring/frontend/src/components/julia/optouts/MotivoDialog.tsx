/** A design-system modal that asks for a REQUIRED reason before an irreversible-ish action (no browser dialogs). */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

export const MOTIVO_MAX = 500;

interface Props {
  aberto: boolean;
  titulo: string;
  descricao: string;
  confirmar: string;
  pendente: boolean;
  /** A server refusal to show inline (the modal stays open so the reason is not lost). */
  erro?: string | null;
  onConfirmar: (motivo: string) => void;
  onFechar: () => void;
}

export function MotivoDialog({ aberto, titulo, descricao, confirmar, pendente, erro, onConfirmar, onFechar }: Props) {
  const [motivo, setMotivo] = useState("");
  const limpo = motivo.trim();
  return (
    <Dialog open={aberto} onOpenChange={(o) => { if (!o && !pendente) onFechar(); }}>
      <DialogContent data-testid="motivo-dialog">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descricao}</DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <label htmlFor="motivo-dialog-texto" className="text-sm font-medium">Motivo (obrigatório)</label>
          <Textarea
            id="motivo-dialog-texto" value={motivo} maxLength={MOTIVO_MAX} rows={4} autoFocus
            onChange={(e) => setMotivo(e.target.value)} data-testid="motivo-dialog-texto"
          />
          <p className="text-right text-xs text-muted-foreground">{motivo.length}/{MOTIVO_MAX}</p>
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="motivo-dialog-erro">{erro}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onFechar} disabled={pendente}>Cancelar</Button>
          <Button onClick={() => onConfirmar(limpo)} disabled={!limpo || pendente} data-testid="motivo-dialog-confirmar">
            {pendente && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {confirmar}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
