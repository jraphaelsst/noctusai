/**
 * RoteirosSection — the card's Roteiros tab.
 *
 * Lists this person's routes, newest first. Every roteiro is either a
 * RASCUNHO (autosaved, edited in `RoteiroEditorDialog` via "Continuar
 * editando") or GERADO (roteiro-ciclo CONTRACT §5): the imóvel list is locked,
 * per visita the corretor records the outcome — Pendente · Realizada ·
 * Cancelada (motivo + quem cancelou, both required) · Não compareceu ·
 * Reagendada (NEUTRAL: it opens a NEW roteiro) — plus an observação, which
 * becomes the card's timeline entry.
 *
 * 🔴 EVERY CONTROL IS RENDERED FROM THE SERVER'S `permissoes`, never from a
 * client-side re-derivation of the rules:
 *  - "Baixar PDF" exists ONLY when `permissoes.baixar_pdf` (a gerado roteiro).
 *    It is never rendered on a draft (the server refuses too: 409).
 *  - "Reabrir como rascunho" is shown when `permissoes.reabrir` or the server
 *    explains why not (`motivo_reabrir`), disabled with that reason.
 *
 * 🔴 "A VISITA ACONTECEU?" AND THE PROPOSTA (sw-lead-to-contract §3)
 * -------------------------------------------------------------------
 * A due GERADO roteiro shows the `VisitaFeedbackPrompt` banner; answering it
 * fills the per-visita outcome. On an answered roteiro the visited imóveis are
 * listed (`renderVisitadas`) each with "Gerar proposta".
 *
 * 🔴 LOADING NEVER UNMOUNTS ROTEIROS THAT EXIST
 * ------------------------------------------------
 * `loading` only skeletons while `roteiros` is genuinely empty — a stale
 * `true` from the caller mid-refetch can never blank rows that are already
 * here. `refreshing` is the separate, non-reserving spinner beside the
 * heading (see `DocumentoChecklistSection`'s docblock for the incident).
 *
 * Presentational (S3, same contract as the rest of `card/**`): props in,
 * callbacks out. The editor dialog and the mutations belong to the wrapper.
 */
import { useState } from "react";
import { FileDown, Handshake, Loader2, LockKeyhole, Pencil, Plus, Trash2, Unlock } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { dataVisitaBR } from "@/lib/roteiroLabels";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { ImovelInteressesList } from "@/components/interesses/ImovelInteressesList";
import {
  CANCELADA_MOTIVO,
  CANCELADA_POR,
  type CanceladaMotivo,
  type CanceladaPor,
  type Roteiro,
  type RoteiroFeedbackBody,
  type RoteiroPatchBody,
  type StatusVisita,
  type Visita,
  type VisitaPatchBody,
} from "@/types/cardHub";

import { ImovelVisitaCard } from "./ImovelVisitaCard";
import { VisitaFeedbackPrompt, roteiroVencido } from "./VisitaFeedbackPrompt";

/** The five outcomes, in the order a corretor thinks about them. Buttons (a
 *  pressed group), not a checkbox: "não aconteceu ainda" and "não aconteceu"
 *  are different answers and the counts must not merge them.
 *
 *  Pressed = tinted background + a border + semibold, never white-on-`success`
 *  (NOTES F2: ≈ 2.1:1 — WCAG 1.4.3). */
const STATUS_OPCOES: { value: StatusVisita; label: string; classe: string }[] = [
  { value: "pendente", label: "Pendente", classe: "border-border bg-muted text-foreground" },
  { value: "realizada", label: "Realizada", classe: "border-success bg-success-light text-foreground" },
  { value: "cancelada", label: "Cancelada", classe: "border-destructive bg-danger-light text-foreground" },
  { value: "nao_compareceu", label: "Não compareceu", classe: "border-destructive bg-danger-light text-foreground" },
  { value: "reagendada", label: "Reagendada", classe: "border-border bg-muted text-foreground" },
];

