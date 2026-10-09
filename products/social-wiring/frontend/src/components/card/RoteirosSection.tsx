/**
 * RoteirosSection — the card's Roteiros tab.
 *
 * Lists this person's routes, newest first, each with its contabilização and
 * its properties in visiting order. Per visita the corretor records the
 * outcome (did it happen?) and an observação — which is the sentence that
 * becomes the card's timeline entry, and the thing someone reads back years
 * later.
 *
 * "Gerar Roteiro" downloads the PDF cronograma, one imóvel per page.
 *
 * 🔴 "A VISITA ACONTECEU?" AND THE PROPOSTA (sw-lead-to-contract §3)
 * -------------------------------------------------------------------
 * A due roteiro shows the `VisitaFeedbackPrompt` banner; answering it fills the
 * per-visita outcome. On an answered roteiro the visited imóveis are listed
 * (`renderVisitadas`) each with "Gerar proposta". The old "Proposta enviada /
 * aceita" toggle pills are GONE: those columns are written only by the proposta
 * orchestration, which keeps a single acceptance path. The accepted visita still
 * gets its ring and badge — "out of six properties, which one is the sale".
 *
 * 🔴 LOADING NEVER UNMOUNTS ROTEIROS THAT EXIST
 * ------------------------------------------------
 * `loading` only skeletons while `roteiros` is genuinely empty — a stale
 * `true` from the caller mid-refetch can never blank rows that are already
 * here. `refreshing` is the separate, non-reserving spinner beside the
 * heading for "a fetch is in flight and we already have roteiros" (see
 * `DocumentoChecklistSection`'s docblock for the incident this rule comes
 * from: an early return on the caller's `isPending || isFetching` alone used
 * to replace the whole list on every unrelated card mutation).
 *
 * Presentational (S3, same contract as the rest of `card/**`): props in,
 * callbacks out. The dialog and the mutations belong to the smart wrapper.
 */
