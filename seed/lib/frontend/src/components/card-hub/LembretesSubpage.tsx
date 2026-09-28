/**
 * LembretesSubpage — the card's "Lembretes" subpage: many ad-hoc reminders
 * per card, each with a título, a due date/time in América/São Paulo and an
 * optional responsável, listed pending-first (overdue highlighted) then
 * concluded. Backend: `noctusai_lib.domain.card_hub.services`
 * (`CardHubConfig.lembretes_crud` opt-in — igig turns it on; social-wiring
 * does not mount this subpage).
 *
 * Half-shipped before this: the table, the wire types and the scheduler's
 * delivery drain (`app/services/notificacoes.py::processar_lembretes_pendentes`)
 * already existed, but no surface let anyone CREATE a lembrete — this is
 * that surface.
 *
 * Presentational only, same contract as the rest of `card-hub/**`
 * (PROJECT.md §0): the product's hook (igig: `useLembretesSubpage`) owns the
 * data + mutations; this file owns only how it looks.
 *
 * MOBILE-FIRST (R0): the create/edit form and every row action meet the 40px
 * touch floor (`TokenCheckbox`/`TooltipIconButton` already do); "Excluir"
 * needs a SECOND tap ("Confirmar exclusão?") rather than a modal dialog — a
 * subpage renders inside the card's own scroll area, with no sheet chrome of
 * its own to host one in, and the two-tap pattern still satisfies
 * "confirmation dialog for destructive actions" without a third, competing,
 * full-screen surface on a 360px phone.
 */
import { useEffect, useState } from "react";
import { Bell, Pencil, Plus, Trash2, X } from "lucide-react";

import { CardHubButton as Button } from "../../design-system/ui/card-hub-button";
import { CardHubInput as Input } from "../../design-system/ui/card-hub-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../design-system/ui/select";
import { Skeleton } from "../../design-system/ui/Skeleton";
import { cn } from "../../utils";

import { dataHoraLocalParaIsoSP, formatarDataHoraSP, isoParaDataHoraLocalSP } from "./format";
import { TokenCheckbox } from "./TokenCheckbox";
import { TooltipIconButton } from "./TooltipIconButton";
import type { Lembrete, LembreteCreateBody, LembreteUpdateBody, Membro } from "./types";

const SEM_RESPONSAVEL = "__none__";

export interface LembretesSubpageProps {
  lembretes: Lembrete[];
  /** No lembretes yet — the FIRST load only; ignored once rows exist. */
  loading: boolean;
  refreshing?: boolean;
  /** pt-BR error message, or `null`. */
  error?: string | null;
  /** Who may be assigned — igig: the org's active `profissional` rows. */
  responsaveis: Membro[];
  onCreate: (body: LembreteCreateBody) => void;
  onUpdate: (id: string, body: LembreteUpdateBody) => void;
  onDelete: (id: string) => void;
  creating?: boolean;
  /** The id currently being patched or deleted — disables just that row. */
  savingId?: string | null;
}

interface FormState {
  titulo: string;
  dataHora: string;
  responsavelId: string;
}

const FORM_VAZIO: FormState = { titulo: "", dataHora: "", responsavelId: SEM_RESPONSAVEL };

