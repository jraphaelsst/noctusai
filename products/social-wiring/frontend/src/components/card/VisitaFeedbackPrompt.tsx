/**
 * VisitaFeedbackPrompt — "A visita aconteceu?" (CONTRACT sw-lead-to-contract §3.2–3.3).
 *
 * Two pieces:
 *  - the BANNER shown on a roteiro while it is due (`roteiroVencido`);
 *  - the ANSWER DIALOG: yes / no for the roteiro, then per-visita detail.
 *    "Não" is one motivo for every visita (default `outro`); "Sim" asks each
 *    visita whether it happened, and a visita that did not requires a motivo
 *    from the closed enum (the server refuses otherwise with a 400).
 *
 * Presentational: `onSubmit` is the only callback out; the caller owns the POST.
 */
import { useState } from "react";
import { CalendarCheck, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  CANCELADA_MOTIVO,
  CANCELADA_POR,
  type CanceladaMotivo,
  type CanceladaPor,
  type ResultadoVisita,
  type Roteiro,
  type RoteiroFeedbackBody,
  type VisitaFeedbackItem,
} from "@/types/cardHub";

/** What an answer can record for a visita (R14). Pendente is not an answer. */
const RESULTADOS: { value: ResultadoVisita; label: string }[] = [
  { value: "realizada", label: "Realizada" },
  { value: "cancelada", label: "Cancelada" },
  { value: "nao_compareceu", label: "Não compareceu" },
  { value: "reagendada", label: "Reagendada (não conta)" },
];

/** Is this roteiro due for an answer at `agora`? `data_visita` is a DATE, so the
 *  comparison is on local `YYYY-MM-DD` strings (no timezone round-trip).
 *  A DRAFT is never due: only a gerado roteiro enters the feedback flow (R14 → 409). */
export function roteiroVencido(roteiro: Roteiro, agora: Date = new Date()): boolean {
  if (roteiro.status !== "gerado") return false;
  if (roteiro.feedback_status !== "pendente" || !roteiro.data_visita) return false;
  const hoje = [
    agora.getFullYear(),
    String(agora.getMonth() + 1).padStart(2, "0"),
    String(agora.getDate()).padStart(2, "0"),
  ].join("-");
  const dia = roteiro.data_visita.slice(0, 10);
  if (dia < hoje) return true;
  if (dia > hoje) return false;
  if (!roteiro.hora_visita) return true;
  const hhmm = `${String(agora.getHours()).padStart(2, "0")}:${String(agora.getMinutes()).padStart(2, "0")}`;
  return roteiro.hora_visita.slice(0, 5) <= hhmm;
}

export interface VisitaFeedbackPromptProps {
  roteiro: Roteiro;
  onSubmit: (body: RoteiroFeedbackBody) => void;
  pending?: boolean;
}

export function VisitaFeedbackPrompt({ roteiro, onSubmit, pending }: VisitaFeedbackPromptProps) {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <div
        className="flex flex-wrap items-center justify-between gap-2 border-b bg-warning-light px-3 py-2"
        data-testid={`visita-feedback-banner-${roteiro.id}`}
        role="status"
      >
        <p className="flex items-center gap-2 text-sm font-medium text-warning-foreground">
          <CalendarCheck className="h-4 w-4" aria-hidden />A visita aconteceu?
        </p>
        <Button
          size="sm"
          onClick={() => setAberto(true)}
          data-testid={`visita-feedback-abrir-${roteiro.id}`}
        >
          Responder
        </Button>
      </div>
      {aberto && (
        <FeedbackDialog
          roteiro={roteiro}
          pending={pending}
          onClose={() => setAberto(false)}
          onSubmit={(body) => {
            onSubmit(body);
            setAberto(false);
          }}
        />
      )}
    </>
  );
}

interface LinhaState {
  resultado: ResultadoVisita;
  motivo: CanceladaMotivo | "";
  por: CanceladaPor | "";
  observacao: string;
}

const linhaInicial = (): LinhaState => ({
  resultado: "realizada",
  motivo: "",
  por: "",
  observacao: "",
});

/** A cancelada needs BOTH a motivo and who cancelled (R11/R14 → 422 `cancelada_incompleta`). */
const faltaCancelamento = (l: LinhaState) =>
  l.resultado === "cancelada" && (l.motivo === "" || l.por === "");

function itemDe(visitaId: string, l: LinhaState): VisitaFeedbackItem {
  return {
    visita_id: visitaId,
    realizada: l.resultado === "realizada",
    resultado: l.resultado,
    ...(l.resultado === "cancelada"
      ? { cancelada_por: l.por || null, cancelada_motivo: l.motivo || null }
      : {}),
    observacao: l.observacao.trim() || null,
  };
}

