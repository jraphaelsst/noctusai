/**
 * ChecklistsSection / ChecklistBlock — the user-created working checklists:
 * title, progress bar, tickable items, inline add. Checklists are
 * user-created objects, not a fixed schema.
 *
 * MOVED from `products/social-wiring/frontend/src/components/card/ClienteCardDialog.tsx`
 * (a private sub-section there) into the seed card hub
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` Slice C).
 * Markup, classes and data-testids are SW's.
 *
 * Presentational only: props in, callbacks out.
 */
import { useState } from "react";
import { MoreHorizontal, Plus, Trash2 } from "lucide-react";

import { Progress } from "../../design-system/ui/progress";
import { cn } from "../../utils";

import { TokenCheckbox } from "./TokenCheckbox";
import { TooltipIconButton } from "./TooltipIconButton";
import type { Checklist } from "./types";

export interface ChecklistsSectionProps {
  checklists: Checklist[];
  /** No checklists yet — the FIRST load only; ignored once rows exist. */
  loading: boolean;
  onRemoveChecklist: (id: string) => void;
  onAddItem: (checklistId: string, texto: string) => void;
  onToggleItem: (checklistId: string, itemId: string, concluido: boolean) => void;
  onRemoveItem: (checklistId: string, itemId: string) => void;
}

export interface ChecklistBlockProps {
  checklist: Checklist;
  onRemove: () => void;
  onAddItem: (texto: string) => void;
  onToggleItem: (itemId: string, concluido: boolean) => void;
  onRemoveItem: (itemId: string) => void;
}

export function ChecklistsSection({
  checklists,
  loading,
  onRemoveChecklist,
  onAddItem,
  onToggleItem,
  onRemoveItem,
}: ChecklistsSectionProps) {
  // Two signals, never one (`KB § PATTERNS/frontend/lying-loading-state.md`):
  // the skeleton only while there is genuinely nothing yet — a stale
  // `loading` mid-refetch never unmounts checklists that are already here.
  if (loading && checklists.length === 0) {
    return <div className="h-16 animate-pulse rounded bg-muted" data-testid="checklists-loading" />;
  }
  if (checklists.length === 0) return null;

  return (
    <div className="space-y-5" data-testid="checklists-section">
      {checklists.map((cl) => (
        <ChecklistBlock
          key={cl.id}
          checklist={cl}
          onRemove={() => onRemoveChecklist(cl.id)}
          onAddItem={(texto) => onAddItem(cl.id, texto)}
          onToggleItem={(itemId, concluido) => onToggleItem(cl.id, itemId, concluido)}
          onRemoveItem={(itemId) => onRemoveItem(cl.id, itemId)}
        />
      ))}
    </div>
  );
}

export function ChecklistBlock({
  checklist,
  onRemove,
  onAddItem,
  onToggleItem,
  onRemoveItem,
}: ChecklistBlockProps) {
  const [novoItem, setNovoItem] = useState("");
  const percent = checklist.total_itens > 0 ? Math.round((checklist.concluidos / checklist.total_itens) * 100) : 0;

  return (
    <div data-testid={`checklist-block-${checklist.id}`}>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-sm font-semibold">{checklist.titulo}</p>
        <TooltipIconButton
          label={`Excluir checklist ${checklist.titulo}`}
          icon={Trash2}
          testId={`checklist-excluir-${checklist.id}`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={onRemove}
        />
      </div>
      <div className="mb-2 flex items-center gap-2">
        <span className="w-9 text-xs text-muted-foreground">{percent}%</span>
        <Progress value={percent} className="h-2 flex-1" />
      </div>
      <ul className="space-y-1">
        {checklist.itens.map((item) => (
          <li key={item.id} className="group flex items-center gap-2">
            <TokenCheckbox
              checked={item.concluido}
              onCheckedChange={(c) => onToggleItem(item.id, c)}
              label={item.texto}
              testId={`checklist-item-checkbox-${item.id}`}
            />
            <span className={cn("flex-1 text-sm", item.concluido && "text-muted-foreground line-through")}>
              {item.texto}
            </span>
            <button
              type="button"
              onClick={() => onRemoveItem(item.id)}
              aria-label={`Remover ${item.texto}`}
              // No hover on a phone: below `sm` the control is always visible
              // and meets the 40px touch floor. Desktop keeps SW's reveal.
              className="opacity-0 group-hover:opacity-100 max-sm:flex max-sm:min-h-10 max-sm:min-w-10 max-sm:items-center max-sm:justify-center max-sm:opacity-100"
              data-testid={`checklist-item-remover-${item.id}`}
            >
              <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          placeholder="Adicionar um item"
          aria-label={`Adicionar um item em ${checklist.titulo}`}
          value={novoItem}
          onChange={(e) => setNovoItem(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && novoItem.trim()) {
              onAddItem(novoItem.trim());
              setNovoItem("");
            }
          }}
          className="h-8 flex-1 rounded border bg-background px-2 text-sm max-sm:h-10"
          data-testid={`checklist-novo-item-${checklist.id}`}
        />
        <TooltipIconButton
          label="Adicionar item"
          icon={Plus}
          testId={`checklist-adicionar-item-${checklist.id}`}
          variant="outline"
          className="h-8 w-8"
          onClick={() => {
            if (!novoItem.trim()) return;
            onAddItem(novoItem.trim());
            setNovoItem("");
          }}
        />
      </div>
    </div>
  );
}