export interface RoteirosSectionProps {
  /**
   * When set, the interest list (`ImovelInteressesList`: tick rows → "Gerar
   * roteiro" → the editor opens with those imóveis as a new draft) is mounted
   * above the saved roteiros. Leave it out and the section stays purely
   * presentational.
   */
  clienteId?: string;
  atendimentoId?: string | null;
  roteiros: Roteiro[];
  /** No `roteiros` yet — the FIRST load only. Ignored once the list is non-empty. */
  loading?: boolean;
  /** A fetch is in flight AND `roteiros` already has rows — never unmounts the list. */
  refreshing?: boolean;
  error?: string | null;
  /** "Criar Roteiro" — opens the editor on a NEW draft. */
  onCriar: () => void;
  /** "Continuar editando" — reopens a draft in the editor. */
  onEditarRascunho: (roteiroId: string) => void;
  onRemover: (roteiroId: string) => void;
  /** "Baixar PDF" — only ever offered on a gerado roteiro (`permissoes.baixar_pdf`). */
  onBaixarPdf: (roteiroId: string) => void;
  /** "Reabrir como rascunho" — the caller owns the confirmation dialog. */
  onReabrir: (roteiroId: string) => void;
  reabrindoId?: string | null;
  /** Date / time of a GERADO roteiro stay editable (R3). */
  onPatchRoteiro: (roteiroId: string, body: RoteiroPatchBody) => void;
  onPatchVisita: (roteiroId: string, visitaId: string, body: VisitaPatchBody) => void;
  /** "Criar novo roteiro com ONExxxx" (R12): closes the visita as reagendada, opens the new draft. */
  onReagendar: (roteiroId: string, visitaId: string) => void;
  reagendandoId?: string | null;
  /** Answer "a visita aconteceu?" for a roteiro. Absent ⇒ no banner is offered. */
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
  onEditarRascunho,
  onRemover,
  onBaixarPdf,
  onReabrir,
  reabrindoId,
  onPatchRoteiro,
  onPatchVisita,
  onReagendar,
  reagendandoId,
  onResponderFeedback,
  feedbackPendingId,
  renderVisitadas,
  pdfPendingId,
}: RoteirosSectionProps) {
  /** The roteiro that replaced a reagendada visita (its new draft), if cached:
   *  the one holding the visita `reagendada_para_visita_id` points to. */
  const roteiroQueSubstituiu = (visitaId: string) => {
    const destino = roteiros
      .flatMap((r) => r.visitas)
      .find((v) => v.id === visitaId)?.reagendada_para_visita_id;
    return destino ? roteiros.find((r) => r.visitas.some((v) => v.id === destino)) : undefined;
  };

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
          mid-refetch (the caller gates it on `isPending && !data`, never
          `isLoading`) can never replace roteiros that are already here. */}
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
              onEditarRascunho={() => onEditarRascunho(roteiro.id)}
              onRemover={() => onRemover(roteiro.id)}
              onBaixarPdf={() => onBaixarPdf(roteiro.id)}
              onReabrir={() => onReabrir(roteiro.id)}
              reabrindo={reabrindoId === roteiro.id}
              onPatchRoteiro={(body) => onPatchRoteiro(roteiro.id, body)}
              onPatchVisita={(visitaId, body) => onPatchVisita(roteiro.id, visitaId, body)}
              onReagendar={(visitaId) => onReagendar(roteiro.id, visitaId)}
              reagendandoVisitaId={reagendandoId ?? null}
              onAbrirNovoRoteiro={(visitaId) => {
                const novo = roteiroQueSubstituiu(visitaId);
                if (novo) onEditarRascunho(novo.id);
              }}
              onResponderFeedback={
                onResponderFeedback ? (body) => onResponderFeedback(roteiro.id, body) : undefined
              }
              feedbackPending={feedbackPendingId === roteiro.id}
              visitadas={
                roteiro.status === "gerado" && roteiro.feedback_status === "respondido"
                  ? renderVisitadas?.(roteiro)
                  : null
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
  onEditarRascunho,
  onRemover,
  onBaixarPdf,
  onReabrir,
  reabrindo,
  onPatchRoteiro,
  onPatchVisita,
  onReagendar,
  reagendandoVisitaId,
  onAbrirNovoRoteiro,
  onResponderFeedback,
  feedbackPending,
  visitadas,
  pdfPending,
}: {
  roteiro: Roteiro;
  onEditarRascunho: () => void;
  onRemover: () => void;
  onBaixarPdf: () => void;
  onReabrir: () => void;
  reabrindo?: boolean;
  onPatchRoteiro: (body: RoteiroPatchBody) => void;
  onPatchVisita: (visitaId: string, body: VisitaPatchBody) => void;
  onReagendar: (visitaId: string) => void;
  reagendandoVisitaId: string | null;
  onAbrirNovoRoteiro: (visitaId: string) => void;
  onResponderFeedback?: (body: RoteiroFeedbackBody) => void;
  feedbackPending?: boolean;
  visitadas?: ReactNode;
  pdfPending?: boolean;
}) {
  const { contagem, permissoes } = roteiro;
  const gerado = roteiro.status === "gerado";
  // At most one per ATENDIMENTO — the server refuses a second, across
  // roteiros. `find` here is the display of that fact, never its enforcement.
  const aceita = roteiro.visitas.find((v) => v.proposta_aceita_em);
  // "Reabrir" is shown when the user may reopen OR the server says why not.
  const mostraReabrir = gerado && (permissoes.reabrir || !!permissoes.motivo_reabrir);

  return (
    <div className="rounded-lg border" data-testid={`roteiro-${roteiro.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {roteiro.titulo || `Roteiro de ${formatDate(roteiro.created_at ?? "", false)}`}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5" data-testid="roteiro-contagem">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-xs font-medium",
                gerado ? "bg-success-light text-foreground" : "bg-warning-light text-warning-foreground",
              )}
              data-testid={`roteiro-status-${roteiro.id}`}
            >
              {gerado ? "Gerado" : "Rascunho"}
            </span>
            {gerado && roteiro.gerado_em && (
              <span className="text-xs text-muted-foreground">
                em {formatDate(roteiro.gerado_em, true)}
              </span>
            )}
            {gerado && (
              <>
                <Chip tom="ok">{contagem.realizadas} realizadas</Chip>
                <Chip tom="ruim">{contagem.perdidas} perdidas</Chip>
                {contagem.reagendadas > 0 && (
                  <Chip tom="neutro">{contagem.reagendadas} reagendadas · não conta</Chip>
                )}
                <Chip tom="neutro">{contagem.pendentes} pendentes</Chip>
              </>
            )}
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
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          {!gerado && (
            <Button
              variant="outline"
              size="sm"
              onClick={onEditarRascunho}
              data-testid={`roteiro-continuar-${roteiro.id}`}
            >
              <Pencil className="mr-2 h-4 w-4" />
              Continuar editando
            </Button>
          )}
          {/* 🔴 ONLY when the server says so — never on a draft. */}
          {permissoes.baixar_pdf && (
            <Button
              variant="outline"
              size="sm"
              onClick={onBaixarPdf}
              disabled={pdfPending}
              data-testid={`roteiro-pdf-${roteiro.id}`}
            >
              {pdfPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <FileDown className="mr-2 h-4 w-4" />
              )}
              Baixar PDF
            </Button>
          )}
          {mostraReabrir && (
            <Button
              variant="outline"
              size="sm"
              onClick={onReabrir}
              disabled={!permissoes.reabrir || reabrindo}
              aria-describedby={
                !permissoes.reabrir ? `roteiro-reabrir-motivo-${roteiro.id}` : undefined
              }
              data-testid={`roteiro-reabrir-${roteiro.id}`}
            >
              {reabrindo ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Unlock className="mr-2 h-4 w-4" />
              )}
              Reabrir como rascunho
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onRemover}
            aria-label={gerado ? "Remover roteiro" : "Excluir rascunho"}
            data-testid={`roteiro-remover-${roteiro.id}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {mostraReabrir && !permissoes.reabrir && permissoes.motivo_reabrir && (
        <p
          id={`roteiro-reabrir-motivo-${roteiro.id}`}
          className="border-b px-3 py-1.5 text-xs text-muted-foreground"
          data-testid={`roteiro-reabrir-motivo-${roteiro.id}`}
        >
          {permissoes.motivo_reabrir}
        </p>
      )}

      {gerado && (
        <div
          className="flex items-start gap-2 border-b bg-info-light px-3 py-2 text-sm"
          data-testid={`roteiro-travado-${roteiro.id}`}
        >
          <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          <p>
            <b>Roteiro gerado — a lista de imóveis está travada.</b> Ainda dá para mudar horários,
            registrar o resultado de cada visita, cancelar visitas e editar observações. Para
            visitar outro imóvel, crie um novo roteiro.
          </p>
        </div>
      )}

      {gerado && onResponderFeedback && roteiroVencido(roteiro) && (
        <VisitaFeedbackPrompt
          roteiro={roteiro}
          onSubmit={onResponderFeedback}
          pending={feedbackPending}
        />
      )}

      {gerado && (
        <CamposGerado
          key={`${roteiro.data_visita}|${roteiro.hora_visita}`}
          roteiro={roteiro}
          onPatch={onPatchRoteiro}
        />
      )}

      <div className="space-y-3 p-3">
        {roteiro.visitas.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">Nenhum imóvel neste roteiro.</p>
        ) : gerado ? (
          roteiro.visitas.map((visita, i) => (
            <VisitaRow
              key={visita.id}
              visita={visita}
              posicao={i + 1}
              onPatch={(body) => onPatchVisita(visita.id, body)}
              onReagendar={() => onReagendar(visita.id)}
              reagendando={reagendandoVisitaId === visita.id}
              onAbrirNovoRoteiro={() => onAbrirNovoRoteiro(visita.id)}
            />
          ))
        ) : (
          // A draft's list is edited in the editor, not here.
          <ol className="space-y-1" aria-label="Imóveis do rascunho">
            {roteiro.visitas.map((v, i) => (
              <li key={v.id} className="text-sm" data-testid={`rascunho-visita-${v.id}`}>
                <span className="mr-2 tabular-nums text-muted-foreground">{i + 1}.</span>
                <b>{v.codigo}</b>
                {v.imovel?.titulo ? ` · ${v.imovel.titulo}` : ""}
              </li>
            ))}
          </ol>
        )}
      </div>
      {visitadas}
    </div>
  );
}

