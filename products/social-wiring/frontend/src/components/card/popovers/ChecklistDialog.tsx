/**
 * ChecklistDialog — screenshot 07: "Adicionar checklist", a single Título
 * field pre-filled "Checklist", Adicionar. Confirms checklists are
 * user-created objects, not a fixed schema (D11's ad-hoc half).
 * PROJECT.md §4.
 *
 * Named `ChecklistDialog` per the brief/contract, implemented as a Popover
 * (matches the compact floating panel the screenshot actually shows,
 * anchored under the Checklist button — not a full modal).
 *
 * Presentational (S3): `onCreate` is the only callback out.
 */
import { useEffect, useState } from "react";
import { CheckSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export interface ChecklistDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreate: (titulo: string) => void;
  saving?: boolean;
}

export function ChecklistDialog({ open, onOpenChange, onCreate, saving }: ChecklistDialogProps) {
  const [titulo, setTitulo] = useState("Checklist");

  useEffect(() => {
    if (open) setTitulo("Checklist");
  }, [open]);

  function submit() {
    if (!titulo.trim()) return;
    onCreate(titulo.trim());
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" data-testid="checklist-trigger">
          <CheckSquare className="mr-2 h-4 w-4" />
          Checklist
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" data-testid="checklist-popover">
        <p className="mb-3 text-center text-sm font-semibold">Adicionar checklist</p>
        <label className="mb-1 block text-xs font-medium text-muted-foreground">Título</label>
        <Input
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          className="mb-3"
          autoFocus
          data-testid="checklist-titulo-input"
        />
        <Button className="w-full" disabled={saving} onClick={submit} data-testid="checklist-adicionar-btn">
          Adicionar
        </Button>
      </PopoverContent>
    </Popover>
  );
}
