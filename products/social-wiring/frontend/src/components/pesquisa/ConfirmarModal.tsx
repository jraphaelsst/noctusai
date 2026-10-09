import { useEffect, useState } from "react";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  titulo: string;
  descricao: string;
  rotuloConfirmar: string;
  onConfirmar: () => void;
  pendente?: boolean;
  /** When set, the confirm button only enables after typing exactly this text. */
  digitarPara?: string;
}

/** Destructive confirmation; optionally requires typing a phrase (brand name). */
export function ConfirmarModal({
  open,
  onOpenChange,
  titulo,
  descricao,
  rotuloConfirmar,
  onConfirmar,
  pendente = false,
  digitarPara,
}: Props) {
  const [digitado, setDigitado] = useState("");
  useEffect(() => {
    if (open) setDigitado("");
  }, [open]);
  const liberado = !digitarPara || digitado.trim() === digitarPara.trim();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{titulo}</AlertDialogTitle>
          <AlertDialogDescription>{descricao}</AlertDialogDescription>
        </AlertDialogHeader>
        {digitarPara && (
          <div className="space-y-1.5">
            <label htmlFor="pesquisa-confirmar-nome" className="text-sm">
              Digite <strong>{digitarPara}</strong> para confirmar
            </label>
            <Input
              id="pesquisa-confirmar-nome"
              value={digitado}
              onChange={(e) => setDigitado(e.target.value)}
              autoComplete="off"
            />
          </div>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pendente}>Cancelar</AlertDialogCancel>
          <Button variant="destructive" disabled={!liberado || pendente} onClick={onConfirmar}>
            {pendente ? "Aguarde…" : rotuloConfirmar}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
