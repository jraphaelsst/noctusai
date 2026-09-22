/**
 * DescricaoSection — the card's single Descrição, read + edit in place.
 *
 * The description is card STATE (`CardResumoBase.descricao`), not a timeline
 * event: one per card, edited, never appended.
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/ClienteCardDialog.tsx`
 * (a private sub-section there) into the seed card hub
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` Slice C).
 * Markup, classes and data-testids are SW's.
 *
 * Presentational only: props in, callbacks out.
 */
import { useState } from "react";
import { Check, ChevronDown, ChevronUp, FileText, Pencil, X } from "lucide-react";

import { Textarea } from "../../design-system/ui/textarea";

import { TooltipIconButton } from "./TooltipIconButton";

export interface DescricaoSectionProps {
  corpo: string;
  onSave: (corpo: string) => void;
  saving?: boolean;
}

export function DescricaoSection({
  corpo,
  onSave,
  saving,
}: DescricaoSectionProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(corpo);
  const [expanded, setExpanded] = useState(false);
  const isLong = corpo.length > 240;
  const shown = !isLong || expanded ? corpo : `${corpo.slice(0, 240)}…`;

  return (
    <div className="mb-4" data-testid="descricao-section">
      <div className="mb-1 flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <FileText className="h-3.5 w-3.5" />
          Descrição
        </p>
        {!editing && (
          // Icon-only, but NOT label-less: `aria-label` + the hover caption
          // carry the word "Editar", so trading the visible text for space
          // does not trade away what the button does.
          <TooltipIconButton
            label="Editar descrição"
            icon={Pencil}
            testId="descricao-editar-btn"
            className="h-7 w-7"
            onClick={() => {
              setDraft(corpo);
              setEditing(true);
            }}
          />
        )}
      </div>

      {editing ? (
        <div className="space-y-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            data-testid="descricao-textarea"
            autoFocus
          />
          <div className="flex gap-1">
            <TooltipIconButton
              label="Salvar descrição"
              icon={Check}
              testId="descricao-salvar-btn"
              variant="default"
              className="h-8 w-8"
              disabled={saving}
              onClick={() => {
                onSave(draft);
                setEditing(false);
              }}
            />
            <TooltipIconButton
              label="Cancelar"
              icon={X}
              testId="descricao-cancelar-btn"
              className="h-8 w-8"
              onClick={() => setEditing(false)}
            />
          </div>
        </div>
      ) : corpo ? (
        <>
          <p className="whitespace-pre-wrap break-words text-sm">{shown}</p>
          {isLong && (
            <TooltipIconButton
              label={expanded ? "Mostrar menos" : "Mostrar mais"}
              icon={expanded ? ChevronUp : ChevronDown}
              testId="descricao-mostrar-mais"
              variant="outline"
              className="mt-2 h-7 w-7"
              onClick={() => setExpanded((v) => !v)}
            />
          )}
        </>
      ) : (
        <p className="text-sm italic text-muted-foreground">Sem descrição ainda.</p>
      )}
    </div>
  );
}
