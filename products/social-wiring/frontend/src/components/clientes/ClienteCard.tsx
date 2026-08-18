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
 *
 * Phase 2 (`lead-card-hub-p2-PROJECT.md` §4) wires this card's click target
 * — it had none — and layers the Trello-grade badge row on top via the new
 * `ClienteCardFace` (`components/card/**`, presentational). The colour
 * strip / due pill / description glyph / anexos / checklist badges render
 * only when `cliente.badges`/`cliente.tags` are present on the row this
 * page's list endpoint returns; see the ASSUMPTION note on `Cliente` in
 * `useClientes.ts` for the open question of whether P1's list endpoint
 * carries them yet.
 */
import { Mail, Phone, RotateCcw, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatDate } from "@noctusai/lib";
import { formatCountOrDash, type Cliente } from "@/hooks/useClientes";
import { ClienteCardFace } from "@/components/card/ClienteCardFace";

export interface ClienteCardProps {
  cliente: Cliente;
  onRestore: (cliente: Cliente) => void;
  restoring: boolean;
  /** Opens the Phase-2 detail dialog (`ClienteDetailModal`). Optional so
   *  existing P1 callers/tests that don't pass it keep working unchanged. */
  onOpen?: (cliente: Cliente) => void;
}

export function ClienteCard({ cliente, onRestore, restoring, onOpen }: ClienteCardProps) {
  return (
    <Card
      data-testid="cliente-card"
      className={`h-full ${!cliente.ativo ? "opacity-80" : ""} ${onOpen ? "cursor-pointer" : ""}`}
      onClick={onOpen ? () => onOpen(cliente) : undefined}
    >
      <CardContent className="space-y-3 p-4">
        {(cliente.badges || cliente.tags?.length) && (
          <ClienteCardFace
            nome={cliente.nome}
            corFaixa={cliente.tags?.[0]?.cor}
            datas={{
              data_entrega: cliente.data_entrega ?? null,
              entrega_concluida: cliente.entrega_concluida ?? false,
            }}
            badges={cliente.badges ?? null}
            className="border-none p-0"
            testId="cliente-card-face"
          />
        )}

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
            onClick={(e) => {
              // Never let the click bubble to the Card's onOpen — restoring
              // and opening the detail dialog are two different actions
              // living on the same click surface.
              e.stopPropagation();
              onRestore(cliente);
            }}
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
