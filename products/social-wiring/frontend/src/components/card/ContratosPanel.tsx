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
 */
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import {
  AlertCircle,
  ChevronDown,
  Download,
  Eye,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { ContratoOut, ContratoStatus, VersaoOut } from "@/hooks/useContratos";
import {
  CONTRATO_ACCEPT_ATTR,
  CONTRATO_STATUS_OPTIONS,
  MODELO_LABEL,
  STATUS_LABEL,
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
  addingVersaoContratoId?: string | null;
  patchingContratoId?: string | null;
  deletingVersaoId?: string | null;
  deletingContratoId?: string | null;
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
  onOpen: (contratoId: string, versaoId: string) => void;
  onDownload: (contratoId: string, versaoId: string) => void;
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
}

export default function ContratosPanel({
  contratos,
  showSkeleton,
  isRefreshing,
  isError,
  errorMessage,
  onRetry,
  onNovoContrato,
  addingVersaoContratoId,
  patchingContratoId,
  deletingVersaoId,
  deletingContratoId,
  onAddVersao,
  onPatchStatus,
  onPatchPrazos,
  onDeleteVersao,
  onDeleteContrato,
  onOpen,
  onDownload,
  renderMatriculaAtos,
  renderGeradorContrato,
}: Props) {
  const lista = contratos ?? [];

  return (
    <div className="space-y-4" data-testid="contratos-panel">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Contratos</h3>
        <div className="flex items-center gap-2">
          {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
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
          Nenhum contrato neste card ainda. Envie o .docx ou PDF — os contratos
          gerados automaticamente também aparecem aqui.
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
              onAddVersao={(file) => onAddVersao(contrato.id, file)}
              onPatchStatus={(status) => onPatchStatus(contrato.id, status)}
              onPatchPrazos={(patch) => onPatchPrazos(contrato.id, patch)}
              onDeleteVersao={(versaoId, motivo) => onDeleteVersao(contrato.id, versaoId, motivo)}
              onDeleteContrato={(motivo) => onDeleteContrato(contrato.id, motivo)}
              onOpen={(versaoId) => onOpen(contrato.id, versaoId)}
              onDownload={(versaoId) => onDownload(contrato.id, versaoId)}
              renderMatriculaAtos={renderMatriculaAtos}
              renderGeradorContrato={renderGeradorContrato}
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
  onAddVersao,
  onPatchStatus,
  onPatchPrazos,
  onDeleteVersao,
  onDeleteContrato,
  onOpen,
  onDownload,
  renderMatriculaAtos,
  renderGeradorContrato,
}: {
  contrato: ContratoOut;
  addingVersao: boolean;
  patching: boolean;
  deletingVersaoId?: string | null;
  deletingContrato: boolean;
  onAddVersao: (file: File) => void;
  onPatchStatus: (status: ContratoStatus) => void;
  onPatchPrazos: (patch: {
    assinatura_data: string | null;
    prazo_pendencias_dias: number | null;
  }) => void;
  onDeleteVersao: (versaoId: string, motivo: string) => void;
  onDeleteContrato: (motivo: string) => void;
  onOpen: (versaoId: string) => void;
  onDownload: (versaoId: string) => void;
  renderMatriculaAtos?: (contratoId: string) => ReactNode;
  renderGeradorContrato?: (contratoId: string, aberto: boolean) => ReactNode;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [historicoAberto, setHistoricoAberto] = useState(false);
  const [matriculaAberta, setMatriculaAberta] = useState(false);
  const [geradorAberto, setGeradorAberto] = useState(false);

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
            <Select
              value={contrato.status}
              onValueChange={(v) => onPatchStatus(v as ContratoStatus)}
              disabled={patching}
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
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {atual ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2.5">
            <div className="min-w-0 space-y-0.5">
              <p className="truncate text-sm">
                Versão {atual.numero}
                {atual.rotulo ? ` · ${atual.rotulo}` : ""}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {atual.nome_original} · {formatBytes(atual.tamanho_bytes)}
                {atual.enviado_por?.nome ? ` · ${atual.enviado_por.nome}` : ""} ·{" "}
                {new Date(atual.created_at).toLocaleString("pt-BR")}
              </p>
              {atual.origem === "gerado" && (
                <p className="text-[10px] text-muted-foreground">Gerado automaticamente</p>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onOpen(atual.id)}
                data-testid={`contrato-abrir-${contrato.id}`}
              >
                <Eye className="mr-1 h-3.5 w-3.5" />
                Abrir
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onDownload(atual.id)}
                data-testid={`contrato-baixar-${contrato.id}`}
              >
                <Download className="mr-1 h-3.5 w-3.5" />
                Baixar
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Sem versão enviada.</p>
        )}

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
                  onOpen={() => onOpen(versao.id)}
                  onDownload={() => onDownload(versao.id)}
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
      </CardContent>
    </Card>
  );
}

function VersaoRow({
  versao,
  deleting,
  podeExcluir,
  onOpen,
  onDownload,
  onExcluir,
}: {
  versao: VersaoOut;
  deleting: boolean;
  podeExcluir: boolean;
  onOpen: () => void;
  onDownload: () => void;
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
        </p>
        <p className="truncate text-muted-foreground">
          {versao.nome_original} · {formatBytes(versao.tamanho_bytes)}
          {versao.enviado_por?.nome ? ` · ${versao.enviado_por.nome}` : ""} ·{" "}
          {new Date(versao.created_at).toLocaleString("pt-BR")}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button type="button" size="icon" variant="ghost" className="h-7 w-7" onClick={onOpen}>
          <Eye className="h-3.5 w-3.5" />
        </Button>
        <Button type="button" size="icon" variant="ghost" className="h-7 w-7" onClick={onDownload}>
          <Download className="h-3.5 w-3.5" />
        </Button>
        {podeExcluir && (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            disabled={deleting}
            onClick={onExcluir}
            data-testid={`contrato-versao-excluir-${versao.id}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}
