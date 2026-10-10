/** Asks the optional `instagram.com` permalink when a post enters the `postado` stage (§6.1). */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { permalinkValido } from "./moveRules";

export interface PostadoDialogProps {
  open: boolean;
  onCancel: () => void;
  /** `permalink` is `undefined` when left blank. */
  onConfirm: (permalink: string | undefined) => void;
}

export function PostadoDialog({ open, onCancel, onConfirm }: PostadoDialogProps) {
  const [url, setUrl] = useState("");
  const valido = permalinkValido(url);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Marcar como postado</DialogTitle>
          <DialogDescription>O link é opcional e pode ser adicionado depois no post.</DialogDescription>
        </DialogHeader>
        <label className="space-y-1 text-sm">
          <span>Link do post (opcional)</span>
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.instagram.com/reel/..."
            aria-invalid={!valido}
          />
        </label>
        {!valido && <p className="text-xs text-destructive">Use um link do instagram.com.</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancelar
          </Button>
          <Button disabled={!valido} onClick={() => onConfirm(url.trim() || undefined)}>
            Confirmar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
