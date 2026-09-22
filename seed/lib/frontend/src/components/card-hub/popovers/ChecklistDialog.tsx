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
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/popovers/ChecklistDialog.tsx` into the
 * seed card hub (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md`
 * Slice C) — a MOVE, not a rewrite: markup, classes and data-testids are SW's,
 * so SW's own suites pass unchanged once it consumes this copy (Slice F).
 */
import { useEffect, useState } from "react";
import { CheckSquare } from "lucide-react";

import { CardHubButton as Button } from "../../../design-system/ui/card-hub-button";
import { CardHubInput as Input } from "../../../design-system/ui/card-hub-input";
import { Popover, PopoverContent, PopoverTrigger } from "../../../design-system/ui/popover";

import { TooltipCaption } from "../TooltipIconButton";

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
    <Popover open={open} onOpenChange={onOpenChange} modal>
      {/* `modal` — see MembrosPopover: portaled out of the card dialog, whose
          scroll lock otherwise swallows wheel events aimed in here. */}
      {/* Icon-only, caption on hover — the card's rule for every action
          (see `TooltipIconButton`). `aria-label` carries the SAME word, so
          the button keeps an accessible name a hover cannot provide.
          `TooltipCaption` wraps the PopoverTrigger rather than replacing the
          Button, because the trigger is what must own the ref Radix hands it. */}
      <TooltipCaption label="Checklist">
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 max-sm:min-h-10 max-sm:min-w-10"
            aria-label="Checklist"
            data-testid="checklist-trigger"
          >
            <CheckSquare className="h-4 w-4" aria-hidden="true" />
          </Button>
        </PopoverTrigger>
      </TooltipCaption>
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
