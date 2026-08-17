/**
 * Primitivos de UI (shadcn-like enxuto, ~um arquivo). O protótipo instalou 47
 * componentes shadcn e usou uns cinco; aqui vale o mesmo resultado visual sem
 * o peso. Na absorção pela plataforma NoctusAI, trocar por `@noctusai/lib`.
 */
import { forwardRef, useEffect, type ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { CLASSES_STATUS, type TomStatus } from "@/lib/status";

// ── Button ──────────────────────────────────────────────────────────────
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-border bg-card text-foreground hover:bg-accent",
        ghost: "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 px-3 text-xs",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, children, disabled, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
);
Button.displayName = "Button";

// ── Inputs ──────────────────────────────────────────────────────────────
const inputClass =
  "h-9 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(inputClass, className)} {...props} />
);
Input.displayName = "Input";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea ref={ref} className={cn(inputClass, "h-20 py-2", className)} {...props} />
));
Textarea.displayName = "Textarea";

export const Select = forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn(inputClass, className)} {...props}>
      {children}
    </select>
  )
);
Select.displayName = "Select";

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <label className={cn("mb-1 block text-xs font-medium text-muted-foreground", className)}>
      {children}
    </label>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

/** Caixa de seleção com rótulo à direita — usada no checklist e nos filtros. */
export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-input accent-[oklch(var(--primary))]"
      />
      {label}
    </label>
  );
}

// ── Card ────────────────────────────────────────────────────────────────
export function Card({
  children,
  className,
  onClick,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "rounded-xl border border-border bg-card p-4 shadow-sm",
        onClick && "cursor-pointer transition hover:border-primary/40 hover:shadow-md",
        className
      )}
    >
      {children}
    </div>
  );
}

/** Cartão de KPI — o ritmo visual do dashboard e do financeiro. */
export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-muted-foreground">
        <span className="text-[11px] uppercase tracking-wider">{label}</span>
        {icon}
      </div>
      <div className="font-display text-2xl md:text-3xl">{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </Card>
  );
}

// ── Badge ───────────────────────────────────────────────────────────────
export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium",
        "border-border bg-muted text-muted-foreground",
        className
      )}
    >
      {children}
    </span>
  );
}

/** Badge pintada pelo sistema de status por cor. */
export function StatusBadge({
  tom,
  children,
  className,
}: {
  tom: TomStatus;
  children: ReactNode;
  className?: string;
}) {
  return <Badge className={cn(CLASSES_STATUS[tom], className)}>{children}</Badge>;
}

// ── Modal ───────────────────────────────────────────────────────────────
export function Modal({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-foreground/40 p-4 py-10"
      onClick={onClose}
    >
      <div
        className={cn("w-full rounded-xl border border-border bg-card p-5 shadow-xl", wide ? "max-w-3xl" : "max-w-md")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-display text-lg">{title}</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ── Estados ─────────────────────────────────────────────────────────────
export function Spinner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center py-12", className)}>
      <Loader2 className="h-6 w-6 animate-spin text-primary" />
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-card/50 py-10 text-center text-sm text-muted-foreground">
      {children}
    </div>
  );
}

export function ErroBox({ erro }: { erro: unknown }) {
  const mensagem = erro instanceof Error ? erro.message : String(erro ?? "Erro desconhecido");
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      {mensagem}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-2xl md:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

// ── Tabela ──────────────────────────────────────────────────────────────
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <Card className={cn("overflow-hidden p-0", className)}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">{children}</table>
      </div>
    </Card>
  );
}

export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th className={cn("px-4 py-3 text-left font-medium", className)}>{children}</th>;
}

export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cn("px-4 py-3", className)}>{children}</td>;
}

export function THead({ children }: { children: ReactNode }) {
  return (
    <thead className="bg-muted/50 text-[11px] uppercase tracking-wider text-muted-foreground">
      {children}
    </thead>
  );
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-border">{children}</tbody>;
}

/** Exclusão em dois toques — sem `window.confirm`, que o teste não alcança. */
export function BotaoExcluir({
  confirmando,
  onPedirConfirmacao,
  onConfirmar,
  titulo = "Excluir",
}: {
  confirmando: boolean;
  onPedirConfirmacao: () => void;
  onConfirmar: () => void;
  titulo?: string;
}) {
  if (confirmando)
    return (
      <Button variant="destructive" size="sm" onClick={onConfirmar}>
        Confirmar?
      </Button>
    );
  return (
    <Button variant="ghost" size="icon" title={titulo} onClick={onPedirConfirmacao}>
      <TrashIcon />
    </Button>
  );
}

function TrashIcon() {
  return (
    <svg
      className="h-4 w-4 text-destructive"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6" />
    </svg>
  );
}
