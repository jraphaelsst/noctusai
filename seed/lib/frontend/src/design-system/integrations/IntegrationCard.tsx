/**
 * `<IntegrationCard/>` — config-driven card for a single provider integration account.
 *
 * Driven entirely by a `ProviderCardConfig` (from the registry) + an
 * `IntegrationAccount` data object. All data-fetching lives in the consuming
 * product; the card is purely presentational + interaction shell.
 *
 * States rendered:
 *   - loading: skeleton shimmer
 *   - error:   inline destructive callout
 *   - empty:   not applicable (the card renders ONE account)
 *   - success: full card with icon / label / secondary fields / badge / actions
 *
 * Interaction:
 *   - Card body click → `onOpenModal(account)` (unless click is on a control).
 *     The consumer decides what this means — e.g. opening the detail modal,
 *     or (per `ProviderCardConfig.dashboardRoute`) deep-linking into the
 *     provider's own dashboard with the account pre-selected.
 *   - Details icon (only rendered when `onOpenDetails` is passed) →
 *     `onOpenDetails(account)` — a secondary affordance so the read-only
 *     detail modal stays reachable even when `onOpenModal` is repurposed
 *     for navigation.
 *   - Pencil icon → toggles inline-edit mode (renders editableFields as inputs).
 *   - Save → calls `onSave(patch)` then exits edit mode.
 *   - Cancel → exits edit mode, discards draft.
 *   - Actions menu: sync/re-validate · delete.
 *   - `busy` prop → disables all controls + shows spinner overlay.
 *
 * There is no "set as default" concept here. `IntegrationAccount.is_default`
 * still exists on the BE contract, but the card never reads it — no badge, no
 * label, no menu action. Every live provider (gmail, meta, n8n, youtube) has
 * never had more than one account per client, so a UI concept for picking
 * "the default one" never had a real second option to distinguish it from;
 * it only produced a placeholder the user had to swap away from to see real
 * data. `PATCH .../set-default` still exists server-side (now unreached from
 * this organ) — see `useSetDefaultAccount` in the social-wiring product.
 *
 * The organ MUST NOT import from any `products/` path.
 */
import * as React from "react";
import {
  Pencil,
  X,
  Check,
  Trash2,
  RefreshCw,
  MoreHorizontal,
  AlertCircle,
  Loader2,
  Settings2,
} from "lucide-react";

import { cn } from "../../utils";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import type {
  IntegrationAccount,
  IntegrationAccountPatch,
  IntegrationStatus,
} from "./types";
import type { ProviderCardConfig } from "./providerCardConfig";
import { getProviderConfig } from "./providerCardConfig";

// ── Status badge ────────────────────────────────────────────────────────────

interface StatusBadgeConfig {
  label: string;
  className: string;
  showSpinner: boolean;
}

export function resolveStatusBadge(status: IntegrationStatus): StatusBadgeConfig {
  switch (status) {
    case "validated":
      return {
        label: "Validado",
        className:
          "border-transparent bg-primary text-primary-foreground",
        showSpinner: false,
      };
    case "validating":
      return {
        label: "Validando",
        className: "border-muted-foreground/30 bg-muted text-muted-foreground",
        showSpinner: true,
      };
    case "wiring":
      return {
        label: "Conectando",
        className: "border-muted-foreground/30 bg-muted text-muted-foreground",
        showSpinner: true,
      };
    case "error":
      return {
        label: "Erro",
        className:
          "border-transparent bg-destructive text-destructive-foreground",
        showSpinner: false,
      };
    case "disconnected":
      return {
        label: "Desconectado",
        className: "border border-muted-foreground/40 text-muted-foreground bg-transparent",
        showSpinner: false,
      };
    default:
      return {
        label: status,
        className: "border border-muted-foreground/40 text-muted-foreground bg-transparent",
        showSpinner: false,
      };
  }
}

function StatusBadge({ status }: { status: IntegrationStatus }) {
  const { label, className, showSpinner } = resolveStatusBadge(status);
  return (
    <Badge className={className}>
      {showSpinner && (
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      )}
      {label}
    </Badge>
  );
}

// ── Actions menu ────────────────────────────────────────────────────────────

interface ActionsMenuProps {
  account: IntegrationAccount;
  busy: boolean;
  onSync?: (account: IntegrationAccount) => void;
  onDelete?: (account: IntegrationAccount) => void;
}

