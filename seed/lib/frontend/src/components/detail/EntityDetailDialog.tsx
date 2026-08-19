/**
 * `<EntityDetailDialog/>` — THE one record-detail modal for the platform.
 *
 * WHY THIS IS AN ORGAN AND NOT A PAGE COMPONENT
 * ---------------------------------------------
 * "Show me everything about this one record" is the same interaction on
 * every surface that lists records: a table row, a kanban card, a search
 * result, a chart drill-in. Before this organ, social-wiring's Leads table
 * had a bespoke `LeadDetailDrawer` and the Funil board had no detail view
 * at all — it deep-linked BACK to the table, which is the UI equivalent of
 * "go look it up yourself".
 *
 * Building it per-surface guarantees drift: add a field to the record and
 * you must remember every place that renders it. Here the LAYOUT lives in
 * one component and the CONTENT is a descriptor the consumer builds once
 * per entity — so a new field is one edit, visible everywhere at once.
 *
 * WHAT BELONGS HERE vs. IN THE CONSUMER
 * -------------------------------------
 * Here: the modal chrome, the field grid, loading / error / not-found
 * states, footer action layout, scroll and escape behaviour.
 * In the consumer: which fields exist, what they're called, how each value
 * renders, and what the actions DO. This organ is purely presentational —
 * it fires callbacks and never mutates, exactly like `IntegrationCard`.
 *
 * ASYNC BY DESIGN
 * ---------------
 * Some surfaces already hold the whole record (a table row); others hold
 * only a projection (a kanban card carries 8 of a lead's 25 columns) and
 * must fetch the rest on open. `isLoading` covers the second case so the
 * consumer does not hand-roll a skeleton per surface — and so a card click
 * never renders a half-empty record as if those fields were blank.
 *
 * Usage:
 * ```tsx
 * <EntityDetailDialog
 *   open={!!selected}
 *   onClose={() => setSelected(null)}
 *   title={lead.cliente_nome ?? 'Lead sem nome'}
 *   badges={lead.needs_review ? [{ label: 'Revisar', variant: 'destructive' }] : []}
 *   note={lead.needs_review ? explainNeedsReview(lead) : undefined}
 *   sections={leadDetailSections(lead)}
 *   actions={[
 *     { label: 'Excluir', variant: 'destructive', align: 'start', onClick: () => remove(lead) },
 *     { label: 'Editar', variant: 'primary', onClick: () => edit(lead) },
 *   ]}
 * />
 * ```
 */
import * as React from 'react';

import { Badge } from '../../design-system/ui/Badge';
import type { BadgeVariant } from '../../design-system/ui/Badge';
import { Button } from '../../design-system/ui/Button';
import type { ButtonVariant } from '../../design-system/ui/Button';
import { Dialog, DialogBody, DialogFooter, DialogHeader } from '../../design-system/ui/Dialog';
import { cn } from '../../utils';

/** One label/value pair in the detail grid. */
export interface DetailField {
  label: string;
  /**
   * Anything renderable. `null`/`undefined`/`''` render the em-dash
   * placeholder rather than collapsing the row — a visibly empty field
   * tells the user we hold no value; a missing row tells them nothing.
   */
  value?: React.ReactNode;
  /** Span both grid columns. Use for long text (observações, notes). */
  wide?: boolean;
  /**
   * Drop the field entirely. For fields that do not APPLY to this record
   * (a campaign lead has no `corretor`), as distinct from a field that
   * applies but is empty — which should render as an em-dash.
   */
  hidden?: boolean;
}

/** A titled group of fields. A section with no visible fields is dropped. */
export interface DetailSection {
  /** Omit for the primary section — it renders without a heading. */
  title?: string;
  fields: DetailField[];
}

export interface DetailAction {
  label: string;
  onClick: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  icon?: React.ReactNode;
  /** Pushes this action to the left of the footer (destructive convention). */
  align?: 'start' | 'end';
  testId?: string;
}

export interface EntityDetailBadge {
  label: string;
  variant?: BadgeVariant;
}

export interface EntityDetailDialogProps {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  /** Secondary line under the title — a subtitle, id, or origin label. */
  subtitle?: React.ReactNode;
  /** Chips beside the title (status, flags). */
  badges?: EntityDetailBadge[];
  /**
   * An explanatory line under the header. Born from the Leads drawer's
   * `needs_review` reason: a flag the user cannot interpret is a flag she
   * cannot act on, so the surface that raises one explains it.
   */
  note?: React.ReactNode;
  sections?: DetailSection[];
  actions?: DetailAction[];
  /** The record is still being fetched — renders a skeleton grid. */
  isLoading?: boolean;
  /** Fetch failed. Takes precedence over `isLoading` and `sections`. */
  error?: React.ReactNode;
  /** Fetch succeeded but the record is gone (deleted under us, bad id). */
  notFound?: boolean;
  /** Extra content between the field grid and the footer. */
  children?: React.ReactNode;
  className?: string;
  testId?: string;
}