export function LembretesSubpage({
  lembretes,
  loading,
  refreshing,
  error,
  responsaveis,
  onCreate,
  onUpdate,
  onDelete,
  creating,
  savingId,
}: LembretesSubpageProps) {
  const [criando, setCriando] = useState(false);
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [confirmandoId, setConfirmandoId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VAZIO);

  // A row mid-edit that gets deleted elsewhere (another tab) must not leave
  // the form open on a lembrete that no longer exists.
  useEffect(() => {
    if (editandoId && !lembretes.some((l) => l.id === editandoId)) setEditandoId(null);
  }, [lembretes, editandoId]);

  function abrirCriacao() {
    setEditandoId(null);
    setForm(FORM_VAZIO);
    setCriando(true);
  }

  function abrirEdicao(l: Lembrete) {
    setCriando(false);
    setConfirmandoId(null);
    setForm({
      titulo: l.titulo,
      dataHora: isoParaDataHoraLocalSP(l.dispara_em),
      responsavelId: l.responsavel?.id ?? SEM_RESPONSAVEL,
    });
    setEditandoId(l.id);
  }

  function fecharFormulario() {
    setCriando(false);
    setEditandoId(null);
    setForm(FORM_VAZIO);
  }

  function submeter() {
    const titulo = form.titulo.trim();
    if (!titulo || !form.dataHora) return;
    const responsavel_id = form.responsavelId === SEM_RESPONSAVEL ? null : form.responsavelId;
    if (editandoId) {
      onUpdate(editandoId, {
        titulo,
        dispara_em: dataHoraLocalParaIsoSP(form.dataHora),
        responsavel_id,
      });
    } else {
      onCreate({ titulo, dispara_em: dataHoraLocalParaIsoSP(form.dataHora), responsavel_id });
    }
    fecharFormulario();
  }

  const formularioAberto = criando || !!editandoId;
  const agora = Date.now();
  const pendentes = lembretes.filter((l) => !l.concluido);
  const concluidos = lembretes.filter((l) => l.concluido);

  if (loading) {
    return (
      <div className="space-y-2" data-testid="lembretes-loading">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="lembretes-subpage">
      {error && (
        <p role="alert" className="text-sm text-destructive" data-testid="lembretes-error">
          {error}
        </p>
      )}

      {!formularioAberto && (
        <Button
          variant="outline"
          onClick={abrirCriacao}
          className="max-sm:min-h-10 max-sm:w-full"
          data-testid="lembrete-novo-btn"
        >
          <Plus className="mr-1 h-4 w-4" aria-hidden="true" /> Novo lembrete
        </Button>
      )}

      {formularioAberto && (
        <div
          className="space-y-3 rounded-lg border border-border p-3"
          data-testid={editandoId ? "lembrete-form-editar" : "lembrete-form-criar"}
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="lembrete-titulo">
              Título
            </label>
            <Input
              id="lembrete-titulo"
              value={form.titulo}
              onChange={(e) => setForm((f) => ({ ...f, titulo: e.target.value }))}
              placeholder="Ex.: Ligar para confirmar a arte"
              autoFocus
              data-testid="lembrete-titulo-input"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground" htmlFor="lembrete-data-hora">
              Data e hora (América/São Paulo)
            </label>
            <Input
              id="lembrete-data-hora"
              type="datetime-local"
              value={form.dataHora}
              onChange={(e) => setForm((f) => ({ ...f, dataHora: e.target.value }))}
              className="max-sm:min-h-10"
              data-testid="lembrete-data-hora-input"
            />
          </div>
          {responsaveis.length > 0 && (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Responsável</label>
              <Select
                value={form.responsavelId}
                onValueChange={(v) => setForm((f) => ({ ...f, responsavelId: v }))}
              >
                <SelectTrigger className="max-sm:min-h-10" data-testid="lembrete-responsavel-select">
                  <SelectValue placeholder="Nenhum" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SEM_RESPONSAVEL}>Nenhum</SelectItem>
                  {responsaveis.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nome}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              className="max-sm:min-h-10 max-sm:flex-1"
              disabled={!form.titulo.trim() || !form.dataHora || creating || !!savingId}
              onClick={submeter}
              data-testid="lembrete-salvar-btn"
            >
              {editandoId ? "Salvar" : "Adicionar"}
            </Button>
            <Button
              variant="outline"
              className="max-sm:min-h-10"
              onClick={fecharFormulario}
              data-testid="lembrete-cancelar-btn"
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {lembretes.length === 0 && !formularioAberto && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="lembretes-vazio">
          <Bell className="h-4 w-4" aria-hidden="true" /> Nenhum lembrete neste cartão ainda.
        </p>
      )}

      {pendentes.length > 0 && (
        <ul className="space-y-2" data-testid="lembretes-pendentes" aria-label="Lembretes pendentes">
          {pendentes.map((l) => (
            <LembreteRow
              key={l.id}
              lembrete={l}
              atrasado={new Date(l.dispara_em).getTime() < agora}
              saving={savingId === l.id}
              confirmandoExclusao={confirmandoId === l.id}
              onToggleConcluido={(concluido) => onUpdate(l.id, { concluido })}
              onEditar={() => abrirEdicao(l)}
              onPedirExclusao={() => setConfirmandoId(l.id)}
              onCancelarExclusao={() => setConfirmandoId(null)}
              onConfirmarExclusao={() => {
                setConfirmandoId(null);
                onDelete(l.id);
              }}
            />
          ))}
        </ul>
      )}

      {concluidos.length > 0 && (
        <ul className="space-y-2 opacity-70" data-testid="lembretes-concluidos" aria-label="Lembretes concluídos">
          {concluidos.map((l) => (
            <LembreteRow
              key={l.id}
              lembrete={l}
              atrasado={false}
              saving={savingId === l.id}
              confirmandoExclusao={confirmandoId === l.id}
              onToggleConcluido={(concluido) => onUpdate(l.id, { concluido })}
              onEditar={() => abrirEdicao(l)}
              onPedirExclusao={() => setConfirmandoId(l.id)}
              onCancelarExclusao={() => setConfirmandoId(null)}
              onConfirmarExclusao={() => {
                setConfirmandoId(null);
                onDelete(l.id);
              }}
            />
          ))}
        </ul>
      )}

      {refreshing && (
        <p className="text-xs text-muted-foreground" data-testid="lembretes-refreshing">
          Atualizando…
        </p>
      )}
    </div>
  );
}

interface LembreteRowProps {
  lembrete: Lembrete;
  atrasado: boolean;
  saving: boolean;
  confirmandoExclusao: boolean;
  onToggleConcluido: (concluido: boolean) => void;
  onEditar: () => void;
  onPedirExclusao: () => void;
  onCancelarExclusao: () => void;
  onConfirmarExclusao: () => void;
}

function LembreteRow({
  lembrete,
  atrasado,
  saving,
  confirmandoExclusao,
  onToggleConcluido,
  onEditar,
  onPedirExclusao,
  onCancelarExclusao,
  onConfirmarExclusao,
}: LembreteRowProps) {
  return (
    <li
      className={cn(
        "flex items-start gap-3 rounded-lg border p-3",
        atrasado ? "border-destructive/50 bg-destructive/5" : "border-border",
      )}
      data-testid={`lembrete-row-${lembrete.id}`}
    >
      <TokenCheckbox
        checked={lembrete.concluido}
        onCheckedChange={onToggleConcluido}
        disabled={saving}
        label={lembrete.concluido ? "Reabrir lembrete" : "Marcar lembrete como concluído"}
        testId={`lembrete-concluido-${lembrete.id}`}
        className="mt-1"
      />
      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-sm font-medium", lembrete.concluido && "line-through")}>
          {lembrete.titulo}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatarDataHoraSP(lembrete.dispara_em)}
          {atrasado && (
            <span className="ml-2 font-medium text-destructive" data-testid={`lembrete-atrasado-${lembrete.id}`}>
              Atrasado
            </span>
          )}
          {lembrete.responsavel && <span className="ml-2">· {lembrete.responsavel.nome}</span>}
        </p>
      </div>
      {confirmandoExclusao ? (
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="destructive"
            size="sm"
            className="max-sm:min-h-10"
            onClick={onConfirmarExclusao}
            data-testid={`lembrete-confirmar-excluir-${lembrete.id}`}
          >
            Confirmar exclusão?
          </Button>
          <TooltipIconButton
            label="Cancelar"
            icon={X}
            onClick={onCancelarExclusao}
            testId={`lembrete-cancelar-excluir-${lembrete.id}`}
          />
        </div>
      ) : (
        <div className="flex shrink-0 items-center gap-1">
          <TooltipIconButton
            label={`Editar lembrete ${lembrete.titulo}`}
            icon={Pencil}
            disabled={saving}
            onClick={onEditar}
            testId={`lembrete-editar-${lembrete.id}`}
          />
          <TooltipIconButton
            label={`Excluir lembrete ${lembrete.titulo}`}
            icon={Trash2}
            disabled={saving}
            onClick={onPedirExclusao}
            testId={`lembrete-excluir-${lembrete.id}`}
          />
        </div>
      )}
    </li>
  );
}
