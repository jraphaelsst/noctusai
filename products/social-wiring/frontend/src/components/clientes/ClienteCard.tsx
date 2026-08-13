/**
 * ClienteCard — one card per human on the Clientes board.
 *
 * No canonical organ matched this shape (`noctus.dev.find_reusable_component`
 * — closest hits were `FilterBar`/`ChartCard`/`KanbanBoard`, all shelfware
 * and none a card-face). Phase 2.1 of the roadmap explicitly extracts "the
 * card face (colour strip, badge row)" into `@noctusai/lib` — this is the
 * ad-hoc, pre-extraction version Phase 1's checkpoint only needs ("the
 * board shows one card per human"). Built local per the
 * `noc-organ-consume-check` skill's Step-4 guidance for a no-match intent.
 */
import { Mail, Phone, RotateCcw, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@noctusai/lib";
import { formatCountOrDash, type Cliente } from "@/hooks/useClientes";

export interface ClienteCardProps {
  cliente: Cliente;
  onRestore: (cliente: Cliente) => void;
  restoring: boolean;
}

export function ClienteCard({ cliente, onRestore, restoring }: ClienteCardProps) {
  return (
    <Card
      data-testid="cliente-card"
      className={`h-full ${!cliente.ativo ? "opacity-80" : ""}`}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="line-clamp-2 text-sm font-semibold leading-snug">{cliente.nome}</p>
          {!cliente.ativo && (
            <Badge variant="secondary" data-testid="cliente-inativo-badge">
              Inativo
            </Badge>
          )}
        </div>

        {/* The 399 keyless people (PROJECT.md §2) must never silently read
            as a confirmed identity — this badge is the visible flag. */}
        {cliente.identidade_incerta && (
          <Badge
            variant="outline"
            className="border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
            data-testid="cliente-identidade-incerta-badge"
          >
            <ShieldAlert className="mr-1 h-3 w-3" />
            Identidade incerta
          </Badge>
        )}

        {cliente.chave_canonica ? (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {cliente.chave_tipo === "email" ? (
              <Mail className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <Phone className="h-3.5 w-3.5 shrink-0" />
            )}
            <span className="truncate">{cliente.chave_canonica}</span>
          </p>
        ) : (
          <p className="text-xs italic text-muted-foreground">Sem contato identificado</p>
        )}

        <div className="flex flex-wrap gap-3 pt-1 text-xs text-muted-foreground">
          <span>{formatCountOrDash(cliente.touch_count)} toques</span>
          <span>{formatCountOrDash(cliente.negociacoes_abertas)} negociações</span>
        </div>

        <p className="text-xs text-muted-foreground">
          Último contato: {formatDate(cliente.ultimo_contato_em)}
        </p>

        {!cliente.ativo && (
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={restoring}
            onClick={() => onRestore(cliente)}
            data-testid="cliente-restaurar-btn"
          >
            <RotateCcw className="mr-2 h-3.5 w-3.5" />
            {restoring ? "Restaurando…" : "Restaurar"}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
