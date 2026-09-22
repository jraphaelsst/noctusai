/**
 * GeralSubpage + GeralActions — the card's open-on-mount working surface.
 *
 * MOVED from the `subpage === "geral"` branch of
 * `products/social-wiring/frontend/src/components/card/ClienteCardDialog.tsx`
 * into the seed card hub
 * (`project-history/roadmaps/cardhub-igig-crm-2026-09.wave-a-design.md` §2,
 * Slice C). Markup, classes and data-testids are SW's.
 *
 * 🔴 NAMED SLOTS, NOT A FORK
 * --------------------------
 * The seed owns the generic spine — etiquetas chips, descrição, anexos, the
 * working checklists — in the order the work happens. A product inserts what
 * only it has at NAMED points (`slots.afterTags`, `slots.afterDescricao`,
 * `slots.beforeAnexos`) instead of copying the subpage to add one block. SW
 * puts its contact line after the tags, the mandatory-data fold after the
 * descrição, and each party's paperwork before the anexos.
 *
 * `GeralActions` is the quick-action row (Etiquetas / Checklist / Membros)
 * — register it as the Geral subpage's `toolbar`. A product adds its own
 * popover after Etiquetas through `afterEtiquetas` (SW: Agendar). Popover
 * state is uncontrolled by default; pass `activePopover` +
 * `onActivePopoverChange` to share one "which popover is open" state with a
 * product popover mounted elsewhere.
 *
 * Presentational only: props in, callbacks out.
 */
import { useState, type ReactNode } from "react";

import { AnexosSection, type AnexosSectionProps } from "./AnexosSection";
import { ChecklistsSection, type ChecklistsSectionProps } from "./ChecklistsSection";
import { DescricaoSection, type DescricaoSectionProps } from "./DescricaoSection";
import { ChecklistDialog } from "./popovers/ChecklistDialog";
import { EtiquetasPopover, type EtiquetasPopoverProps } from "./popovers/EtiquetasPopover";
import { MembrosPopover, type MembrosPopoverProps } from "./popovers/MembrosPopover";
import type { Tag } from "./types";

// ─── GeralActions ─────────────────────────────────────────────────────────

/** The seed's own popover keys; a product may use further keys for its own
 *  popovers when it controls the state. */
export type GeralPopoverKey = "etiquetas" | "checklist" | "membros" | (string & {});

export interface GeralActionsProps {
  etiquetas: Omit<EtiquetasPopoverProps, "open" | "onOpenChange">;
  membros: Omit<MembrosPopoverProps, "open" | "onOpenChange">;
  onCreateChecklist: (titulo: string) => void;
  checklistSaving?: boolean;
  /** Rendered between Etiquetas and Checklist — a product's own action. */
  afterEtiquetas?: ReactNode;
  /** Controlled popover state (optional). */
  activePopover?: GeralPopoverKey | null;
  onActivePopoverChange?: (key: GeralPopoverKey | null) => void;
}

export function GeralActions({
  etiquetas,
  membros,
  onCreateChecklist,
  checklistSaving,
  afterEtiquetas,
  activePopover: controlled,
  onActivePopoverChange,
}: GeralActionsProps) {
  const [local, setLocal] = useState<GeralPopoverKey | null>(null);
  const active = controlled !== undefined ? controlled : local;
  const setActive = (key: GeralPopoverKey | null) => {
    if (controlled === undefined) setLocal(key);
    onActivePopoverChange?.(key);
  };

  return (
    <div className="mb-4 flex flex-wrap gap-1" data-testid="card-geral-actions">
      <EtiquetasPopover
        {...etiquetas}
        open={active === "etiquetas"}
        onOpenChange={(o) => setActive(o ? "etiquetas" : null)}
      />
      {afterEtiquetas}
      <ChecklistDialog
        open={active === "checklist"}
        onOpenChange={(o) => setActive(o ? "checklist" : null)}
        saving={checklistSaving}
        onCreate={(titulo) => {
          onCreateChecklist(titulo);
          setActive(null);
        }}
      />
      <MembrosPopover
        {...membros}
        open={active === "membros"}
        onOpenChange={(o) => setActive(o ? "membros" : null)}
      />
    </div>
  );
}

// ─── GeralSubpage ─────────────────────────────────────────────────────────

export interface GeralSubpageSlots {
  /** After the etiquetas chips (SW: the contact line). */
  afterTags?: ReactNode;
  /** After the descrição (SW: the Dados obrigatórios fold). */
  afterDescricao?: ReactNode;
  /** Before the anexos (SW: each party's paperwork panel). */
  beforeAnexos?: ReactNode;
}

export interface GeralSubpageProps {
  /** The card's selected tags — rendered as chips, only when there are any. */
  tags: Tag[];
  descricao: DescricaoSectionProps;
  anexos: AnexosSectionProps;
  checklists: ChecklistsSectionProps;
  slots?: GeralSubpageSlots;
}

export function GeralSubpage({ tags, descricao, anexos, checklists, slots }: GeralSubpageProps) {
  return (
    <>
      {/* Etiquetas — only when set. An empty heading on every card would be
          furniture that means nothing. */}
      {tags.length > 0 && (
        <div className="mb-4" data-testid="etiquetas-chips">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Etiquetas
          </p>
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <span
                key={tag.id}
                className="rounded px-2.5 py-1 text-xs font-medium text-white"
                style={{ backgroundColor: tag.cor }}
                data-testid={`etiqueta-chip-${tag.id}`}
              >
                {tag.nome}
              </span>
            ))}
          </div>
        </div>
      )}

      {slots?.afterTags}

      <DescricaoSection {...descricao} />

      {slots?.afterDescricao}

      {slots?.beforeAnexos}

      <AnexosSection {...anexos} />

      {/* The user-created working checklists — last, and only when there are
          any. */}
      <ChecklistsSection {...checklists} />
    </>
  );
}
