/**
 * `<ContratosPanel/>` — the card's Contratos subpage.
 *
 * Every atendimento needs somewhere to keep its legal paperwork: uploaded
 * today, auto-generated later — both land in the SAME list, the latter
 * marked "Gerado automaticamente" rather than split into a second surface.
 * Legal works in revisions, so each contract is a STATUS plus a VERSION
 * history, not a single file.
 *
 * 🔴 THE CREATE DIALOG IS A SIBLING, NOT A CHILD
 * -----------------------------------------------
 * "Novo contrato" only flips a boolean the caller owns
 * (`NovoContratoDialog` renders top-level in `ClienteDetailModal`, same
 * reason `CriarRoteiroDialog` does) — a Dialog nested inside
 * `ClienteCardDialog`'s own Dialog content fights the outer focus trap and
 * scroll lock.
 *
 * "Nova versão" on an existing contract does NOT reopen that dialog: it is a
 * single required file with no other fields to collect, so it is a plain
 * hidden input behind a button — the same shape `FinanciamentoPanel`'s
 * per-slot upload uses — rather than a second modal for one field.
 *
 * 🔴 `renderMatriculaAtos` IS A RENDER PROP, NOT AN IMPORT — same reason
 * `ClienteDetailModal.renderDocumentosDePessoa` is one. This file stays
 * presentational (S3): the "Descrição do imóvel (matrícula)" section fetches
 * — `useMatriculaExtracoes` / `useMatriculaAtos` / `useContratoAtos` /
 * `useDefinirContratoAtos` all live behind it — and a `card/**` file may not
 * call those hooks directly. The caller supplies `MatriculaAtosContainer`
 * (in `components/`, not `components/card/`) through this callback instead.
 *
 * 🔴 ASSINATURA DIGITAL (signature-integration-CONTRACT §4)
 * -----------------------------------------------------------
 * `assinaturas` is a lookup by `contrato.id`, fetched by `ContratosContainer`
 * (`useAssinaturas`) — same S3 discipline as everything above. Two DIFFERENT
 * existence checks read it, on purpose (see `envelopeVivo`'s docblock in
 * `useContratos.ts`):
 *   - "Enviar para assinatura" shows only on a `gerado` current version AND
 *     only while there is no LIVE envelope (`pendente`/`parcial`) — a
 *     cancelled/expired one may be superseded by a fresh send.
 *   - the status `<Select/>` is disabled the moment ANY envelope exists at
 *     all, live or not — the manual `enviado_assinatura`/`assinado` picks are
 *     retired for good once a contract enters this flow.
 * The "Enviar para assinatura" DIALOG itself (`EnviarAssinaturaDialog`) is
 * mounted by `ContratosContainer`, not here — it needs compradores/vendedores/
 * testemunhas data this presentational file must not fetch; this panel only
 * calls `onAbrirEnvioAssinatura` to open it. "Cancelar envio" is a plain
 * motivo dialog (`_CancelarEnvioDialog` below) since it needs no such data —
 * same reasoning as `excluirContrato`'s `window.prompt`, but with a length
 * gate (§3.3: 3..500 chars) a bare `prompt()` cannot express well.
 */
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileDown,
  FileType2,
  ExternalLink,
  Eye,
  History,
  Loader2,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { TooltipIconButton } from "@noctusai/lib/components";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { ContratoModalidadeSection } from "@/components/card/ContratoModalidadeSection";
import type {
  AssinaturaEntry,
  AssinaturaOut,
  ContratoOut,
  ContratoStatus,
  ModalidadeAssinatura,
  VersaoOut,
} from "@/hooks/useContratos";
import {
  CONTRATO_ACCEPT_ATTR,
  CONTRATO_STATUS_OPTIONS,
  MODELO_LABEL,
  STATUS_ASSINATURA_LABEL,
  STATUS_LABEL,
  envelopeVivo,
  formatBytes,
  validateContratoFile,
} from "@/hooks/useContratos";