function FieldRow({ field }: { field: DetailField }) {
  const isEmpty =
    field.value === null || field.value === undefined || field.value === '';
  return (
    <div className={cn('min-w-0', field.wide && 'col-span-2')}>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {field.label}
      </dt>
      {/* break-words, not overflow: a long email or code must wrap inside
          the panel rather than push a horizontal scrollbar onto the modal. */}
      <dd className="mt-0.5 break-words text-sm">
        {isEmpty ? <span className="text-muted-foreground">—</span> : field.value}
      </dd>
    </div>
  );
}

/**
 * The label/value grid, on its own — the SAME renderer the dialog uses.
 *
 * Extracted 2026-08-19 so a surface that is not a dialog can show a record's
 * fields without re-implementing them. social-wiring's lead card needed the
 * lead's own data inline; copying the grid would have meant the card and the
 * detail dialog drifting apart field by field, which is precisely what
 * `leadDetailSections` exists to prevent one level up
 * (`KB § PATTERNS/architect/products-consume-canonical-organs.md`).
 *
 * Sections whose every field is `hidden` are dropped rather than rendered as a
 * bare heading over nothing — a heading with no rows reads as "this data failed
 * to load", which is a different and alarming claim.
 */
export function DetailSections({
  sections,
  className,
  testId = 'detail-sections',
}: {
  sections?: DetailSection[];
  className?: string;
  testId?: string;
}) {
  const visible = React.useMemo(
    () =>
      (sections ?? [])
        .map((s) => ({ ...s, fields: s.fields.filter((f) => !f.hidden) }))
        .filter((s) => s.fields.length > 0),
    [sections],
  );

  if (visible.length === 0) return null;

  return (
    <div className={className} data-testid={testId}>
      {visible.map((section, i) => (
        <div key={section.title ?? `section-${i}`} className={i > 0 ? 'mt-5' : undefined}>
          {section.title && (
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {section.title}
            </h3>
          )}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            {section.fields.map((field) => (
              <FieldRow key={field.label} field={field} />
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-4" data-testid="entity-detail-loading">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="space-y-1.5">
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
          <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

export function EntityDetailDialog({
  open,
  onClose,
  title,
  subtitle,
  badges,
  note,
  sections,
  actions,
  isLoading,
  error,
  notFound,
  children,
  className,
  testId = 'entity-detail-dialog',
}: EntityDetailDialogProps) {
  const startActions = (actions ?? []).filter((a) => a.align === 'start');
  const endActions = (actions ?? []).filter((a) => a.align !== 'start');

  return (
    <Dialog
      open={open}
      onClose={onClose}
      className={cn('max-w-lg', className)}
      title={typeof title === 'string' ? title : undefined}
    >
      <div data-testid={testId}>
        <DialogHeader className="flex-col items-start gap-1">
          <div className="flex w-full flex-wrap items-center gap-2">
            <h2 className="min-w-0 flex-1 truncate text-lg font-semibold">{title}</h2>
            {badges?.map((b) => (
              <Badge key={b.label} variant={b.variant ?? 'default'}>
                {b.label}
              </Badge>
            ))}
          </div>
          {subtitle && (
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          )}
          {note && (
            <p className="text-xs text-muted-foreground" data-testid={`${testId}-note`}>
              {note}
            </p>
          )}
        </DialogHeader>

        <DialogBody>
          {error ? (
            <p className="text-sm text-destructive" data-testid={`${testId}-error`}>
              {error}
            </p>
          ) : isLoading ? (
            <SkeletonGrid />
          ) : notFound ? (
            <p className="text-sm text-muted-foreground" data-testid={`${testId}-not-found`}>
              Registro não encontrado.
            </p>
          ) : (
            <>
              <DetailSections sections={sections} testId={`${testId}-sections`} />
              {children}
            </>
          )}
        </DialogBody>

        {(startActions.length > 0 || endActions.length > 0) && (
          <DialogFooter className="justify-between gap-2">
            <div className="flex gap-2">
              {startActions.map((a) => (
                <ActionButton key={a.label} action={a} />
              ))}
            </div>
            <div className="flex gap-2">
              {endActions.map((a) => (
                <ActionButton key={a.label} action={a} />
              ))}
            </div>
          </DialogFooter>
        )}
      </div>
    </Dialog>
  );
}
EntityDetailDialog.displayName = 'EntityDetailDialog';

function ActionButton({ action }: { action: DetailAction }) {
  return (
    <Button
      variant={action.variant ?? 'outline'}
      size="sm"
      disabled={action.disabled}
      onClick={action.onClick}
      data-testid={action.testId}
    >
      {action.icon}
      {action.label}
    </Button>
  );
}