function ActionsMenu({
  account,
  busy,
  onSync,
  onDelete,
}: ActionsMenuProps) {
  const [open, setOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  // Close on outside click
  React.useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div className="relative" ref={menuRef}>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Mais ações"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={busy}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <MoreHorizontal className="h-4 w-4" />
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-1 min-w-[160px] rounded-md border border-border bg-background py-1 shadow-md"
        >
          {onSync && (
            <button
              role="menuitem"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onSync(account);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-sm hover:bg-accent"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Sincronizar / Revalidar
            </button>
          )}
          {onDelete && (
            <button
              role="menuitem"
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onDelete(account);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Remover
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Edit form ───────────────────────────────────────────────────────────────

interface EditFormProps {
  account: IntegrationAccount;
  config: ProviderCardConfig;
  busy: boolean;
  onSave: (patch: IntegrationAccountPatch) => void;
  onCancel: () => void;
}

function EditForm({ account, config, busy, onSave, onCancel }: EditFormProps) {
  const [draft, setDraft] = React.useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const f of config.editableFields) {
      if (f.bag === "root") {
        init[f.key] = String((account as unknown as Record<string, unknown>)[f.key] ?? "");
      } else if (f.bag === "channel_info") {
        init[f.key] = String(account.channel_info[f.key] ?? "");
      } else {
        init[f.key] = String(account.metadata[f.key] ?? "");
      }
    }
    return init;
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const patch: IntegrationAccountPatch = {};
    for (const f of config.editableFields) {
      (patch as Record<string, string | null>)[f.key] =
        draft[f.key] ?? null;
    }
    onSave(patch);
  }

  return (
    <form
      onSubmit={handleSubmit}
      onClick={(e) => e.stopPropagation()}
      className="space-y-2 pt-1"
    >
      {config.editableFields.map((field) => (
        <div key={field.key} className="flex flex-col gap-0.5">
          <label
            htmlFor={`ic-edit-${account.id}-${field.key}`}
            className="text-xs font-medium text-muted-foreground"
          >
            {field.label}
          </label>
          <Input
            id={`ic-edit-${account.id}-${field.key}`}
            type={field.inputType ?? "text"}
            placeholder={field.placeholder}
            disabled={busy}
            value={draft[field.key] ?? ""}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))
            }
          />
        </div>
      ))}

      <div className="flex items-center gap-2 pt-1">
        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={busy}
          aria-label="Salvar"
        >
          {busy ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Check className="h-3 w-3" />
          )}
          Salvar
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={onCancel}
        >
          <X className="h-3 w-3" />
          Cancelar
        </Button>
      </div>
    </form>
  );
}

// ── IntegrationCard ─────────────────────────────────────────────────────────

export interface IntegrationCardProps {
  /** The account data to display. */
  account: IntegrationAccount;
  /**
   * Override the config to use. When omitted, the registry is consulted
   * via `getProviderConfig(account.provider)`.
   */
  config?: ProviderCardConfig;
  /** Loading state — renders a skeleton. */
  isLoading?: boolean;
  /** Error state — renders an inline error block. */
  error?: Error | null;
  /**
   * When true, all interactive controls are disabled and a spinner
   * overlay indicates a mutation is in-flight.
   */
  busy?: boolean;
  /**
   * Called when the user clicks the card body. Historically this opened the
   * detail modal; consumers MAY repurpose it (e.g. deep-link navigation) —
   * when they do, pass `onOpenDetails` too so the detail modal stays
   * reachable via the secondary affordance below.
   */
  onOpenModal?: (account: IntegrationAccount) => void;
  /**
   * Called when the user clicks the secondary "details" icon-button.
   * Renders a small gear icon next to the edit pencil / actions menu.
   * Use this to keep the read-only detail modal reachable when
   * `onOpenModal` has been repurposed for something else (e.g. navigation).
   */
  onOpenDetails?: (account: IntegrationAccount) => void;
  /** Called with the patch payload when the user saves the inline-edit form. */
  onSave?: (patch: IntegrationAccountPatch) => void;
  /** Called when the user triggers the delete action. */
  onDelete?: (account: IntegrationAccount) => void;
  /** Called when the user triggers the sync/re-validate action. */
  onSync?: (account: IntegrationAccount) => void;
  /** Optional extra className applied to the wrapper. */
  className?: string;
}

