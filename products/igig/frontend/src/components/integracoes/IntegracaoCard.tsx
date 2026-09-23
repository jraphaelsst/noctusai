/**
 * Shared chrome for the Integrações cards: a titled card with a status badge,
 * plus `CopyField` — a read-only URL with a "Copiar" button (webhook URLs
 * that get pasted into WAHA / the Meta app).
 */
import type { ReactNode } from "react";
import { Badge, Button, Skeleton } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Copy } from "lucide-react";
import { toast } from "sonner";

export function IntegracaoCard({
  titulo,
  icone,
  badge,
  descricao,
  showSkeleton,
  erro,
  children,
  testId,
}: {
  titulo: string;
  icone: ReactNode;
  badge?: { texto: string; variante: BadgeVariant } | null;
  descricao?: ReactNode;
  showSkeleton?: boolean;
  /** Load error — rendered instead of the body. */
  erro?: string | null;
  children?: ReactNode;
  testId?: string;
}) {
  return (
    <section className="min-w-0 space-y-3 rounded-lg border border-border bg-card p-4" data-testid={testId}>
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-muted-foreground">{icone}</span>
        <h2 className="text-sm font-semibold text-foreground">{titulo}</h2>
        {badge ? <Badge variant={badge.variante}>{badge.texto}</Badge> : null}
      </header>
      {descricao ? <div className="text-xs text-muted-foreground">{descricao}</div> : null}
      {showSkeleton ? (
        <Skeleton className="h-24 w-full" />
      ) : erro ? (
        <p role="alert" className="text-sm text-destructive">
          {erro}
        </p>
      ) : (
        children
      )}
    </section>
  );
}

export function CopyField({ label, valor }: { label: string; valor: string }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="flex min-w-0 items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded bg-muted px-2 py-2 text-xs text-foreground">{valor}</code>
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-10 w-10 shrink-0 sm:h-8 sm:w-8"
          aria-label={`Copiar ${label}`}
          onClick={() =>
            navigator.clipboard
              ?.writeText(valor)
              .then(() => toast.success("Copiado."))
              .catch(() => toast.error("Não foi possível copiar."))
          }
        >
          <Copy className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