/** Date and time stay editable on a GERADO roteiro (R3): saved when the field loses focus. */
function CamposGerado({
  roteiro,
  onPatch,
}: {
  roteiro: Roteiro;
  onPatch: (body: RoteiroPatchBody) => void;
}) {
  const [data, setData] = useState(roteiro.data_visita ?? "");
  const [hora, setHora] = useState((roteiro.hora_visita ?? "").slice(0, 5));
  return (
    <div className="flex flex-wrap items-end gap-3 border-b px-3 py-2">
      <div>
        <label
          className="mb-1 block text-xs font-medium text-muted-foreground"
          htmlFor={`roteiro-data-${roteiro.id}`}
        >
          Data da visita
        </label>
        <Input
          id={`roteiro-data-${roteiro.id}`}
          type="date"
          required
          value={data}
          onChange={(e) => setData(e.target.value)}
          // A gerado roteiro keeps its date: the server answers 422 to a null.
          onBlur={() => {
            if (data && data !== (roteiro.data_visita ?? "")) onPatch({ data_visita: data });
            else if (!data) setData(roteiro.data_visita ?? "");
          }}
          data-testid={`roteiro-data-${roteiro.id}`}
        />
      </div>
      <div>
        <label
          className="mb-1 block text-xs font-medium text-muted-foreground"
          htmlFor={`roteiro-hora-${roteiro.id}`}
        >
          Horário
        </label>
        <Input
          id={`roteiro-hora-${roteiro.id}`}
          type="time"
          value={hora}
          onChange={(e) => setHora(e.target.value)}
          onBlur={() => {
            if (hora !== (roteiro.hora_visita ?? "").slice(0, 5)) {
              onPatch({ hora_visita: hora || null });
            }
          }}
          data-testid={`roteiro-hora-${roteiro.id}`}
        />
      </div>
    </div>
  );
}

