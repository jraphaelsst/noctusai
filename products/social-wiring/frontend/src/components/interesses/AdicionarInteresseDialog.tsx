/**
 * AdicionarInteresseDialog — the small "Adicionar interesse" popup: a live
 * código search, click a row to add it. Also reused (via `titulo`) by the
 * proprietários section to register an owned imóvel — same flow, different
 * destination, so the caller owns the mutation (`onSelecionar`).
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ImovelResumo } from "@/types/interesses";

import { ImovelBuscaTypeahead } from "./ImovelBuscaTypeahead";

export interface AdicionarInteresseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelecionar: (imovel: ImovelResumo) => void;
  jaNaLista?: string[];
  titulo?: string;
  descricao?: string;
}

export function AdicionarInteresseDialog({
  open,
  onOpenChange,
  onSelecionar,
  jaNaLista,
  titulo = "Adicionar interesse",
  descricao = "Digite o código — a lista se afunila até sobrar o imóvel. Clique para adicionar.",
}: AdicionarInteresseDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="adicionar-interesse-dialog">
        <DialogHeader>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>{descricao}</DialogDescription>
        </DialogHeader>
        {/* Mounted only while open ⇒ the search box resets on every open. */}
        {open && (
          <ImovelBuscaTypeahead autoFocus onSelect={onSelecionar} jaNaLista={jaNaLista} />
        )}
      </DialogContent>
    </Dialog>
  );
}
