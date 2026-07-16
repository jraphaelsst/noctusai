/**
 * CreateFolderDialog — name-only create form. `parentId` is pre-set by the
 * trigger (root "+ Nova pasta" button → null; a folder's "Nova subpasta"
 * menu item → that folder's id) and is not user-editable in the dialog
 * itself, keeping the flow to one field per the "Two subtabs... folder tree
 * they build themselves" scope (no separate parent picker UI needed since
 * the entry point already carries that context).
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface CreateFolderDialogProps {
  open: boolean;
  parentId: string | null;
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (name: string, parentId: string | null) => void;
}

export function CreateFolderDialog({
  open,
  parentId,
  pending,
  onOpenChange,
  onSubmit,
}: CreateFolderDialogProps) {
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) setName("");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova pasta</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) onSubmit(name.trim(), parentId);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="n8n-folder-name">Nome</Label>
            <Input
              id="n8n-folder-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex.: Automações de vendas"
              autoFocus
            />
          </div>
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!name.trim() || pending}>
              {pending ? "Criando…" : "Criar pasta"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