function FeedbackDialog({
  roteiro,
  pending,
  onClose,
  onSubmit,
}: {
  roteiro: Roteiro;
  pending?: boolean;
  onClose: () => void;
  onSubmit: (body: RoteiroFeedbackBody) => void;
}) {
  const [aconteceu, setAconteceu] = useState<boolean | null>(null);
  // "Não aconteceu": one outcome for every visita (default `cancelada`, the common one).
  const [geral, setGeral] = useState<LinhaState>({ ...linhaInicial(), resultado: "cancelada" });
  const [linhas, setLinhas] = useState<Record<string, LinhaState>>(() =>
    Object.fromEntries(roteiro.visitas.map((v) => [v.id, linhaInicial()])),
  );

  const setLinha = (id: string, patch: Partial<LinhaState>) =>
    setLinhas((atual) => ({ ...atual, [id]: { ...atual[id], ...patch } }));

  // Block the submit here rather than meeting the server's 422.
  const faltaMotivo =
    aconteceu === true
      ? roteiro.visitas.some((v) => faltaCancelamento(linhas[v.id]))
      : aconteceu === false && faltaCancelamento(geral);
  const podeEnviar = aconteceu !== null && !faltaMotivo && !pending;

  function enviar() {
    if (aconteceu === null) return;
    if (!aconteceu) {
      onSubmit({
        aconteceu: false,
        visitas: roteiro.visitas.map((v) => itemDe(v.id, { ...geral, observacao: "" })),
      });
      return;
    }
    onSubmit({
      aconteceu: true,
      visitas: roteiro.visitas.map((v) => itemDe(v.id, linhas[v.id])),
    });
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" data-testid="visita-feedback-dialog">
        <DialogHeader>
          <DialogTitle>A visita aconteceu?</DialogTitle>
          <DialogDescription>
            {roteiro.titulo || "Roteiro"} — {roteiro.visitas.length} imóve
            {roteiro.visitas.length === 1 ? "l" : "is"}.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2" role="group" aria-label="A visita aconteceu?">
          {[
            { v: true, label: "Sim, aconteceu" },
            { v: false, label: "Não aconteceu" },
          ].map((o) => (
            <button
              key={String(o.v)}
              type="button"
              aria-pressed={aconteceu === o.v}
              onClick={() => setAconteceu(o.v)}
              className={cn(
                "flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                aconteceu === o.v
                  ? o.v
                    ? "border-success bg-success text-white"
                    : "border-destructive bg-destructive text-white"
                  : "hover:bg-muted",
              )}
              data-testid={`visita-feedback-${o.v ? "sim" : "nao"}`}
            >
              {o.label}
            </button>
          ))}
        </div>

        {aconteceu === false && (
          <ResultadoCampos
            linha={geral}
            onChange={(p) => setGeral((l) => ({ ...l, ...p }))}
            testid="visita-feedback-geral"
            legenda="O que aconteceu?"
          />
        )}

        {aconteceu === true && (
          <ul className="max-h-[50vh] space-y-3 overflow-y-auto" data-testid="visita-feedback-linhas">
            {roteiro.visitas.map((v) => {
              const l = linhas[v.id];
              return (
                <li key={v.id} className="space-y-2 rounded-md border p-3">
                  <span className="block truncate text-sm font-medium">
                    {v.imovel?.titulo || v.codigo}
                  </span>
                  <ResultadoCampos
                    linha={l}
                    onChange={(p) => setLinha(v.id, p)}
                    testid={`visita-feedback-${v.id}`}
                    legenda="Resultado"
                  />
                  <Textarea
                    rows={2}
                    value={l.observacao}
                    onChange={(e) => setLinha(v.id, { observacao: e.target.value })}
                    placeholder="Observação (opcional)"
                    aria-label={`Observação da visita a ${v.codigo}`}
                  />
                </li>
              );
            })}
          </ul>
        )}

        {faltaMotivo && (
          <p className="text-xs text-destructive" data-testid="visita-feedback-falta-motivo">
            Informe o motivo e quem cancelou cada visita cancelada.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={enviar} disabled={!podeEnviar} data-testid="visita-feedback-enviar">
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Salvar resposta
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResultadoCampos({
  linha,
  onChange,
  testid,
  legenda,
}: {
  linha: LinhaState;
  onChange: (patch: Partial<LinhaState>) => void;
  testid: string;
  legenda: string;
}) {
  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-muted-foreground">
        {legenda}
        <select
          className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
          value={linha.resultado}
          onChange={(e) => onChange({ resultado: e.target.value as ResultadoVisita })}
          data-testid={`${testid}-resultado`}
        >
          {RESULTADOS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      {linha.resultado === "cancelada" && (
        <div className="flex flex-wrap gap-2">
          <label className="block flex-1 text-xs font-medium text-muted-foreground">
            Motivo *
            <select
              className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              value={linha.motivo}
              onChange={(e) => onChange({ motivo: e.target.value as CanceladaMotivo | "" })}
              data-testid={`${testid}-motivo`}
            >
              <option value="">Selecione…</option>
              {CANCELADA_MOTIVO.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block flex-1 text-xs font-medium text-muted-foreground">
            Quem cancelou *
            <select
              className="mt-1 h-9 w-full rounded-md border bg-background px-2 text-sm text-foreground"
              value={linha.por}
              onChange={(e) => onChange({ por: e.target.value as CanceladaPor | "" })}
              data-testid={`${testid}-por`}
            >
              <option value="">Selecione…</option>
              {CANCELADA_POR.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
    </div>
  );
}
