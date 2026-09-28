/**
 * Perdidos — the archive of negócios marked as perdido (achado #10: the
 * board never shows a lost card again, and until now there was no way to
 * even SEE the archive, let alone reopen one). Reads the same
 * `GET /negocios?status=perdido` the seed's own docstring already
 * documented as endpoint-only; "Reabrir" calls the new
 * `POST /negocios/{id}/reabrir` (comercial_router.py — see its own
 * docstring for why it stays file-disjoint from comercial_funil.py).
 *
 * Filterable client-side (motivo, título) — the list is bounded by how many
 * deals an agency has actually lost, never a pagination concern in practice.
 */
import { useMemo, useState } from "react";
import { Archive, RotateCcw, Search } from "lucide-react";
import { Badge, Button, Input, Skeleton } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { SheetDialog } from "@/components/common/SheetDialog";
import { usePerdidos, useReabrirNegocio } from "@/hooks/useComercial";
import { describeError } from "@/lib/errors";
import { brl, dataBR } from "@/lib/format";
import type { Negocio } from "@/types/crm";

export interface PerdidosViewProps {
  open: boolean;
  onClose: () => void;
  /** Opens the reopened negócio's card once it lands back on the board. */
  onReaberto: (negocioId: string) => void;
}

export function PerdidosView({ open, onClose, onReaberto }: PerdidosViewProps) {
  const { perdidos, showSkeleton, isError, error } = usePerdidos();
  const reabrir = useReabrirNegocio();
  const [filtro, setFiltro] = useState("");

  const filtrados = useMemo(() => {
    const termo = filtro.trim().toLowerCase();
    if (!termo) return perdidos;
    return perdidos.filter((n) =>
      [n.titulo, n.motivo_perda, n.lead?.empresa, n.lead?.nome]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(termo)),
    );
  }, [perdidos, filtro]);

  return (
    <SheetDialog
      open={open}
      onClose={onClose}
      title="Perdidos"
      description="Negócios arquivados — saíram do funil com o motivo, a etapa e o tempo parado."
      testId="perdidos-view"
    >
      <div className="space-y-3 p-4 sm:p-6">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Buscar perdidos"
            className="h-10 pl-9"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            placeholder="Buscar por título, empresa ou motivo…"
          />
        </div>

        {showSkeleton ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError ? (
          <p role="alert" className="text-sm text-destructive">
            {describeError(error, "Não foi possível carregar os perdidos.")}
          </p>
        ) : filtrados.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            <Archive className="h-6 w-6" />
            {perdidos.length === 0 ? "Nenhum negócio perdido ainda." : "Nenhum perdido corresponde à busca."}
          </div>
        ) : (
          <ul className="space-y-2" data-testid="perdidos-lista">
            {filtrados.map((n) => (
              <PerdidoItem
                key={n.id}
                negocio={n}
                busy={reabrir.isPending && reabrir.variables === n.id}
                onReabrir={() =>
                  reabrir.mutate(n.id, {
                    onSuccess: () => {
                      toast.success("Negócio reaberto.");
                      onReaberto(n.id);
                    },
                    onError: (e) => toast.error(describeError(e, "Não foi possível reabrir o negócio.")),
                  })
                }
              />
            ))}
          </ul>
        )}
      </div>
    </SheetDialog>
  );
}

function PerdidoItem({
  negocio,
  busy,
  onReabrir,
}: {
  negocio: Negocio;
  busy: boolean;
  onReabrir: () => void;
}) {
  const titulo = negocio.lead?.empresa || negocio.lead?.nome || negocio.titulo;
  return (
    <li className="rounded-lg border border-border p-3" data-testid="perdido-item">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{titulo}</p>
          <p className="text-xs text-muted-foreground">
            {negocio.perdido_stage?.label ? `Perdido em ${negocio.perdido_stage.label}` : "Etapa removida"}
            {negocio.perdido_em ? ` · ${dataBR(negocio.perdido_em)}` : ""}
            {negocio.valor_estimado != null ? ` · ${brl(negocio.valor_estimado)}` : ""}
          </p>
        </div>
        <Badge variant="destructive">Perdido</Badge>
      </div>
      {negocio.motivo_perda ? (
        <p className="mt-2 text-sm text-foreground">{negocio.motivo_perda}</p>
      ) : null}
      <div className="mt-2 flex justify-end">
        <Button size="sm" variant="outline" disabled={busy} onClick={onReabrir}>
          <RotateCcw className="mr-1 h-4 w-4" /> {busy ? "Reabrindo…" : "Reabrir"}
        </Button>
      </div>
    </li>
  );
}