interface Props {
  contratos: ContratoOut[] | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  errorMessage?: string | null;
  onRetry: () => void;
  onNovoContrato: () => void;
  /** "Gerar contrato" — starts a contract the generator fills. Optional:
   *  the button is omitted while the caller has not wired it. */
  onGerarContrato?: () => void;
  iniciandoGeracao?: boolean;
  /** The contract the last "Gerar contrato" click created — its matrícula
   *  and generator sections open on mount, since those are the next steps. */
  contratoIniciadoId?: string | null;
  addingVersaoContratoId?: string | null;
  patchingContratoId?: string | null;
  deletingVersaoId?: string | null;
  deletingContratoId?: string | null;
  /** The `versao.id` currently minting a .docx URL — narrower than a single
   *  `isPending`, since Abrir/Baixar (pdf) and "Baixar .docx" share the same
   *  underlying mutation. */
  baixandoDocxVersaoId?: string | null;
  onAddVersao: (contratoId: string, file: File) => void;
  onPatchStatus: (contratoId: string, status: ContratoStatus) => void;
  /** Migration 114. `assinatura_data`: `YYYY-MM-DD` or `null` to clear.
   *  `prazo_pendencias_dias`: `null` restores the office default (10 days) —
   *  see `ContratoPatch`. Always sends BOTH fields together (the row's whole
   *  editable pair), never a bare single-field PATCH. */
  onPatchPrazos: (
    contratoId: string,
    patch: { assinatura_data: string | null; prazo_pendencias_dias: number | null },
  ) => void;
  onDeleteVersao: (contratoId: string, versaoId: string, motivo: string) => void;
  onDeleteContrato: (contratoId: string, motivo: string) => void;
  onOpen: (contratoId: string, versaoId: string, formato?: "pdf" | "docx") => void;
  onDownload: (contratoId: string, versaoId: string, formato?: "pdf" | "docx") => void;
  /** Renders the "Descrição do imóvel (matrícula)" section for one contract.
   *  Optional — omitted entirely (not even the collapsible header) while the
   *  caller has not wired it, so this panel never breaks when nobody has. */
  renderMatriculaAtos?: (contratoId: string) => ReactNode;
  /** Renders the "Gerar contrato" section (F5) for one contract. `aberto` is
   *  whether THIS card's collapsible is open — the caller (`GeradorContratoContainer`)
   *  uses it to gate the readiness fetch, since Radix mounts collapsible
   *  content up front (see the container's header note); it is not implied
   *  by this callback being invoked at all. Same optional-omission discipline
   *  as `renderMatriculaAtos`. */
  renderGeradorContrato?: (contratoId: string, aberto: boolean) => ReactNode;
  /** Renders the "Proveniência" section (`sw-extraction-contract`) for one
   *  contract — data lineage per field: where the value came from and its
   *  confirmation state. `aberto` gates the caller's lazy fetch, same
   *  discipline as `renderGeradorContrato`. Optional — omitted entirely
   *  while the caller has not wired it. */
  renderProveniencia?: (contratoId: string, aberto: boolean) => ReactNode;
  /** Renders the "Testemunhas do contrato" selection (migration 168) for one
   *  contract — a count selector plus that many registered-witness picks.
   *  `aberto` gates the caller's lazy fetch, same discipline as
   *  `renderGeradorContrato`. Optional — omitted entirely while the caller
   *  has not wired it. */
  renderTestemunhasSelect?: (contratoId: string, aberto: boolean) => ReactNode;
  /** `contrato.id` → its `useAssinaturas` entry. A missing key means "never
   *  eligible" (no `gerado` version ever existed) and reads the same as a
   *  resolved `data: null` — see `_AssinaturaSection`. */
  assinaturas?: Record<string, AssinaturaEntry>;
  /** Opens `EnviarAssinaturaDialog` (mounted by the caller) for this contract
   *  + version. Optional — the button is omitted while not wired, same
   *  discipline as `onGerarContrato`. */
  onAbrirEnvioAssinatura?: (contratoId: string, versaoId: string) => void;
  onCancelarAssinatura?: (contratoId: string, motivo: string) => void;
  cancelandoAssinaturaContratoId?: string | null;
  /** Migration 151 (owner directive 2026-09-22). A UI convenience ONLY —
   *  same posture `ConflitosPendentesPanel`'s own `isAdmin` already takes:
   *  the server's `PUT .../processo-legado` reads the TRUSTED
   *  `noctus_users` row and 403s a spoofed claim regardless of this. Gates
   *  the "Processo anterior à plataforma" checkbox; the amber badge it
   *  sets is visible to everyone. Defaults to `false` — the checkbox is
   *  omitted, never mistakenly shown, while a caller hasn't wired it. */
  isAdmin?: boolean;
  onSetProcessoLegado?: (contratoId: string, ativo: boolean, motivo?: string) => void;
  settingProcessoLegadoContratoId?: string | null;
  /** Migration 157 — the Digital/Física toggle. Omitted ⇒ the toggle renders
   *  read-only (disabled), never a control that does nothing. */
  onPatchModalidade?: (contratoId: string, modalidade: ModalidadeAssinatura) => void;
  /** Migration 157 — "Marcar como assinado" (+ optional scanned PDF) for a
   *  física contract. */
  onMarcarAssinadoFisico?: (contratoId: string, file: File | null) => void;
  marcandoAssinadoContratoId?: string | null;
}

