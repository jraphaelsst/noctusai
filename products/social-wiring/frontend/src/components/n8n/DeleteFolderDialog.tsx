/**
 * DeleteFolderDialog — deleting a folder requires choosing where its
 * contents (child folders + workflows) land (`reassign_to`). Defaults to
 * the folder's own parent ("move up one level") when it has one, else the
 * root — the least-surprising choice — and lets the operator pick a
 * different existing folder instead. Self and descendants are excluded
 * from the picker (can't reassign into the thing being deleted).
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
import type { N8nFolderOut } from "@/hooks/useN8nWorkflows";

const ROOT_SENTINEL = "__root__";

export interface DeleteFolderDialogProps {
  folder: N8nFolderOut | null;
  /** Every other folder eligible as a reassign target (self + descendants
   * already excluded by the caller). */
  candidateFolders: N8nFolderOut[];
  pending: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reassignTo: string | null) => void;
}

export function DeleteFolderDialog({
  folder,
  candidateFolders,
  pending,
  onOpenChange,
  onConfirm,
}: DeleteFolderDialogProps) {
  const [target, setTarget] = useState<string>(ROOT_SENTINEL);

  useEffect(() => {
    if (folder) setTarget(folder.parent_id ?? ROOT_SENTINEL);
  }, [folder]);

  return (
    <Dialog open={!!folder} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Excluir pasta "{folder?.name}"?</DialogTitle>
          <DialogDescription>
            Escolha para onde mover as subpastas e fluxos desta pasta antes de excluí-la.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label>Mover conteúdo para</Label>
          <Select value={target} onValueChange={setTarget}>
            <SelectTrigger data-testid="n8n-delete-folder-reassign">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ROOT_SENTINEL}>Raiz (sem pasta)</SelectItem>
              {candidateFolders.map((f) => (
                <SelectItem key={f.id} value={f.id}>
                  {f.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter className="mt-4">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
            Cancelar
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={pending}
            onClick={() => onConfirm(target === ROOT_SENTINEL ? null : target)}
          >
            {pending ? "Excluindo…" : "Excluir pasta"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
