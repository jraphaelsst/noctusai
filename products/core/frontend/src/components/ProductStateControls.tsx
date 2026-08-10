/**
 * Shared controls for the product WORKING GUIDE — the two axes that tell the
 * team which products to touch, and where.
 *
 *     ativo + live → work it in PROD
 *     ativo + dev  → work it in DEV only
 *     inativo      → do not touch the product at all
 *
 * These live in one module because THREE surfaces render them (the admin
 * products table, the centralized control panel, and the dashboard cards).
 * If each surface hand-rolled its own toggle, the transition rules would drift
 * between them — and a guide that disagrees with itself is worse than none.
 *
 * The components are presentational + callback-driven on purpose: each host
 * page owns its own data fetching (the admin table uses local state, the panel
 * refetches a list), so the shared piece is the RULES and the affordance, not
 * a data layer none of them share.
 */
import React, { useEffect, useRef, useState } from 'react';
import { Check, Pencil } from 'lucide-react';

export type DeployScope = 'live' | 'dev';

// ---------------------------------------------------------------------------
// Bucketing — the three working states, defined ONCE
// ---------------------------------------------------------------------------

export type Bucket = 'prod' | 'dev' | 'ignore';

/** Minimal shape needed to bucket a row — both the control board and the
 *  catalog table pass their own richer Product type, which structurally
 *  satisfies this. */
export interface BucketableProduct {
  ativo: boolean;
  deploy_scope: DeployScope;
}

/** The single definition of "which bucket is this product in?".
 *
 *  Lives here rather than in either page because BOTH the control board and
 *  the catalog table group by it. Two copies of this function is precisely how
 *  the two screens would start disagreeing about what "in production" means. */
export function bucketOf(p: BucketableProduct): Bucket {
  if (!p.ativo) return 'ignore';
  return p.deploy_scope === 'live' ? 'prod' : 'dev';
}

export const BUCKETS: {
  key: Bucket;
  title: string;
  rule: string;
  /** Border tone for the control board's card sections. */
  tone: string;
  /** Row tint + accent for the catalog table's section header rows. */
  headerTone: string;
}[] = [
  {
    key: 'prod',
    title: 'Producao',
    rule: 'Ativo + LIVE — validamos em dev e promovemos para prod.',
    tone: 'border-success/40',
    headerTone: 'bg-success/10 text-success',
  },
  {
    key: 'dev',
    title: 'Desenvolvimento',
    rule: 'Ativo + DEV — trabalhamos e publicamos apenas em dev; nao chega em prod.',
    tone: 'border-warning/40',
    headerTone: 'bg-warning-light text-warning-foreground',
  },
  {
    key: 'ignore',
    title: 'Ignorados',
    rule: 'Inativo — nao tocamos no codigo deste produto.',
    tone: 'border-border',
    headerTone: 'bg-muted text-muted-foreground',
  },
];

/** The curated palette the colour popover offers. Free-form hex stays
 *  available underneath — these are the fast path, not a restriction. */
export const PRODUCT_COLORS: { hex: string; label: string }[] = [
  { hex: '#6366f1', label: 'Indigo' },
  { hex: '#8b5cf6', label: 'Violeta' },
  { hex: '#3b82f6', label: 'Azul' },
  { hex: '#0ea5e9', label: 'Ceu' },
  { hex: '#14b8a6', label: 'Teal' },
  { hex: '#10b981', label: 'Verde' },
  { hex: '#84cc16', label: 'Lima' },
  { hex: '#f59e0b', label: 'Ambar' },
  { hex: '#f97316', label: 'Laranja' },
  { hex: '#ef4444', label: 'Vermelho' },
  { hex: '#ec4899', label: 'Rosa' },
  { hex: '#64748b', label: 'Cinza' },
];

// ---------------------------------------------------------------------------
// Status (ativo / inativo)
// ---------------------------------------------------------------------------

