/**
 * `<QualificacaoCompletudePanel/>` — one party's contract qualification
 * completeness, contract automation F3 (migration 110).
 *
 * Self-contained, mirroring `CertidoesPartePanel`: the only required input is
 * `clienteId` — the panel's own query keys off it. Mounted via
 * `ClienteCardDialog`'s per-parte render prop (`renderQualificacaoDaParte`)
 * AND, once for the titular, thunked in from the "Dados do cliente" tab
 * (`renderQualificacaoDoTitular`) — the same lazy-child pattern
 * `CertidoesPartePanel`/`PessoaDocumentosPanel` already use, so a card with
 * three parties never fires four completude queries for panels nobody opened.
 *
 * Two states, honestly (`KB § PATTERNS/frontend/lying-loading-state.md`):
 * `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`
 * (an indicator only — the panel stays mounted through a background refetch).
 *
 * `completude_contratual` is a STRICTER, SEPARATE question from the
 * Documentos-tab checklist: a party can be fully ticked there (the CRM's
 * "has something plausible been collected") and still fail here (the legal
 * name, a complete endereço, a qualified cônjuge). Rendering both side by
 * side is deliberate — an operator reading only the green checklist would
 * never learn the contract still can't name this person.
 */
import { AlertCircle, CheckCircle2, Loader2, User } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { useQualificacaoCompletude } from "@/hooks/useCardHub";
import {
  rotuloEstadoCivil,
  rotuloFaltando,
} from "@/types/qualificacaoCompletude";

export interface QualificacaoCompletudePanelProps {
  /** The PERSON's own `clientes.id` — never a parte edge id (qualificação is
   *  a fact about the person, not their role in this deal). */
  clienteId: string;
  /** Optional label for the empty/error copy; the panel works without it. */
  nome?: string;
  /**
   * Opens the linked cônjuge's OWN card. A callback, not a link the panel
   * resolves itself: this component does not know how cards get opened
   * (mirrors every other render-prop-fed panel on this card) — the container
   * (`ClienteDetailModal`) owns that behaviour. Omitted renders the spouse's
   * name as plain, unclickable text.
   */
  onAbrirConjuge?: (clienteId: string, nome: string | null) => void;
}

export function QualificacaoCompletudePanel({
  clienteId,
  nome,
  onAbrirConjuge,
}: QualificacaoCompletudePanelProps) {
  const completude = useQualificacaoCompletude(clienteId);

  // Two signals off `data`, never `isLoading` — a background refetch (fired
  // by a save elsewhere on the card) must never blank this panel.
  const showSkeleton = completude.isPending && !completude.data;
  const isRefreshing = completude.isFetching && !!completude.data;
  const data = completude.data;

  if (showSkeleton) {
    return (
      <div
        className="space-y-2 py-2"
        data-testid="qualificacao-completude-skeleton"
      >
        <div className="h-4 w-40 animate-pulse rounded bg-muted" />
        <div className="h-4 w-56 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  if (completude.isError && !data) {
    return (
      <div className="space-y-2 py-2" data-testid="qualificacao-completude-error">
        <p className="text-sm text-destructive">
          Não foi possível carregar a qualificação
          {nome ? ` de ${nome}` : ""}.
        </p>
        <Button size="sm" variant="outline" onClick={() => completude.refetch()}>
          Tentar novamente
        </Button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div
      className="space-y-2 rounded-md border p-3"
      data-testid="qualificacao-completude-panel"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Qualificação para contrato
        </p>
        <div className="flex items-center gap-1.5">
          {isRefreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="qualificacao-completude-refreshing"
            />
          )}
          {completude.isError && (
            <span
              className="text-xs text-destructive"
              data-testid="qualificacao-completude-refresh-error"
            >
              Falha ao atualizar
            </span>
          )}
        </div>
      </div>

      <p className="text-sm" data-testid="qualificacao-completude-estado-civil">
        Estado civil: {rotuloEstadoCivil(data.estado_civil)}
      </p>

      {data.completo ? (
        <p
          className="flex items-center gap-1.5 text-sm text-emerald-600"
          data-testid="qualificacao-completude-completo"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          Qualificação completa para o contrato.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="qualificacao-completude-faltando">
          {data.faltando
            .filter((chave) => chave !== "conjuge" && chave !== "conjuge_qualificacao")
            .map((chave) => (
              <li
                key={chave}
                className="flex items-center gap-1.5 text-sm text-amber-700"
                data-testid={`qualificacao-completude-faltando-${chave}`}
              >
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                {rotuloFaltando(chave)}
              </li>
            ))}
        </ul>
      )}

      {/* The pair fact — rendered as its own block rather than folded into the
          list above, because "cônjuge pendente" and "cônjuge incompleto" are
          questions about a DIFFERENT person's record, not this one's. */}
      {data.faltando.includes("conjuge") && (
        <p
          className="flex items-center gap-1.5 text-sm text-amber-700"
          data-testid="qualificacao-completude-conjuge-pendente"
        >
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          Cônjuge pendente — vincule no papel da parte.
        </p>
      )}

      {data.conjuge && (
        <div
          className="flex items-center justify-between gap-2 rounded-md border border-border/60 bg-muted/30 p-2 text-sm"
          data-testid="qualificacao-completude-conjuge"
        >
          <div className="flex items-center gap-1.5">
            <User className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span data-testid="qualificacao-completude-conjuge-nome">
              {data.conjuge.nome ?? "Cônjuge sem nome"}
            </span>
            <Badge
              variant={data.conjuge.completo ? "default" : "secondary"}
              data-testid="qualificacao-completude-conjuge-badge"
            >
              {data.conjuge.completo ? "Qualificado" : "Qualificação pendente"}
            </Badge>
          </div>
          {onAbrirConjuge && (
            <Button
              size="sm"
              variant="ghost"
              data-testid="qualificacao-completude-conjuge-abrir"
              onClick={() => onAbrirConjuge(data.conjuge!.cliente_id, data.conjuge!.nome)}
            >
              Ver cadastro
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
