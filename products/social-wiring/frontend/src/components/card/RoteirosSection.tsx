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
 * Presentational (S3, same contract as the rest of `card/**`): props in,
 * callbacks out. The dialog and the mutations belong to the smart wrapper.
 */
import { useState } from "react";
import { FileDown, Loader2, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
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
  loading?: boolean;
  error?: string | null;
  onCriar: () => void;
  onRemover: (roteiroId: string) => void;
  onGerarPdf: (roteiroId: string) => void;
  onPatchVisita: (
    roteiroId: string,
    visitaId: string,
    body: { status?: StatusVisita; observacao?: string | null },
  ) => void;
  pdfPendingId?: string | null;
}

export function RoteirosSection({
  roteiros,
  loading,
  error,
  onCriar,
  onRemover,
  onGerarPdf,
  onPatchVisita,
  pdfPendingId,
}: RoteirosSectionProps) {
  return (
    <div data-testid="roteiros-section">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Roteiros</h3>
        <Button size="sm" onClick={onCriar} data-testid="roteiro-criar-trigger">
          <Plus className="mr-2 h-4 w-4" />
          Criar Roteiro
        </Button>
      </div>

      {/* 🔴 The loading branch is gated by the CALLER on `isPending ||
          isFetching`, never `isLoading` — v5's `isLoading` is false during a
          background refetch, so an empty branch would render "nenhum roteiro"
          over roteiros that exist. */}
      {loading ? (
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
  pdfPending,
}: {
  roteiro: Roteiro;
  onRemover: () => void;
  onGerarPdf: () => void;
  onPatchVisita: (visitaId: string, body: { status?: StatusVisita; observacao?: string | null }) => void;
  pdfPending?: boolean;
}) {
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
            />
          ))
        )}
      </div>
    </div>
  );
}

function VisitaRow({
  visita,
  posicao,
  onPatch,
}: {
  visita: Visita;
  posicao: number;
  onPatch: (body: { status?: StatusVisita; observacao?: string | null }) => void;
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