export function StatusToggle({
  ativo,
  deployScope,
  onToggle,
  busy = false,
  size = 'sm',
}: {
  ativo: boolean;
  deployScope: DeployScope;
  onToggle: (next: boolean) => void;
  busy?: boolean;
  size?: 'sm' | 'xs';
}) {
  const pad = size === 'xs' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs';

  function handleClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (busy) return;
    if (ativo) {
      // Deactivating is the consequential direction, and when the product is
      // LIVE it also silently demotes the scope. Say so BEFORE it happens —
      // a surprise demotion is exactly the kind of thing that erodes trust in
      // the guide.
      const extra =
        deployScope === 'live'
          ? '\n\nEste produto esta LIVE. Ele sera movido para DEV antes de ser desativado (um produto inativo nunca pode estar live).'
          : '';
      if (!confirm(`Desativar este produto?${extra}`)) return;
    }
    onToggle(!ativo);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      title={
        ativo
          ? 'Ativo — clique para desativar (o produto passa a ser ignorado)'
          : 'Inativo — clique para reativar (volta sempre em DEV)'
      }
      className={`inline-flex items-center rounded-full font-medium transition-colors disabled:opacity-50 ${pad} ${
        ativo
          ? 'bg-success/10 text-success hover:bg-success/20'
          : 'bg-danger/10 text-danger hover:bg-danger/20'
      }`}
    >
      {ativo ? 'Ativo' : 'Inativo'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Deploy scope (live / dev)
// ---------------------------------------------------------------------------

export function DeployScopeToggle({
  ativo,
  deployScope,
  onToggle,
  busy = false,
}: {
  ativo: boolean;
  deployScope: DeployScope;
  onToggle: (next: DeployScope) => void;
  busy?: boolean;
}) {
  // An inactive product has no working scope — it is one we have agreed not to
  // touch. Disabling here mirrors the server's 409 so the UI never offers an
  // action the API will refuse.
  const disabled = busy || !ativo;
  const live = deployScope === 'live';

  return (
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        if (disabled) return;
        onToggle(live ? 'dev' : 'live');
      }}
      disabled={disabled}
      title={
        !ativo
          ? 'Produto inativo nao pode ter escopo de trabalho — ative-o primeiro'
          : live
            ? 'LIVE — trabalhamos este produto em producao. Clique para mover para DEV'
            : 'DEV — trabalhamos este produto apenas em dev. Clique para promover a LIVE'
      }
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide transition-colors ${
        !ativo
          ? 'bg-muted text-muted-foreground cursor-not-allowed opacity-60'
          : live
            ? 'bg-success/10 text-success hover:bg-success/20'
            : 'bg-warning-light text-warning-foreground hover:bg-warning-light/80'
      }`}
    >
      {live ? 'live' : 'dev'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Colour picker popover
// ---------------------------------------------------------------------------

export function ColorPickerButton({
  cor,
  onPick,
  busy = false,
}: {
  cor: string;
  onPick: (hex: string) => void;
  busy?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape. Without this the popover survives a click
  // on another row and the operator edits the colour of a product they are no
  // longer looking at.
  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="relative inline-block" ref={ref} onClick={e => e.stopPropagation()}>
      <button
        type="button"
        onClick={() => !busy && setOpen(o => !o)}
        disabled={busy}
        title={`Cor ${cor} — clique para alterar`}
        className="inline-flex items-center justify-center w-6 h-6 rounded-full border border-border hover:ring-2 hover:ring-primary/40 transition-all disabled:opacity-50"
      >
        <span
          className="inline-block w-3.5 h-3.5 rounded-full"
          style={{ backgroundColor: cor }}
        />
      </button>

      {open && (
        <div className="absolute z-50 mt-2 left-0 w-52 rounded-lg border border-border bg-card p-3 shadow-lg">
          <p className="text-xs font-medium text-foreground mb-2">Cor do produto</p>
          <div className="grid grid-cols-6 gap-1.5">
            {PRODUCT_COLORS.map(c => (
              <button
                key={c.hex}
                type="button"
                title={c.label}
                onClick={() => {
                  onPick(c.hex);
                  setOpen(false);
                }}
                className="relative w-6 h-6 rounded-full border border-border/50 hover:scale-110 transition-transform"
                style={{ backgroundColor: c.hex }}
              >
                {c.hex.toLowerCase() === (cor || '').toLowerCase() && (
                  <Check className="absolute inset-0 m-auto w-3.5 h-3.5 text-white drop-shadow" />
                )}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-3 pt-3 border-t border-border">
            <input
              type="color"
              value={cor || '#6366f1'}
              onChange={e => onPick(e.target.value)}
              className="w-8 h-7 p-0 border-none cursor-pointer rounded bg-transparent"
              title="Cor personalizada"
            />
            <span className="text-xs text-muted-foreground font-mono">{cor}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Edit affordance — icon, not a text button
// ---------------------------------------------------------------------------

export function EditIconButton({ onClick, label = 'Editar produto' }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={e => {
        e.stopPropagation();
        onClick();
      }}
      className="inline-flex items-center justify-center w-7 h-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
    >
      <Pencil className="w-3.5 h-3.5" />
    </button>
  );
}