import { useState } from "react";
import { FileDown, Handshake, Loader2, Plus, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { ImovelInteressesList } from "@/components/interesses/ImovelInteressesList";
import {
  MOTIVOS_NAO_REALIZADA,
  type Roteiro,
  type RoteiroFeedbackBody,
  type StatusVisita,
  type Visita,
} from "@/types/cardHub";

import { ImovelVisitaCard } from "./ImovelVisitaCard";
import { VisitaFeedbackPrompt, roteiroVencido } from "./VisitaFeedbackPrompt";

/** The three outcomes, in the order a corretor thinks about them. Three
 *  buttons, not a checkbox: "não aconteceu ainda" and "não aconteceu" are
 *  different answers and the counts must not merge them. */
const STATUS_OPCOES: { value: StatusVisita; label: string; classe: string }[] = [
  { value: "realizada", label: "Realizada", classe: "bg-emerald-600 text-white" },
  { value: "nao_realizada", label: "Não realizada", classe: "bg-rose-600 text-white" },
  { value: "pendente", label: "Pendente", classe: "bg-muted text-foreground" },
];

/** `YYYY-MM-DD` → `dd/mm/aaaa` without a timezone round-trip (a DATE has no
 *  instant; `new Date("2026-10-01")` would render the 30th west of UTC). */
function dataVisitaBR(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

export interface RoteirosSectionProps {
  /**
   * When set, the interest list (`ImovelInteressesList`: tick rows → "Gerar
   * roteiro" → order + date → POST → PDF) is mounted above the saved roteiros
   * — this tab is where the roteiro flow lives (CONTRACT §6). The card dialog
   * passes it; leave it out and the section stays purely presentational.
   */
  clienteId?: string;
  atendimentoId?: string | null;
  roteiros: Roteiro[];
  /** No `roteiros` yet — the FIRST load only. Ignored once the list is
   *  non-empty (see the file docblock). */
  loading?: boolean;
  /** A fetch is in flight AND `roteiros` already has rows — a small,
   *  non-reserving spinner beside the heading. Never unmounts the list. */
  refreshing?: boolean;
  error?: string | null;
  onCriar: () => void;
  onRemover: (roteiroId: string) => void;
  onGerarPdf: (roteiroId: string) => void;
  onPatchVisita: (
    roteiroId: string,
    visitaId: string,
    body: { status?: StatusVisita; observacao?: string | null },
  ) => void;
  /** Add one property to an EXISTING roteiro (`POST .../visitas`). The list
   *  used to be fixed at creation even though the route always existed. */
  onAddVisita: (roteiroId: string, codigo: string) => void;
  /** Drop one property from a roteiro (`DELETE .../visitas/{id}`). */
  onRemoveVisita: (roteiroId: string, visitaId: string) => void;
  /** Answer "a visita aconteceu?" for a roteiro
   *  (`POST .../roteiros/{id}/feedback`). Absent ⇒ no banner is offered. */
  onResponderFeedback?: (roteiroId: string, body: RoteiroFeedbackBody) => void;
  feedbackPendingId?: string | null;
  /** Slot under an ANSWERED roteiro — the visited-imóveis list with its
   *  "Gerar proposta" buttons (`VisitadasLista`, a smart component). */
  renderVisitadas?: (roteiro: Roteiro) => ReactNode;
  pdfPendingId?: string | null;
}

export function RoteirosSection({
  clienteId,
  atendimentoId,
  roteiros,
  loading,
  refreshing,
  error,
  onCriar,
  onRemover,
  onGerarPdf,
  onPatchVisita,
  onAddVisita,
  onRemoveVisita,
  onResponderFeedback,
  feedbackPendingId,
  renderVisitadas,
  pdfPendingId,
}: RoteirosSectionProps) {
  return (
    <div data-testid="roteiros-section">
      {clienteId && (
        <div className="mb-6" data-testid="roteiros-interesses">
          <ImovelInteressesList clienteId={clienteId} atendimentoId={atendimentoId} />
        </div>
      )}
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-sm font-semibold">Roteiros</h3>
          {refreshing && (
            <Loader2
              className="h-3 w-3 animate-spin text-muted-foreground"
              data-testid="roteiros-refreshing"
            />
          )}
        </div>
        <Button size="sm" onClick={onCriar} data-testid="roteiro-criar-trigger">
          <Plus className="mr-2 h-4 w-4" />
          Criar Roteiro
        </Button>
      </div>

      {/* `roteiros.length === 0` guards the skeleton: a stale `loading=true`
          mid-refetch (the caller still gates it on `isPending || isFetching`,
          never `isLoading`) can never replace roteiros that are already
          here — see the file docblock. */}
      {loading && roteiros.length === 0 ? (
        <div className="space-y-2" data-testid="roteiros-loading">
          <div className="h-20 animate-pulse rounded-lg bg-muted" />
          <div className="h-20 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : error ? (
        <p className="text-sm text-destructive" data-testid="roteiros-erro">
          {error}
        </p>
      ) : roteiros.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="roteiros-empty">
          Nenhum roteiro criado. Crie um para planejar as visitas deste cliente.
        </p>
      ) : (
        <div className="space-y-4">
          {roteiros.map((roteiro) => (
            <RoteiroCard
              key={roteiro.id}
              roteiro={roteiro}
              onRemover={() => onRemover(roteiro.id)}
              onGerarPdf={() => onGerarPdf(roteiro.id)}
              onPatchVisita={(visitaId, body) => onPatchVisita(roteiro.id, visitaId, body)}
              onAddVisita={(codigo) => onAddVisita(roteiro.id, codigo)}
              onRemoveVisita={(visitaId) => onRemoveVisita(roteiro.id, visitaId)}
              onResponderFeedback={
                onResponderFeedback
                  ? (body) => onResponderFeedback(roteiro.id, body)
                  : undefined
              }
              feedbackPending={feedbackPendingId === roteiro.id}
              visitadas={
                roteiro.feedback_status === "respondido" ? renderVisitadas?.(roteiro) : null
              }
              pdfPending={pdfPendingId === roteiro.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RoteiroCard({
  roteiro,
  onRemover,
  onGerarPdf,
  onPatchVisita,
  onAddVisita,
  onRemoveVisita,
  onResponderFeedback,
  feedbackPending,
  visitadas,
  pdfPending,
}: {
  roteiro: Roteiro;
  onRemover: () => void;
  onGerarPdf: () => void;
  onPatchVisita: (visitaId: string, body: { status?: StatusVisita; observacao?: string | null }) => void;
  onAddVisita: (codigo: string) => void;
  onRemoveVisita: (visitaId: string) => void;
  onResponderFeedback?: (body: RoteiroFeedbackBody) => void;
  feedbackPending?: boolean;
  visitadas?: ReactNode;
  pdfPending?: boolean;
}) {
  const [novoCodigo, setNovoCodigo] = useState("");
  const { contagem } = roteiro;
  // At most one per ATENDIMENTO — the server refuses a second, across
  // roteiros. `find` here is the display of that fact, never its enforcement.
  const aceita = roteiro.visitas.find((v) => v.proposta_aceita_em);

  return (
    <div className="rounded-lg border" data-testid={`roteiro-${roteiro.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {roteiro.titulo || `Roteiro de ${formatDate(roteiro.created_at ?? "", false)}`}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5" data-testid="roteiro-contagem">
            <Chip tom="ok">{contagem.realizadas} realizadas</Chip>
            <Chip tom="ruim">{contagem.nao_realizadas} não realizadas</Chip>
            <Chip tom="neutro">{contagem.pendentes} pendentes</Chip>
            {roteiro.data_visita && (
              <Chip tom="neutro">
                <span data-testid="roteiro-data-visita-chip">
                  visita em {dataVisitaBR(roteiro.data_visita)}
                </span>
              </Chip>
            )}
            {aceita && (
              // The one fact somebody scanning this card is looking for.
              <Chip tom="ok">
                <Handshake className="mr-1 inline h-3 w-3" aria-hidden />
                proposta aceita: {aceita.codigo}
              </Chip>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={onGerarPdf}
            // An empty roteiro has nothing to print, and the API answers 422
            // rather than handing back a zero-page file. Disabling here means
            // the user never meets that error.
            disabled={contagem.total === 0 || pdfPending}
            data-testid={`roteiro-pdf-${roteiro.id}`}
          >
            {pdfPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <FileDown className="mr-2 h-4 w-4" />
            )}
            Gerar Roteiro
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onRemover}
            aria-label="Remover roteiro"
            data-testid={`roteiro-remover-${roteiro.id}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {onResponderFeedback && roteiroVencido(roteiro) && (
        <VisitaFeedbackPrompt
          roteiro={roteiro}
          onSubmit={onResponderFeedback}
          pending={feedbackPending}
        />
      )}

      <div className="space-y-3 p-3">
        {roteiro.visitas.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">
            Nenhum imóvel neste roteiro.
          </p>
        ) : (
          roteiro.visitas.map((visita, i) => (
            <VisitaRow
              key={visita.id}
              visita={visita}
              posicao={i + 1}
              onPatch={(body) => onPatchVisita(visita.id, body)}
              onRemove={() => onRemoveVisita(visita.id)}
            />
          ))
        )}

        {/* Add a property to a roteiro that already exists. */}
        <form
          className="flex items-center gap-2 pt-1"
          onSubmit={(e) => {
            e.preventDefault();
            const codigo = novoCodigo.trim().toUpperCase();
            if (!codigo) return;
            onAddVisita(codigo);
            setNovoCodigo("");
          }}
        >
          <Input
            value={novoCodigo}
            onChange={(e) => setNovoCodigo(e.target.value)}
            placeholder="Código do imóvel"
            className="h-8 text-sm"
            aria-label="Código do imóvel a adicionar"
            data-testid={`roteiro-add-codigo-${roteiro.id}`}
          />
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={novoCodigo.trim().length === 0}
            data-testid={`roteiro-add-visita-${roteiro.id}`}
          >
            <Plus className="mr-1 h-3.5 w-3.5" />
            Adicionar
          </Button>
        </form>
      </div>
      {visitadas}
    </div>
  );
}

function VisitaRow({
  visita,
  posicao,
  onPatch,
  onRemove,
}: {
  visita: Visita;
  posicao: number;
  onPatch: (body: { status?: StatusVisita; observacao?: string | null }) => void;
  onRemove: () => void;
}) {
  const [observacao, setObservacao] = useState(visita.observacao ?? "");
  const sujo = (visita.observacao ?? "") !== observacao;
  const temProposta = !!visita.proposta_em;
  const aceita = !!visita.proposta_aceita_em;

  return (
    <div className="space-y-2" data-testid={`visita-${visita.id}`}>
      {visita.imovel ? (
        <ImovelVisitaCard
          id={visita.id}
          imovel={visita.imovel}
          posicao={posicao}
          // Reordering happens where the plan is made — inside the dialog.
          // A sort handle on a route already being walked would invite
          // reshuffling history.
          sortable={false}
          propostaFeita={temProposta}
          propostaAceita={aceita}
        />
      ) : (
        <p className="rounded-lg border p-3 text-sm">{visita.codigo}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5 pl-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={onRemove}
          aria-label={`Remover ${visita.codigo} do roteiro`}
          data-testid={`visita-remover-${visita.id}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
        {STATUS_OPCOES.map((opcao) => {
          const ativo = visita.status === opcao.value;
          return (
            <button
              key={opcao.value}
              type="button"
              onClick={() => onPatch({ status: opcao.value })}
              aria-pressed={ativo}
              className={cn(
                "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                ativo ? opcao.classe : "bg-muted/50 text-muted-foreground hover:bg-muted",
              )}
              data-testid={`visita-status-${opcao.value}-${visita.id}`}
            >
              {opcao.label}
            </button>
          );
        })}
        {visita.feedback_em && (
          <span className="text-xs text-muted-foreground">
            em {formatDate(visita.feedback_em, true)}
          </span>
        )}
        {visita.status === "nao_realizada" && visita.nao_realizada_motivo && (
          <span className="text-xs text-rose-700 dark:text-rose-300" data-testid={`visita-motivo-${visita.id}`}>
            {MOTIVOS_NAO_REALIZADA.find((m) => m.value === visita.nao_realizada_motivo)?.label ??
              visita.nao_realizada_motivo}
          </span>
        )}
      </div>

      <div className="pl-1">
        <Textarea
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          // Saved on blur, not on every keystroke: this is prose, and a PATCH
          // per character would be both noisy and lossy under a slow network.
          onBlur={() => {
            if (sujo) onPatch({ observacao: observacao.trim() || null });
          }}
          rows={2}
          placeholder="Observação da visita..."
          data-testid={`visita-observacao-${visita.id}`}
        />
      </div>
    </div>
  );
}

function Chip({ tom, children }: { tom: "ok" | "ruim" | "neutro"; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        tom === "ok" && "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
        tom === "ruim" && "bg-rose-100 text-rose-900 dark:bg-rose-950 dark:text-rose-200",
        tom === "neutro" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