function VisitaRow({
  visita,
  posicao,
  onPatch,
  onReagendar,
  reagendando,
  onAbrirNovoRoteiro,
}: {
  visita: Visita;
  posicao: number;
  onPatch: (body: VisitaPatchBody) => void;
  onReagendar: () => void;
  reagendando?: boolean;
  onAbrirNovoRoteiro: () => void;
}) {
  const [observacao, setObservacao] = useState(visita.observacao ?? "");
  const sujo = (visita.observacao ?? "") !== observacao;
  // "Cancelada" and "Reagendada" need more than a click: the user's pick is held
  // here until the server can be told everything it requires.
  const [escolha, setEscolha] = useState<StatusVisita | null>(null);
  const [motivo, setMotivo] = useState<CanceladaMotivo | "">(visita.cancelada_motivo ?? "");
  const [por, setPor] = useState<CanceladaPor | "">(visita.cancelada_por ?? "");
  const temProposta = !!visita.proposta_em;
  const aceita = !!visita.proposta_aceita_em;

  const ativo: StatusVisita = escolha ?? visita.status;
  const cancelando = ativo === "cancelada";
  const incompleta = cancelando && (motivo === "" || por === "");

  function escolher(valor: StatusVisita) {
    if (valor === "cancelada") {
      setEscolha("cancelada");
      // Already cancelada on the server: nothing to send until a field changes.
      return;
    }
    if (valor === "reagendada") {
      // R11 refuses `reagendada`; it goes through R12 on the button below.
      setEscolha("reagendada");
      return;
    }
    setEscolha(null);
    onPatch({ status: valor });
  }

  function mudarCancelamento(novoMotivo: CanceladaMotivo | "", novoPor: CanceladaPor | "") {
    setMotivo(novoMotivo);
    setPor(novoPor);
    if (novoMotivo && novoPor) {
      onPatch({ status: "cancelada", cancelada_motivo: novoMotivo, cancelada_por: novoPor });
      setEscolha(null);
    }
  }

  return (
    <div className="space-y-2" data-testid={`visita-${visita.id}`}>
      {visita.imovel ? (
        <ImovelVisitaCard
          id={visita.id}
          imovel={visita.imovel}
          posicao={posicao}
          // The list is LOCKED on a gerado roteiro (`permissoes.editar_imoveis`
          // is false): no handle, no remove.
          sortable={false}
          propostaFeita={temProposta}
          propostaAceita={aceita}
        />
      ) : (
        <p className="rounded-lg border p-3 text-sm">{visita.codigo}</p>
      )}

      <div className="pl-1">
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="group"
          aria-label={`Resultado da visita a ${visita.codigo}`}
        >
          {STATUS_OPCOES.map((opcao) => {
            const pressionado = ativo === opcao.value;
            return (
              <button
                key={opcao.value}
                type="button"
                onClick={() => escolher(opcao.value)}
                aria-pressed={pressionado}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-xs transition-colors",
                  pressionado
                    ? `font-semibold ${opcao.classe}`
                    : "border-border bg-transparent text-muted-foreground hover:bg-muted",
                )}
                data-testid={`visita-status-${opcao.value}-${visita.id}`}
              >
                {opcao.label}
              </button>
            );
          })}
          {visita.resultado_em && (
            <span className="text-xs text-muted-foreground">
              em {formatDate(visita.resultado_em, true)}
            </span>
          )}
        </div>

        {cancelando && (
          <div className="mt-2 flex flex-wrap items-end gap-3" data-testid={`visita-cancelada-${visita.id}`}>
            <div>
              <label
                className="mb-1 block text-xs font-medium text-muted-foreground"
                htmlFor={`motivo-${visita.id}`}
              >
                Motivo *
              </label>
              <select
                id={`motivo-${visita.id}`}
                required
                value={motivo}
                onChange={(e) => mudarCancelamento(e.target.value as CanceladaMotivo | "", por)}
                className="h-9 rounded-md border bg-background px-2 text-sm"
                data-testid={`visita-motivo-${visita.id}`}
              >
                <option value="">Selecione…</option>
                {CANCELADA_MOTIVO.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                className="mb-1 block text-xs font-medium text-muted-foreground"
                htmlFor={`por-${visita.id}`}
              >
                Quem cancelou *
              </label>
              <select
                id={`por-${visita.id}`}
                required
                value={por}
                onChange={(e) => mudarCancelamento(motivo, e.target.value as CanceladaPor | "")}
                className="h-9 rounded-md border bg-background px-2 text-sm"
                data-testid={`visita-cancelada-por-${visita.id}`}
              >
                <option value="">Selecione…</option>
                {CANCELADA_POR.map((m) => (
                  <option key={m.value} value={m.value}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            {incompleta && (
              <p className="text-xs text-muted-foreground" role="status">
                Informe o motivo e quem cancelou para registrar o cancelamento.
              </p>
            )}
          </div>
        )}

        {ativo === "reagendada" && (
          <div
            className="mt-2 rounded-md border bg-info-light px-2.5 py-2 text-sm"
            data-testid={`visita-reagendada-${visita.id}`}
          >
            <p>
              <b>Reagendada não conta como perdida.</b> A nova data vai num novo roteiro.
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {visita.status === "reagendada" ? (
                visita.reagendada_para_visita_id && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onAbrirNovoRoteiro}
                    data-testid={`visita-abrir-novo-${visita.id}`}
                  >
                    Abrir o novo roteiro
                  </Button>
                )
              ) : (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onReagendar}
                    disabled={reagendando}
                    data-testid={`visita-reagendar-${visita.id}`}
                  >
                    {reagendando && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
                    Criar novo roteiro com {visita.codigo}
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    abre um rascunho já com este imóvel
                  </span>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="pl-1">
        <label className="sr-only" htmlFor={`obs-${visita.id}`}>
          Observação da visita a {visita.codigo}
        </label>
        <Textarea
          id={`obs-${visita.id}`}
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          // Saved on blur, not on every keystroke: this is prose, and a PATCH
          // per character would be both noisy and lossy under a slow network.
          // (An observação is allowed on any roteiro status — R11.)
          onBlur={() => {
            if (sujo) onPatch({ observacao: observacao.trim() || null });
          }}
          rows={2}
          placeholder="Como foi? Isso vira o registro no histórico do card."
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
        tom === "ok" && "bg-success-light text-success",
        tom === "ruim" && "bg-danger-light text-destructive",
        tom === "neutro" && "bg-muted text-muted-foreground",
      )}
    >
      {children}
    </span>
  );
}
