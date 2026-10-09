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
  MOTIVOS_NAO_REALIZADA,
  type MotivoNaoRealizada,
  type Roteiro,
  type RoteiroFeedbackBody,
} from "@/types/cardHub";

/** Is this roteiro due for an answer at `agora`? `data_visita` is a DATE, so the
 *  comparison is on local `YYYY-MM-DD` strings (no timezone round-trip). */
export function roteiroVencido(roteiro: Roteiro, agora: Date = new Date()): boolean {
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
        className="flex flex-wrap items-center justify-between gap-2 border-b bg-amber-50 px-3 py-2 dark:bg-amber-950/30"
        data-testid={`visita-feedback-banner-${roteiro.id}`}
        role="status"
      >
        <p className="flex items-center gap-2 text-sm font-medium text-amber-900 dark:text-amber-200">
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
  realizada: boolean;
  motivo: MotivoNaoRealizada | "";
  observacao: string;
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
  const [motivoGeral, setMotivoGeral] = useState<MotivoNaoRealizada>("outro");
  const [linhas, setLinhas] = useState<Record<string, LinhaState>>(() =>
    Object.fromEntries(
      roteiro.visitas.map((v) => [v.id, { realizada: true, motivo: "" as const, observacao: "" }]),
    ),
  );

  const setLinha = (id: string, patch: Partial<LinhaState>) =>
    setLinhas((atual) => ({ ...atual, [id]: { ...atual[id], ...patch } }));

  // "Sim": a visita that did not happen needs its motivo — block the submit
  // here rather than meeting the server's 400.
  const faltaMotivo =
    aconteceu === true && roteiro.visitas.some((v) => !linhas[v.id].realizada && !linhas[v.id].motivo);
  const podeEnviar = aconteceu !== null && !faltaMotivo && !pending;

  function enviar() {
    if (aconteceu === null) return;
    if (!aconteceu) {
      onSubmit({
        aconteceu: false,
        visitas: roteiro.visitas.map((v) => ({
          visita_id: v.id,
          realizada: false,
          motivo: motivoGeral,
        })),
      });
      return;
    }
    onSubmit({
      aconteceu: true,
      visitas: roteiro.visitas.map((v) => {
        const l = linhas[v.id];
        return {
          visita_id: v.id,
          realizada: l.realizada,
          motivo: l.realizada ? null : (l.motivo as MotivoNaoRealizada),
          observacao: l.observacao.trim() || null,
        };
      }),
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
                    ? "border-emerald-600 bg-emerald-600 text-white"
                    : "border-rose-600 bg-rose-600 text-white"
                  : "hover:bg-muted",
              )}
              data-testid={`visita-feedback-${o.v ? "sim" : "nao"}`}
            >
              {o.label}
            </button>
          ))}
        </div>

        {aconteceu === false && (
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Motivo</span>
            <MotivoSelect
              value={motivoGeral}
              onChange={(m) => m && setMotivoGeral(m)}
              testid="visita-feedback-motivo-geral"
            />
          </label>
        )}

        {aconteceu === true && (
          <ul className="max-h-[50vh] space-y-3 overflow-y-auto" data-testid="visita-feedback-linhas">
            {roteiro.visitas.map((v) => {
              const l = linhas[v.id];
              return (
                <li key={v.id} className="space-y-2 rounded-md border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">
                      {v.imovel?.titulo || v.codigo}
                    </span>
                    <label className="flex shrink-0 items-center gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        checked={l.realizada}
                        onChange={(e) => setLinha(v.id, { realizada: e.target.checked })}
                        data-testid={`visita-feedback-realizada-${v.id}`}
                      />
                      Realizada
                    </label>
                  </div>
                  {!l.realizada && (
                    <MotivoSelect
                      value={l.motivo}
                      onChange={(m) => setLinha(v.id, { motivo: m })}
                      allowEmpty
                      testid={`visita-feedback-motivo-${v.id}`}
                    />
                  )}
                  <Textarea
                    rows={2}
                    value={l.observacao}
                    onChange={(e) => setLinha(v.id, { observacao: e.target.value })}
                    placeholder="Observação (opcional)"
                  />
                </li>
              );
            })}
          </ul>
        )}

        {faltaMotivo && (
          <p className="text-xs text-destructive" data-testid="visita-feedback-falta-motivo">
            Informe o motivo de cada visita não realizada.
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

function MotivoSelect({
  value,
  onChange,
  allowEmpty,
  testid,
}: {
  value: MotivoNaoRealizada | "";
  onChange: (m: MotivoNaoRealizada | "") => void;
  allowEmpty?: boolean;
  testid: string;
}) {
  return (
    <select
      className="h-9 w-full rounded-md border bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value as MotivoNaoRealizada | "")}
      data-testid={testid}
    >
      {allowEmpty && <option value="">Selecione o motivo…</option>}
      {MOTIVOS_NAO_REALIZADA.map((m) => (
        <option key={m.value} value={m.value}>
          {m.label}
        </option>
      ))}
    </select>
  );
}