export default function ContratosPanel({
  contratos,
  showSkeleton,
  isRefreshing,
  isError,
  errorMessage,
  onRetry,
  onNovoContrato,
  onGerarContrato,
  iniciandoGeracao = false,
  contratoIniciadoId,
  addingVersaoContratoId,
  patchingContratoId,
  deletingVersaoId,
  deletingContratoId,
  baixandoDocxVersaoId,
  onAddVersao,
  onPatchStatus,
  onPatchPrazos,
  onDeleteVersao,
  onDeleteContrato,
  onOpen,
  onDownload,
  renderMatriculaAtos,
  renderGeradorContrato,
  renderProveniencia,
  renderTestemunhasSelect,
  assinaturas = {},
  onAbrirEnvioAssinatura,
  onCancelarAssinatura,
  cancelandoAssinaturaContratoId,
  isAdmin = false,
  onSetProcessoLegado,
  settingProcessoLegadoContratoId,
  onPatchModalidade,
  onMarcarAssinadoFisico,
  marcandoAssinadoContratoId,
}: Props) {
  const lista = contratos ?? [];

  return (
    <div className="space-y-4" data-testid="contratos-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Contratos</h3>
        <div className="flex items-center gap-2">
          {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {onGerarContrato && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={iniciandoGeracao}
              onClick={onGerarContrato}
              data-testid="contrato-gerar-btn"
            >
              {iniciandoGeracao ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              )}
              Gerar contrato
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            onClick={onNovoContrato}
            data-testid="contrato-novo-btn"
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Novo contrato
          </Button>
        </div>
      </div>

      {isError && (
        <div
          className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-3"
          data-testid="contratos-erro"
        >
          <p className="flex items-center gap-2 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {errorMessage ?? "Não foi possível carregar os contratos."}
          </p>
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        </div>
      )}

      {showSkeleton && (
        <div className="space-y-2" data-testid="contratos-skeleton">
          {[0, 1].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-md border bg-muted/40" />
          ))}
        </div>
      )}

      {!showSkeleton && !isError && lista.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid="contratos-vazio">
          Nenhum contrato neste card ainda. Clique em “Gerar contrato” para
          gerá-lo a partir dos dados do card, ou envie o .docx ou PDF.
        </p>
      )}

      {!showSkeleton && lista.length > 0 && (
        <div className="space-y-3" data-testid="contratos-lista">
          {lista.map((contrato) => (
            <ContratoCard
              key={contrato.id}
              contrato={contrato}
              addingVersao={addingVersaoContratoId === contrato.id}
              patching={patchingContratoId === contrato.id}
              deletingVersaoId={deletingVersaoId}
              deletingContrato={deletingContratoId === contrato.id}
              baixandoDocxVersaoId={baixandoDocxVersaoId}
              onAddVersao={(file) => onAddVersao(contrato.id, file)}
              onPatchStatus={(status) => onPatchStatus(contrato.id, status)}
              onPatchPrazos={(patch) => onPatchPrazos(contrato.id, patch)}
              onDeleteVersao={(versaoId, motivo) => onDeleteVersao(contrato.id, versaoId, motivo)}
              onDeleteContrato={(motivo) => onDeleteContrato(contrato.id, motivo)}
              onOpen={(versaoId, formato) => onOpen(contrato.id, versaoId, formato)}
              onDownload={(versaoId, formato) => onDownload(contrato.id, versaoId, formato)}
              renderMatriculaAtos={renderMatriculaAtos}
              renderGeradorContrato={renderGeradorContrato}
              renderProveniencia={renderProveniencia}
              renderTestemunhasSelect={renderTestemunhasSelect}
              recemIniciado={contratoIniciadoId === contrato.id}
              assinaturaEntry={assinaturas[contrato.id]}
              onAbrirEnvioAssinatura={
                onAbrirEnvioAssinatura
                  ? (versaoId) => onAbrirEnvioAssinatura(contrato.id, versaoId)
                  : undefined
              }
              onCancelarAssinatura={
                onCancelarAssinatura
                  ? (motivo) => onCancelarAssinatura(contrato.id, motivo)
                  : undefined
              }
              cancelandoAssinatura={cancelandoAssinaturaContratoId === contrato.id}
              isAdmin={isAdmin}
              onSetProcessoLegado={
                onSetProcessoLegado
                  ? (ativo, motivo) => onSetProcessoLegado(contrato.id, ativo, motivo)
                  : undefined
              }
              settingProcessoLegado={settingProcessoLegadoContratoId === contrato.id}
              onPatchModalidade={
                onPatchModalidade ? (m) => onPatchModalidade(contrato.id, m) : undefined
              }
              onMarcarAssinadoFisico={
                onMarcarAssinadoFisico
                  ? (file) => onMarcarAssinadoFisico(contrato.id, file)
                  : undefined
              }
              marcandoAssinado={marcandoAssinadoContratoId === contrato.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ContratoCard({
  contrato,
  addingVersao,
  patching,
  deletingVersaoId,
  deletingContrato,
  baixandoDocxVersaoId,
  onAddVersao,
  onPatchStatus,
  onPatchPrazos,
  onDeleteVersao,
  onDeleteContrato,
  onOpen,
  onDownload,
  renderMatriculaAtos,
  renderGeradorContrato,
  renderProveniencia,
  renderTestemunhasSelect,
  recemIniciado = false,
  assinaturaEntry,
  onAbrirEnvioAssinatura,
  onCancelarAssinatura,
  cancelandoAssinatura = false,
  isAdmin = false,
  onSetProcessoLegado,
  settingProcessoLegado = false,
  onPatchModalidade,
  onMarcarAssinadoFisico,
  marcandoAssinado = false,
}: {
  contrato: ContratoOut;
  addingVersao: boolean;
  patching: boolean;
  deletingVersaoId?: string | null;
  deletingContrato: boolean;
  baixandoDocxVersaoId?: string | null;
  onAddVersao: (file: File) => void;
  onPatchStatus: (status: ContratoStatus) => void;
  onPatchPrazos: (patch: {
    assinatura_data: string | null;
    prazo_pendencias_dias: number | null;
  }) => void;
  onDeleteVersao: (versaoId: string, motivo: string) => void;
  onDeleteContrato: (motivo: string) => void;
  onOpen: (versaoId: string, formato?: "pdf" | "docx") => void;
  onDownload: (versaoId: string, formato?: "pdf" | "docx") => void;
  renderMatriculaAtos?: (contratoId: string) => ReactNode;
  renderGeradorContrato?: (contratoId: string, aberto: boolean) => ReactNode;
  renderProveniencia?: (contratoId: string, aberto: boolean) => ReactNode;
  renderTestemunhasSelect?: (contratoId: string, aberto: boolean) => ReactNode;
  recemIniciado?: boolean;
  /** This contract's `useAssinaturas` entry — `undefined` when the contract
   *  was never eligible (no `gerado` version ever existed). */
  assinaturaEntry?: AssinaturaEntry;
  onAbrirEnvioAssinatura?: (versaoId: string) => void;
  onCancelarAssinatura?: (motivo: string) => void;
  cancelandoAssinatura?: boolean;
  isAdmin?: boolean;
  onSetProcessoLegado?: (ativo: boolean, motivo?: string) => void;
  settingProcessoLegado?: boolean;
  onPatchModalidade?: (modalidade: ModalidadeAssinatura) => void;
  onMarcarAssinadoFisico?: (file: File | null) => void;
  marcandoAssinado?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [historicoAberto, setHistoricoAberto] = useState(false);
  const [processoLegadoDialogOpen, setProcessoLegadoDialogOpen] = useState(false);
  const [matriculaAberta, setMatriculaAberta] = useState(recemIniciado);
  const [geradorAberto, setGeradorAberto] = useState(recemIniciado);
  const [provenienciaAberta, setProvenienciaAberta] = useState(false);
  const [testemunhasAberta, setTestemunhasAberta] = useState(false);

  // Local drafts for the two migration-114 fields — a plain string, parsed
  // only on save. `prazo_pendencias_dias` null reads as "" (the placeholder
  // below names the office default, never a fake "0").
  const [assinaturaData, setAssinaturaData] = useState(contrato.assinatura_data ?? "");
  const [prazoPendencias, setPrazoPendencias] = useState(
    contrato.prazo_pendencias_dias == null ? "" : String(contrato.prazo_pendencias_dias),
  );
  useEffect(() => {
    setAssinaturaData(contrato.assinatura_data ?? "");
    setPrazoPendencias(
      contrato.prazo_pendencias_dias == null ? "" : String(contrato.prazo_pendencias_dias),
    );
  }, [contrato.assinatura_data, contrato.prazo_pendencias_dias]);

  const prazoInvalido = prazoPendencias.trim() !== "" && Number(prazoPendencias) <= 0;
  const prazosSujo =
    assinaturaData !== (contrato.assinatura_data ?? "") ||
    prazoPendencias !== (contrato.prazo_pendencias_dias == null ? "" : String(contrato.prazo_pendencias_dias));

  function salvarPrazos() {
    if (prazoInvalido) return;
    onPatchPrazos({
      assinatura_data: assinaturaData || null,
      prazo_pendencias_dias: prazoPendencias.trim() === "" ? null : Number(prazoPendencias),
    });
  }

  const atual = contrato.versao_atual;
  // numero DESC — the newest revision reads first.
  const versoesOrdenadas = [...contrato.versoes].sort((a, b) => b.numero - a.numero);
  const gerado = contrato.origem === "gerado";
  const soUmaVersao = contrato.versoes.length <= 1;
  // 🔴 "does an envelope exist AT ALL" — deliberately NOT `envelopeVivo`. See
  // this file's header note: the status select is retired for good the
  // moment a contract enters the signature flow, live or not. Reads
  // `!= null` on `.data`, not on the entry itself: while unresolved
  // (`data === undefined`) the select stays enabled — disabling it on a
  // guess would be the same lying-loading-state shape `showSkeleton`/
  // `isRefreshing` exist to avoid.
  const envelopeExiste = assinaturaEntry?.data != null;

  function handleArquivo(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    // Reset so choosing the SAME file twice still fires a change.
    e.target.value = "";
    if (!file) return;
    const erro = validateContratoFile(file);
    if (erro) {
      setFileError(erro);
      return;
    }
    setFileError(null);
    onAddVersao(file);
  }

  function excluirContrato() {
    const motivo = window.prompt("Por que este contrato está sendo removido?");
    if (motivo && motivo.trim()) onDeleteContrato(motivo.trim());
  }

  function excluirVersao(versaoId: string) {
    const motivo = window.prompt("Por que esta versão está sendo removida?");
    if (motivo && motivo.trim()) onDeleteVersao(versaoId, motivo.trim());
  }

  return (
    <Card data-testid={`contrato-card-${contrato.id}`}>
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-0.5">
            <CardTitle className="text-sm font-medium">{contrato.titulo}</CardTitle>
            <p className="text-xs text-muted-foreground">{MODELO_LABEL[contrato.modelo]}</p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-1.5">
            {gerado && (
              <Badge
                variant="secondary"
                className="gap-1 text-[10px]"
                data-testid={`contrato-gerado-${contrato.id}`}
              >
                <Sparkles className="h-3 w-3" />
                Gerado automaticamente
              </Badge>
            )}
            {contrato.processo_legado && (
              <Badge
                variant="outline"
                className="gap-1 border-amber-300 bg-amber-50 text-[10px] text-amber-800"
                data-testid={`contrato-processo-legado-badge-${contrato.id}`}
              >
                <History className="h-3 w-3" />
                Processo anterior à plataforma
              </Badge>
            )}
            <div className="flex flex-col items-end gap-0.5">
              <Select
                value={contrato.status}
                onValueChange={(v) => onPatchStatus(v as ContratoStatus)}
                disabled={patching || envelopeExiste}
              >
                <SelectTrigger
                  className="h-8 w-[200px]"
                  data-testid={`contrato-status-${contrato.id}`}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONTRATO_STATUS_OPTIONS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {STATUS_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {envelopeExiste && (
                <p
                  className="text-[10px] text-muted-foreground"
                  data-testid={`contrato-status-assinatura-hint-${contrato.id}`}
                >
                  definido pela plataforma de assinatura
                </p>
              )}
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {atual ? (
          <_VersaoAtualRow
            contratoId={contrato.id}
            versao={atual}
            baixandoDocx={baixandoDocxVersaoId === atual.id}
            onOpen={onOpen}
            onDownload={onDownload}
          />
        ) : (
          <p className="text-xs text-muted-foreground">Sem versão enviada.</p>
        )}

        {/* Migration 157 — the Digital/Física gate. Digital keeps the
            existing send-for-signature section verbatim; Física replaces it
            with print + "Marcar como assinado" and never offers a send. */}
        <ContratoModalidadeSection
          contrato={contrato}
          envelopeVivo={envelopeVivo(assinaturaEntry?.data)}
          patching={patching}
          onPatchModalidade={onPatchModalidade}
          onBaixarImpressao={(versaoId) => onDownload(versaoId, "pdf")}
          onMarcarAssinado={onMarcarAssinadoFisico}
          marcandoAssinado={marcandoAssinado}
          digitalContent={
            atual ? (
              <_AssinaturaSection
                contratoId={contrato.id}
                versao={atual}
                entry={assinaturaEntry}
                onAbrirEnvio={onAbrirEnvioAssinatura}
                onCancelar={onCancelarAssinatura}
                cancelando={cancelandoAssinatura}
              />
            ) : null
          }
        />

        <div
          className="grid gap-3 rounded-md border p-2.5 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          data-testid={`contrato-prazos-${contrato.id}`}
        >
          <div className="space-y-1.5">
            <Label htmlFor={`contrato-assinatura-data-${contrato.id}`}>
              Data de assinatura
            </Label>
            <Input
              id={`contrato-assinatura-data-${contrato.id}`}
              type="date"
              value={assinaturaData}
              onChange={(e) => setAssinaturaData(e.target.value)}
              data-testid={`contrato-assinatura-data-${contrato.id}`}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`contrato-prazo-pendencias-${contrato.id}`}>
              Prazo de pendências (dias)
            </Label>
            <Input
              id={`contrato-prazo-pendencias-${contrato.id}`}
              type="number"
              min={1}
              placeholder="Padrão do escritório (10)"
              value={prazoPendencias}
              onChange={(e) => setPrazoPendencias(e.target.value)}
              data-testid={`contrato-prazo-pendencias-${contrato.id}`}
            />
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!prazosSujo || prazoInvalido || patching}
            onClick={salvarPrazos}
            data-testid={`contrato-prazos-salvar-${contrato.id}`}
          >
            {patching ? "Salvando…" : "Salvar"}
          </Button>
          {prazoInvalido && (
            <p
              className="text-xs text-destructive sm:col-span-3"
              data-testid={`contrato-prazo-erro-${contrato.id}`}
            >
              O prazo de pendências deve ser um número inteiro de dias maior que zero.
            </p>
          )}
        </div>

        {isAdmin && onSetProcessoLegado && (
          <div
            className="flex items-start gap-2 rounded-md border p-2.5"
            data-testid={`contrato-processo-legado-${contrato.id}`}
          >
            <Checkbox
              id={`contrato-processo-legado-checkbox-${contrato.id}`}
              checked={contrato.processo_legado}
              disabled={settingProcessoLegado}
              onCheckedChange={(checked) => {
                if (checked === true) {
                  setProcessoLegadoDialogOpen(true);
                } else {
                  onSetProcessoLegado(false);
                }
              }}
              data-testid={`contrato-processo-legado-checkbox-${contrato.id}`}
            />
            <Label
              htmlFor={`contrato-processo-legado-checkbox-${contrato.id}`}
              className="text-xs font-normal leading-snug text-muted-foreground"
            >
              Processo anterior à plataforma — dispensar prazos de certidões
            </Label>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={addingVersao || contrato.status === "cancelado"}
            onClick={() => inputRef.current?.click()}
            data-testid={`contrato-nova-versao-${contrato.id}`}
          >
            {addingVersao ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="mr-1.5 h-3.5 w-3.5" />
            )}
            Nova versão
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={deletingContrato}
            onClick={excluirContrato}
            data-testid={`contrato-excluir-${contrato.id}`}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Excluir
          </Button>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept={CONTRATO_ACCEPT_ATTR}
            data-testid={`contrato-input-${contrato.id}`}
            onChange={handleArquivo}
          />
        </div>
        {fileError && (
          <p className="text-xs text-destructive" data-testid={`contrato-arquivo-erro-${contrato.id}`}>
            {fileError}
          </p>
        )}

        {contrato.versoes.length > 0 && (
          <Collapsible open={historicoAberto} onOpenChange={setHistoricoAberto}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                data-testid={`contrato-historico-toggle-${contrato.id}`}
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${historicoAberto ? "rotate-180" : ""}`}
                />
                {contrato.versoes.length} versão{contrato.versoes.length > 1 ? "ões" : ""}
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 space-y-1.5">
              {versoesOrdenadas.map((versao) => (
                <VersaoRow
                  key={versao.id}
                  versao={versao}
                  deleting={deletingVersaoId === versao.id}
                  podeExcluir={!soUmaVersao}
                  baixandoDocx={baixandoDocxVersaoId === versao.id}
                  onOpen={() => onOpen(versao.id)}
                  onDownload={() => onDownload(versao.id)}
                  onDownloadDocx={() => onDownload(versao.id, "docx")}
                  onExcluir={() => excluirVersao(versao.id)}
                />
              ))}
            </CollapsibleContent>
          </Collapsible>
        )}

        {renderMatriculaAtos && (
          <Collapsible open={matriculaAberta} onOpenChange={setMatriculaAberta}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                data-testid={`contrato-matricula-toggle-${contrato.id}`}
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${matriculaAberta ? "rotate-180" : ""}`}
                />
                Descrição do imóvel (matrícula)
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              {renderMatriculaAtos(contrato.id)}
            </CollapsibleContent>
          </Collapsible>
        )}

        {renderGeradorContrato && (
          <Collapsible open={geradorAberto} onOpenChange={setGeradorAberto}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                data-testid={`contrato-gerador-toggle-${contrato.id}`}
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${geradorAberto ? "rotate-180" : ""}`}
                />
                Gerar contrato
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              {renderGeradorContrato(contrato.id, geradorAberto)}
            </CollapsibleContent>
          </Collapsible>
        )}

        {renderTestemunhasSelect && (
          <Collapsible open={testemunhasAberta} onOpenChange={setTestemunhasAberta}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                data-testid={`contrato-testemunhas-toggle-${contrato.id}`}
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${testemunhasAberta ? "rotate-180" : ""}`}
                />
                Testemunhas do contrato
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              {renderTestemunhasSelect(contrato.id, testemunhasAberta)}
            </CollapsibleContent>
          </Collapsible>
        )}

        {renderProveniencia && (
          <Collapsible open={provenienciaAberta} onOpenChange={setProvenienciaAberta}>
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                data-testid={`contrato-proveniencia-toggle-${contrato.id}`}
              >
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${provenienciaAberta ? "rotate-180" : ""}`}
                />
                Proveniência
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              {renderProveniencia(contrato.id, provenienciaAberta)}
            </CollapsibleContent>
          </Collapsible>
        )}
      </CardContent>
      {onSetProcessoLegado && (
        <_ProcessoLegadoDialog
          open={processoLegadoDialogOpen}
          onOpenChange={setProcessoLegadoDialogOpen}
          onConfirmar={(motivo) => {
            onSetProcessoLegado(true, motivo);
            setProcessoLegadoDialogOpen(false);
          }}
          enviando={settingProcessoLegado}
        />
      )}
    </Card>
  );
}

/**
 * `_VersaoAtualRow` — the card's current-version block (Abrir / Baixar /
 * "Baixar .docx"). Extracted from `ContratoCard` (migration 120) so the
 * .docx button's pending state — narrower than `addingVersao`/`patching`,
 * it tracks THIS version's own `getUrl` call — has somewhere to live without
 * bloating the card's own prop list further.
 */
function _VersaoAtualRow({
  contratoId,
  versao,
  baixandoDocx,
  onOpen,
  onDownload,
}: {
  contratoId: string;
  versao: VersaoOut;
  baixandoDocx: boolean;
  onOpen: (versaoId: string, formato?: "pdf" | "docx") => void;
  onDownload: (versaoId: string, formato?: "pdf" | "docx") => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2.5">
      <div className="min-w-0 space-y-0.5">
        <p className="truncate text-sm">
          Versão {versao.numero}
          {versao.rotulo ? ` · ${versao.rotulo}` : ""}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {versao.nome_original} · {formatBytes(versao.tamanho_bytes)}
          {versao.enviado_por?.nome ? ` · ${versao.enviado_por.nome}` : ""} ·{" "}
          {new Date(versao.created_at).toLocaleString("pt-BR")}
        </p>
        {versao.origem === "gerado" && (
          <p className="text-[10px] text-muted-foreground">Gerado automaticamente</p>
        )}
        {versao.origem === "assinado" && (
          <Badge
            variant="secondary"
            className="gap-1 text-[10px]"
            data-testid={`contrato-assinado-${contratoId}`}
          >
            <CheckCircle2 className="h-3 w-3" />
            Assinado
          </Badge>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <TooltipIconButton
          label="Abrir"
          icon={Eye}
          onClick={() => onOpen(versao.id)}
          testId={`contrato-abrir-${contratoId}`}
        />
        <TooltipIconButton
          label="Baixar PDF"
          icon={FileDown}
          onClick={() => onDownload(versao.id)}
          testId={`contrato-baixar-${contratoId}`}
        />
        {/* Migration 120 — only ever `true` on a `gerado` version. */}
        {versao.docx_disponivel && (
          <TooltipIconButton
            label="Baixar .docx"
            icon={baixandoDocx ? Loader2 : FileType2}
            iconClassName={baixandoDocx ? "animate-spin" : undefined}
            disabled={baixandoDocx}
            onClick={() => onDownload(versao.id, "docx")}
            testId={`contrato-baixar-docx-${contratoId}`}
          />
        )}
      </div>
    </div>
  );
}

function VersaoRow({
  versao,
  deleting,
  podeExcluir,
  baixandoDocx,
  onOpen,
  onDownload,
  onDownloadDocx,
  onExcluir,
}: {
  versao: VersaoOut;
  deleting: boolean;
  podeExcluir: boolean;
  baixandoDocx: boolean;
  onOpen: () => void;
  onDownload: () => void;
  onDownloadDocx: () => void;
  onExcluir: () => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed p-2 text-xs"
      data-testid={`contrato-versao-${versao.id}`}
    >
      <div className="min-w-0 space-y-0.5">
        <p className="truncate">
          Versão {versao.numero}
          {versao.rotulo ? ` · ${versao.rotulo}` : ""}
          {versao.origem === "gerado" && (
            <span className="ml-1.5 text-muted-foreground">(gerado automaticamente)</span>
          )}
          {versao.origem === "assinado" && (
            <span
              className="ml-1.5 text-muted-foreground"
              data-testid={`contrato-versao-assinado-${versao.id}`}
            >
              (Assinado)
            </span>
          )}
        </p>
        <p className="truncate text-muted-foreground">
          {versao.nome_original} · {formatBytes(versao.tamanho_bytes)}
          {versao.enviado_por?.nome ? ` · ${versao.enviado_por.nome}` : ""} ·{" "}
          {new Date(versao.created_at).toLocaleString("pt-BR")}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <TooltipIconButton
          label="Abrir"
          icon={Eye}
          className="h-7 w-7"
          onClick={onOpen}
          testId={`contrato-versao-abrir-${versao.id}`}
        />
        <TooltipIconButton
          label="Baixar PDF"
          icon={FileDown}
          className="h-7 w-7"
          onClick={onDownload}
          testId={`contrato-versao-baixar-${versao.id}`}
        />
        {versao.docx_disponivel && (
          <TooltipIconButton
            label="Baixar .docx"
            icon={baixandoDocx ? Loader2 : FileType2}
            iconClassName={baixandoDocx ? "animate-spin" : undefined}
            className="h-7 w-7"
            disabled={baixandoDocx}
            onClick={onDownloadDocx}
            testId={`contrato-versao-baixar-docx-${versao.id}`}
          />
        )}
        {podeExcluir && (
          <TooltipIconButton
            label="Excluir versão"
            icon={Trash2}
            className="h-7 w-7"
            disabled={deleting}
            onClick={onExcluir}
            testId={`contrato-versao-excluir-${versao.id}`}
          />
        )}
      </div>
    </div>
  );
}

/**
 * `_AssinaturaSection` — the envelope's own row (signature-integration-CONTRACT
 * §4): either the "Enviar para assinatura" button, the pendente/parcial
 * status block, or nothing at all once the envelope is `concluido` (the
 * "Assinado" badge on the signed VERSION already covers that state — see
 * `_VersaoAtualRow`/`VersaoRow`).
 *
 * 🔴 `envelopeVivo`, not bare truthiness — a `cancelado`/`expirado` envelope
 * still lets "Enviar para assinatura" show again (§3.2's migration note: "a
 * cancelled/expired one may be superseded").
 *
 * 🔴 WHILE `entry.data` IS UNRESOLVED (`isPending && data === undefined`)
 * THIS RENDERS NOTHING — never the button, never the status block. Reading
 * `undefined` as "no envelope" would flash "Enviar para assinatura" on a
 * contract that already has a live one, the exact lying-loading-state shape
 * `KB § PATTERNS/frontend/lying-loading-state.md` exists to rule out.
 */
function _AssinaturaSection({
  contratoId,
  versao,
  entry,
  onAbrirEnvio,
  onCancelar,
  cancelando = false,
}: {
  contratoId: string;
  versao: VersaoOut;
  entry?: AssinaturaEntry;
  onAbrirEnvio?: (versaoId: string) => void;
  onCancelar?: (motivo: string) => void;
  cancelando?: boolean;
}) {
  const [cancelarAberto, setCancelarAberto] = useState(false);
  const carregando = !!entry && entry.isPending && entry.data === undefined;

  if (carregando) {
    return (
      <p
        className="flex items-center gap-1.5 text-xs text-muted-foreground"
        data-testid={`contrato-assinatura-carregando-${contratoId}`}
      >
        <Loader2 className="h-3 w-3 animate-spin" />
        Verificando status de assinatura…
      </p>
    );
  }

  const assinatura = entry?.data;
  const vivo = envelopeVivo(assinatura);

  if (!vivo) {
    if (versao.origem !== "gerado" || !onAbrirEnvio) return null;
    return (
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => onAbrirEnvio(versao.id)}
        data-testid={`contrato-enviar-assinatura-${contratoId}`}
      >
        <Send className="mr-1.5 h-3.5 w-3.5" />
        Enviar para assinatura
      </Button>
    );
  }

  // `vivo` implies `assinatura` is set (see `envelopeVivo`).
  const envelope = assinatura as AssinaturaOut;

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-md border p-2.5"
      data-testid={`contrato-assinatura-status-${contratoId}`}
    >
      <Badge
        variant="secondary"
        className="gap-1 text-[11px]"
        data-testid={`contrato-assinatura-chip-${contratoId}`}
      >
        <Clock3 className="h-3 w-3" />
        {STATUS_ASSINATURA_LABEL[envelope.status]}
      </Badge>
      <a
        href={envelope.link_assinatura}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        data-testid={`contrato-abrir-provedor-${contratoId}`}
      >
        Abrir no {envelope.provedor}
        <ExternalLink className="h-3 w-3" />
      </a>
      {onCancelar && (
        <>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            disabled={cancelando}
            onClick={() => setCancelarAberto(true)}
            data-testid={`contrato-cancelar-envio-${contratoId}`}
          >
            {cancelando ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <XCircle className="mr-1.5 h-3.5 w-3.5" />
            )}
            Cancelar envio
          </Button>
          <_CancelarEnvioDialog
            open={cancelarAberto}
            onOpenChange={setCancelarAberto}
            onConfirmar={(motivo) => {
              onCancelar(motivo);
              setCancelarAberto(false);
            }}
            enviando={cancelando}
          />
        </>
      )}
    </div>
  );
}

const MOTIVO_CANCELAMENTO_MIN = 3;
const MOTIVO_CANCELAMENTO_MAX = 500;

/**
 * `_CancelarEnvioDialog` — §3.3's motivo, 3..500 chars. A plain `Dialog`
 * (not lifted to `ClienteDetailModal`) rather than `window.prompt`: unlike
 * `excluirContrato`'s prompt, this needs live length feedback a bare
 * `prompt()` cannot give — see this file's header note on the "sibling
 * dialog" discipline not applying here (no partes/testemunhas data needed).
 */
function _CancelarEnvioDialog({
  open,
  onOpenChange,
  onConfirmar,
  enviando,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmar: (motivo: string) => void;
  enviando: boolean;
}) {
  const [motivo, setMotivo] = useState("");

  useEffect(() => {
    if (!open) setMotivo("");
  }, [open]);

  const motivoValido =
    motivo.trim().length >= MOTIVO_CANCELAMENTO_MIN &&
    motivo.trim().length <= MOTIVO_CANCELAMENTO_MAX;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="cancelar-envio-dialog">
        <DialogHeader>
          <DialogTitle>Cancelar envio para assinatura</DialogTitle>
          <DialogDescription>
            Explique por que este envio está sendo cancelado (3 a 500 caracteres).
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={motivo}
          maxLength={MOTIVO_CANCELAMENTO_MAX}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Motivo do cancelamento"
          data-testid="cancelar-envio-motivo"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={enviando}>
            Voltar
          </Button>
          <Button
            variant="destructive"
            disabled={!motivoValido || enviando}
            onClick={() => onConfirmar(motivo.trim())}
            data-testid="cancelar-envio-confirmar"
          >
            {enviando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Cancelar envio
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const MOTIVO_PROCESSO_LEGADO_MIN = 3;
const MOTIVO_PROCESSO_LEGADO_MAX = 500;

/**
 * `_ProcessoLegadoDialog` — migration 151's motivo, 3..500 chars, same
 * shape as `_CancelarEnvioDialog` above. Only asked when turning the flag
 * ON: `ContratoCard` calls `onSetProcessoLegado(false)` directly for the
 * OFF case, since there is nothing left to explain once the dispensation
 * is lifted.
 */
function _ProcessoLegadoDialog({
  open,
  onOpenChange,
  onConfirmar,
  enviando,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirmar: (motivo: string) => void;
  enviando: boolean;
}) {
  const [motivo, setMotivo] = useState("");

  useEffect(() => {
    if (!open) setMotivo("");
  }, [open]);

  const motivoValido =
    motivo.trim().length >= MOTIVO_PROCESSO_LEGADO_MIN &&
    motivo.trim().length <= MOTIVO_PROCESSO_LEGADO_MAX;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="processo-legado-dialog">
        <DialogHeader>
          <DialogTitle>Processo anterior à plataforma</DialogTitle>
          <DialogDescription>
            Este deal começou antes da plataforma — as certidões podem ter sido emitidas
            fora do fluxo atual. Explique por que (3 a 500 caracteres); os prazos de
            certidões passam a ser avisos, não bloqueios, apenas para este contrato.
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={motivo}
          maxLength={MOTIVO_PROCESSO_LEGADO_MAX}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Motivo"
          data-testid="processo-legado-motivo"
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={enviando}>
            Voltar
          </Button>
          <Button
            disabled={!motivoValido || enviando}
            onClick={() => onConfirmar(motivo.trim())}
            data-testid="processo-legado-confirmar"
          >
            {enviando && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Marcar como processo anterior
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