export function IntegrationCard({
  account,
  config: configProp,
  isLoading = false,
  error = null,
  busy = false,
  onOpenModal,
  onOpenDetails,
  onSave,
  onDelete,
  onSync,
  className = "",
}: IntegrationCardProps) {
  const [editMode, setEditMode] = React.useState(false);

  const config: ProviderCardConfig | undefined =
    configProp ?? getProviderConfig(account.provider);

  const Icon = config?.icon;
  const primaryLabel = config ? config.primary(account) : account.account_label;
  const secondaryFields = config ? config.secondary(account) : [];

  // ── Loading skeleton ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div
        className={cn(
          "rounded-lg border border-border bg-card p-4 shadow-sm",
          className,
        )}
        aria-busy="true"
        aria-label="Carregando conta de integração"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 animate-pulse rounded-full bg-muted" />
            <div className="space-y-1.5">
              <div className="h-4 w-32 animate-pulse rounded bg-muted" />
              <div className="h-3 w-20 animate-pulse rounded bg-muted" />
            </div>
          </div>
          <div className="h-5 w-16 animate-pulse rounded-full bg-muted" />
        </div>
        <div className="mt-3 flex gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="space-y-1">
              <div className="h-3 w-12 animate-pulse rounded bg-muted" />
              <div className="h-3 w-8 animate-pulse rounded bg-muted" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        role="alert"
        className={cn(
          "inline-flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive",
          className,
        )}
      >
        <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{error.message || "Não foi possível carregar esta integração."}</span>
      </div>
    );
  }

  // ── Success ─────────────────────────────────────────────────────────────
  return (
    <div
      role="article"
      aria-label={`Conta ${primaryLabel}`}
      onClick={() => {
        if (!editMode && !busy && onOpenModal) onOpenModal(account);
      }}
      className={cn(
        "relative rounded-lg border border-border bg-card p-4 shadow-sm transition-colors",
        !editMode && onOpenModal && !busy
          ? "cursor-pointer hover:border-primary/50 hover:bg-accent/30"
          : "",
        className,
      )}
    >
      {/* Busy overlay */}
      {busy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-background/60">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-label="Processando..." />
        </div>
      )}

      {/* Card header */}
      <div className="flex items-start justify-between gap-3">
        {/* Provider icon + label */}
        <div className="flex min-w-0 items-center gap-3">
          {Icon && (
            <span
              className={cn(
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted",
                config?.accent,
              )}
              aria-hidden="true"
            >
              <Icon className="h-5 w-5" />
            </span>
          )}

          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <p className="truncate text-sm font-semibold text-foreground">
                {primaryLabel}
              </p>
            </div>
            {config && (
              <p className="text-xs text-muted-foreground">{config.displayName}</p>
            )}
          </div>
        </div>

        {/* Status badge + controls */}
        <div
          className="flex shrink-0 items-center gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          <StatusBadge status={account.status} />

          {/* Details toggle — secondary affordance for the read-only detail
              modal, kept reachable even when onOpenModal is repurposed. */}
          {onOpenDetails && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Ver detalhes"
              disabled={busy}
              onClick={() => onOpenDetails(account)}
              className="text-muted-foreground"
            >
              <Settings2 className="h-3.5 w-3.5" />
            </Button>
          )}

          {/* Edit toggle */}
          {onSave && config && config.editableFields.length > 0 && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={editMode ? "Cancelar edição" : "Editar conta"}
              disabled={busy}
              onClick={() => setEditMode((v) => !v)}
              className={cn(
                editMode ? "text-primary" : "text-muted-foreground",
              )}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
          )}

          {/* Actions menu */}
          <ActionsMenu
            account={account}
            busy={busy}
            onSync={onSync}
            onDelete={onDelete}
          />
        </div>
      </div>

      {/* Secondary fields */}
      {secondaryFields.length > 0 && !editMode && (
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5">
          {secondaryFields.map((f) => (
            <div key={f.label} className="flex flex-col">
              <dt className="text-xs text-muted-foreground">{f.label}</dt>
              <dd className="text-xs font-medium text-foreground">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* Inline-edit form */}
      {editMode && config && onSave && (
        <EditForm
          account={account}
          config={config}
          busy={busy}
          onSave={(patch) => {
            onSave(patch);
            setEditMode(false);
          }}
          onCancel={() => setEditMode(false)}
        />
      )}
    </div>
  );
}

export default IntegrationCard;
