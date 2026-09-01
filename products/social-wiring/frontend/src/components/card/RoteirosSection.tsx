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
import { FileDown, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { Roteiro, StatusVisita, Visita } from "@/types/cardHub";

import { ImovelVisitaCard } from "./ImovelVisitaCard";

/** The three outcomes, in the order a corretor thinks about them. Three
 *  buttons, not a checkbox: "não aconteceu ainda" and "não aconteceu" are
 *  different answers and the counts must not merge them. */
const STATUS_OPCOES: { value: StatusVisita; label: string; classe: string }[] = [
  { value: "realizada", label: "Realizada", classe: "bg-emerald-600 text-white" },
  { value: "nao_realizada", label: "Não realizada", classe: "bg-rose-600 text-white" },
  { value: "pendente", label: "Pendente", classe: "bg-muted text-foreground" },
];

export interface RoteirosSectionProps {
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
  pdfPendingId?: string | null;
}

export function RoteirosSection({
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
  pdfPendingId,
}: RoteirosSectionProps) {
  return (
    <div data-testid="roteiros-section">
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
  pdfPending,
}: {
  roteiro: Roteiro;
  onRemover: () => void;
  onGerarPdf: () => void;
  onPatchVisita: (visitaId: string, body: { status?: StatusVisita; observacao?: string | null }) => void;
  onAddVisita: (codigo: string) => void;
  onRemoveVisita: (visitaId: string) => void;
  pdfPending?: boolean;
}) {
  const [novoCodigo, setNovoCodigo] = useState("");
  const { contagem } = roteiro;

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
