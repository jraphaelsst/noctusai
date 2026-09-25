/**
 * `<FinanciamentoPanel/>` — the card's Financiamento/Escritura subpage.
 *
 * The decision (pendente / aprovado / recusado), then the paperwork: the
 * escritura set always, the FGTS set only when FGTS is in play.
 *
 * 🔴 ONE SLOT PER DOCUMENT TYPE, NOT A FREE PILE
 * -----------------------------------------------
 * Every required type is rendered whether or not a file exists for it, so the
 * panel answers "what is still missing" without anyone having to hold the
 * list in their head. A plain uploads list would show what HAS arrived and
 * say nothing about what has not — which is the question this screen exists
 * to answer.
 *
 * 🔴 OPENING A DOCUMENT IS A RECORDED ACCESS
 * -------------------------------------------
 * These are income tax returns and employment records. The signed-URL call is
 * made only on an explicit click — never on render, never on a timer — because
 * each one appends to the server-side access log naming the viewer.
 */
import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileText,
  Loader2,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { DocumentoTipoSlot, documentoDoTipo } from "@/components/card/DocumentoTipoSlot";

import type { AgenteFinanceiro } from "@/hooks/useAgentesFinanceiros";

import type {
  Financiamento,
  FinanciamentoDocumento,
  FinanciamentoPatch,
  SituacaoFinanciamento,
} from "@/hooks/useFinanciamento";
import {
  SITUACAO_LABEL,
  TIPO_LABEL,
  financiamentoExtracaoEmAndamento,
  rotuloAviso,
} from "@/hooks/useFinanciamento";

/** Radix treats `value=""` as uncontrolled, so "no agent" needs a real
 *  token, mapped back to null on save. */
const SEM_AGENTE = "__sem_agente__";

interface Props {
  /** Active agents from the org registry — what the dropdown may offer. */
  agentes?: AgenteFinanceiro[];
  agentesLoading?: boolean;
  financiamento: Financiamento | undefined;
  loading: boolean;
  saving: boolean;
  uploading: boolean;
  error?: string | null;
  onSave: (patch: FinanciamentoPatch) => void;
  onUpload: (file: File, tipoDocumento: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
  /** Migration 171 extraction actions (contract §E.5/§F) — re-run a
   *  stuck/errored read, confirm a machine reading, or discard it (the file
   *  and reading both stay; only the "awaiting decision" state clears).
   *  Optional so every EXISTING test/caller of this presentational
   *  component keeps compiling; a caller that omits them simply never shows
   *  extraction chrome for a document with `extracao_status != null`. */
  onExtrair?: (documentoId: string) => void;
  onConfirmarExtracao?: (documentoId: string) => void;
  onDescartarExtracao?: (documentoId: string) => void;
  extraindo?: boolean;
  confirmandoExtracao?: boolean;
  descartandoExtracao?: boolean;
}

const SITUACOES: SituacaoFinanciamento[] = ["pendente", "aprovado", "recusado"];

const SITUACAO_ICON = {
  pendente: Clock,
  aprovado: CheckCircle2,
  recusado: XCircle,
} as const;

export default function FinanciamentoPanel({
  financiamento,
  loading,
  saving,
  uploading,
  error,
  onSave,
  onUpload,
  onRemove,
  onOpen,
  onExtrair,
  onConfirmarExtracao,
  onDescartarExtracao,
  extraindo,
  confirmandoExtracao,
  descartandoExtracao,
  agentes = [],
  agentesLoading,
}: Props) {
  const [observacoes, setObservacoes] = useState<string | null>(null);
  const [proposta, setProposta] = useState<string | null>(null);

  const f = financiamento;
  const situacao = f?.situacao ?? "pendente";

  // 🔴 The deal's own agent is APPENDED when it is not among the active ones,
  // never dropped. `agentes` holds only active banks (that is what the
  // dropdown may offer); a deal financed by one since retired must still name
  // it, or selecting anything else would be the only way to make the control
  // agree with the record.
  const opcoesAgente: Array<AgenteFinanceiro | { id: string; nome: string; codigo_banco: string | null; ativo: boolean }> =
    (() => {
      const atual = f?.agente_financeiro;
      if (!atual || agentes.some((a) => a.id === atual.id)) return agentes;
      return [...agentes, { ...atual }];
    })();
  const docsPorTipo = new Map<string, FinanciamentoDocumento>();
  (f?.documentos ?? []).forEach((d) => {
    // Newest first from the server, so the first one wins — a re-uploaded
    // document supersedes its predecessor in the slot without hiding it from
    // the audit trail, which lives server-side.
    if (!docsPorTipo.has(d.tipo_documento)) docsPorTipo.set(d.tipo_documento, d);
  });

  // The new "Financiamento" doc group (contract §A) shows only once the
  // deal is actually in play there — a financiamento parcela exists, or the
  // financiamento row has been touched at all (`existe`, which `situacao`
  // going non-default, `fgts`, an agente or a proposta all set). Otherwise
  // this section would demand a guia ITBI/proposta on every deal, including
  // an all-cash one.
  const mostrarSecaoFinanciamentoDocs = Boolean(
    f?.tem_parcela_financiamento || f?.existe,
  );

  const faltando = [
    ...(f?.tipos_escritura ?? []),
    ...(f?.fgts ? f?.tipos_fgts ?? [] : []),
    ...(mostrarSecaoFinanciamentoDocs ? f?.tipos_financiamento_docs ?? [] : []),
  ].filter((t) => !docsPorTipo.has(t)).length;

  return (
    <div className="space-y-4" data-testid="financiamento-panel">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Situação do financiamento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {SITUACOES.map((s) => {
              const Icon = SITUACAO_ICON[s];
              const ativa = s === situacao;
              return (
                <Button
                  key={s}
                  type="button"
                  size="sm"
                  variant={ativa ? "default" : "outline"}
                  disabled={loading || saving}
                  onClick={() => onSave({ situacao: s })}
                  data-testid={`financiamento-situacao-${s}`}
                  aria-pressed={ativa}
                >
                  <Icon className="mr-1.5 h-3.5 w-3.5" />
                  {SITUACAO_LABEL[s]}
                </Button>
              );
            })}
          </div>

          {f?.situacao_em && situacao !== "pendente" && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {SITUACAO_LABEL[situacao]} em{" "}
              {new Date(f.situacao_em).toLocaleString("pt-BR")}
              {/* H6 (owner, 2026-09-25) — a signed contrato de financiamento
                  auto-sets "aprovado". The badge says so; it never hides
                  that a person may still change it. */}
              {f.situacao_origem === "extraido" && (
                <Badge
                  variant="secondary"
                  className="text-[10px]"
                  data-testid="financiamento-situacao-origem-extraido"
                >
                  Detectado no contrato assinado
                </Badge>
              )}
            </p>
          )}

          {/* ─── Agente financeiro (migration 100) ────────────────────────
              Chosen from the org's registry, never typed. An agency works
              with the same four or five banks repeatedly, and typed per deal
              "Caixa Econômica Federal" becomes three spellings inside a
              month — at which point "how many deals went through Caixa"
              stops having an answer.

              🔴 A RETIRED AGENT STILL RENDERS. The dropdown lists only active
              ones, but a deal financed by a bank the agency has since stopped
              working with must keep naming it. When this deal's agent is not
              in the active list, it is appended and marked — never dropped,
              which would silently blank the institution on a signed
              contract. */}
          <div className="space-y-1.5">
            <Label htmlFor="financiamento-agente">Agente financeiro</Label>
            <Select
              value={f?.agente_financeiro_id ?? SEM_AGENTE}
              onValueChange={(v) =>
                onSave({ agente_financeiro_id: v === SEM_AGENTE ? null : v })
              }
              disabled={loading || saving}
            >
              <SelectTrigger
                id="financiamento-agente"
                data-testid="financiamento-agente"
              >
                <SelectValue placeholder="Selecione o banco" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SEM_AGENTE}>Não definido</SelectItem>
                {opcoesAgente.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.nome}
                    {a.codigo_banco ? ` (${a.codigo_banco})` : ""}
                    {a.ativo === false ? " — inativo" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {/* H7 (owner, 2026-09-25) — the registry row was created BY an
                extraction landing (bank read off a document, no matching
                agente cadastrado), not typed by a person. Shown so nobody
                mistakes an auto-created bank for a hand-vetted one. */}
            {f?.agente_financeiro?.origem === "auto_criado" && (
              <p
                className="flex items-center gap-1.5 text-xs text-amber-600"
                data-testid="financiamento-agente-auto-criado"
              >
                <AlertTriangle className="h-3 w-3" />
                Cadastrado automaticamente a partir do documento lido.
              </p>
            )}
            {agentes.length === 0 && !agentesLoading && (
              <p className="text-xs text-muted-foreground">
                Nenhum agente cadastrado. Cadastre em Emissões → Agentes
                Financeiros.
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="financiamento-proposta">Número da proposta</Label>
            <Input
              id="financiamento-proposta"
              value={proposta ?? f?.numero_proposta ?? ""}
              onChange={(e) => setProposta(e.target.value)}
              onBlur={() => {
                if (
                  proposta !== null &&
                  proposta !== (f?.numero_proposta ?? "")
                ) {
                  onSave({ numero_proposta: proposta.trim() || null });
                }
              }}
              disabled={loading}
              data-testid="financiamento-proposta"
            />
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <Label htmlFor="fgts-financiamento" className="cursor-pointer">
              Vai usar FGTS
            </Label>
            <Switch
              id="fgts-financiamento"
              checked={f?.fgts ?? false}
              onCheckedChange={(v) => onSave({ fgts: v })}
              disabled={loading || saving}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="financiamento-observacoes">Observações</Label>
            <Textarea
              id="financiamento-observacoes"
              rows={2}
              value={observacoes ?? f?.observacoes ?? ""}
              onChange={(e) => setObservacoes(e.target.value)}
              onBlur={() => {
                if (observacoes !== null && observacoes !== (f?.observacoes ?? "")) {
                  onSave({ observacoes: observacoes.trim() || null });
                }
              }}
              disabled={loading}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Secao
        titulo="Escritura"
        tipos={f?.tipos_escritura ?? []}
        docsPorTipo={docsPorTipo}
        loading={loading}
        uploading={uploading}
        onUpload={onUpload}
        onRemove={onRemove}
        onOpen={onOpen}
        onExtrair={onExtrair}
        onConfirmarExtracao={onConfirmarExtracao}
        onDescartarExtracao={onDescartarExtracao}
        extraindo={extraindo}
        confirmandoExtracao={confirmandoExtracao}
        descartandoExtracao={descartandoExtracao}
      />

      {f?.fgts && (
        <Secao
          titulo="FGTS"
          tipos={f?.tipos_fgts ?? []}
          docsPorTipo={docsPorTipo}
          loading={loading}
          uploading={uploading}
          onUpload={onUpload}
          onRemove={onRemove}
          onOpen={onOpen}
          onExtrair={onExtrair}
          onConfirmarExtracao={onConfirmarExtracao}
          onDescartarExtracao={onDescartarExtracao}
          extraindo={extraindo}
          confirmandoExtracao={confirmandoExtracao}
          descartandoExtracao={descartandoExtracao}
        />
      )}

      {/* New "Financiamento" doc group (contract §A/§F) — guia ITBI's
          sibling documents that only make sense once financing is actually
          in play. `proposta_financiamento`/`contrato_financiamento`. */}
      {mostrarSecaoFinanciamentoDocs && (
        <Secao
          titulo="Financiamento"
          tipos={f?.tipos_financiamento_docs ?? []}
          docsPorTipo={docsPorTipo}
          loading={loading}
          uploading={uploading}
          onUpload={onUpload}
          onRemove={onRemove}
          onOpen={onOpen}
          onExtrair={onExtrair}
          onConfirmarExtracao={onConfirmarExtracao}
          onDescartarExtracao={onDescartarExtracao}
          extraindo={extraindo}
          confirmandoExtracao={confirmandoExtracao}
          descartandoExtracao={descartandoExtracao}
        />
      )}

      {faltando > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="financiamento-faltando">
          {faltando} documento{faltando > 1 ? "s" : ""} ainda não enviado
          {faltando > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}

function Secao({
  titulo,
  tipos,
  docsPorTipo,
  loading,
  uploading,
  onUpload,
  onRemove,
  onOpen,
  onExtrair,
  onConfirmarExtracao,
  onDescartarExtracao,
  extraindo,
  confirmandoExtracao,
  descartandoExtracao,
}: {
  titulo: string;
  tipos: string[];
  docsPorTipo: Map<string, FinanciamentoDocumento>;
  loading: boolean;
  uploading: boolean;
  onUpload: (file: File, tipo: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
  onExtrair?: (documentoId: string) => void;
  onConfirmarExtracao?: (documentoId: string) => void;
  onDescartarExtracao?: (documentoId: string) => void;
  extraindo?: boolean;
  confirmandoExtracao?: boolean;
  descartandoExtracao?: boolean;
}) {
  // Every documento currently on the deal, so `DocumentoTipoSlot` (which
  // reads the ONE row of its own `tipoDocumento` out of the full list) sees
  // documents from every section, not just this one's `tipos`.
  const todosDocumentos = Array.from(docsPorTipo.values());

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FileText className="h-4 w-4" />
          {titulo}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {tipos.map((tipo) => (
          <FinanciamentoDocSlot
            key={tipo}
            tipo={tipo}
            documentos={todosDocumentos}
            loading={loading}
            uploading={uploading}
            onUpload={onUpload}
            onRemove={onRemove}
            onOpen={onOpen}
            onExtrair={onExtrair}
            onConfirmarExtracao={onConfirmarExtracao}
            onDescartarExtracao={onDescartarExtracao}
            extraindo={extraindo}
            confirmandoExtracao={confirmandoExtracao}
            descartandoExtracao={descartandoExtracao}
          />
        ))}
      </CardContent>
    </Card>
  );
}

/**
 * One required document type — filled or not — built on the shared
 * `DocumentoTipoSlot` (contract §F: "replace the local Slot … that makes it
 * the third consumer", after `CertidaoCasamentoSlot` and
 * `EmpresaCartaoSlot`). Extraction chrome (status / aviso / confirmar /
 * descartar / reler) renders only for a document whose `extracao_status` is
 * non-null — most `atendimento_documentos` types (certidão de casamento,
 * comprovante de residência, …) have no registered extractor and show the
 * bare slot, exactly as before this contract. Mirrors
 * `EmpresasSection.EmpresaCartaoSlot`'s own three-action layout.
 */
function FinanciamentoDocSlot({
  tipo,
  documentos,
  loading,
  uploading,
  onUpload,
  onRemove,
  onOpen,
  onExtrair,
  onConfirmarExtracao,
  onDescartarExtracao,
  extraindo,
  confirmandoExtracao,
  descartandoExtracao,
}: {
  tipo: string;
  documentos: FinanciamentoDocumento[];
  loading: boolean;
  uploading: boolean;
  onUpload: (file: File, tipo: string) => void;
  onRemove: (documentoId: string, motivo: string) => void;
  onOpen: (documentoId: string) => void;
  onExtrair?: (documentoId: string) => void;
  onConfirmarExtracao?: (documentoId: string) => void;
  onDescartarExtracao?: (documentoId: string) => void;
  extraindo?: boolean;
  confirmandoExtracao?: boolean;
  descartandoExtracao?: boolean;
}) {
  const documento = documentoDoTipo(documentos, tipo);
  const label = TIPO_LABEL[tipo] ?? tipo;
  const testId = `financiamento-slot-${tipo}`;

  const emAndamento = financiamentoExtracaoEmAndamento(documento?.extracao_status ?? null);
  // The confirm/discard pair is offered only once a read has landed AND
  // nobody has decided on it yet — an already-discarded reading stays
  // visible (the file is kept) but no longer asks anything.
  const aguardaDecisao = documento?.extracao_status === "ok" && !documento.extracao_descartada_em;

  return (
    <div className="space-y-1.5">
      <DocumentoTipoSlot
        documentos={documentos}
        tipoDocumento={tipo}
        label={label}
        onUpload={(file) => onUpload(file, tipo)}
        uploading={uploading}
        onVisualizar={(documentoId) => onOpen(documentoId)}
        onRemover={(documentoId, motivo) => onRemove(documentoId, motivo)}
        testId={testId}
      />
      {emAndamento && (
        <p
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          data-testid={`${testId}-processando`}
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          Lendo o documento…
        </p>
      )}
      {documento?.extracao_status === "erro" && (
        <div
          className="flex items-center justify-between gap-2 text-xs text-destructive"
          data-testid={`${testId}-erro`}
        >
          <span>{documento.extracao_erro || "Não foi possível ler o documento."}</span>
          {onExtrair && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onExtrair(documento.id)}
              disabled={loading || extraindo}
              data-testid={`${testId}-reler`}
            >
              Reenviar para leitura
            </Button>
          )}
        </div>
      )}
      {documento?.extracao_status === "sem_dados" && (
        <p className="text-xs text-muted-foreground" data-testid={`${testId}-sem-dados`}>
          Nenhum dado foi identificado neste documento.
        </p>
      )}
      {documento?.extracao_aviso && (
        <p
          className="flex items-center gap-1.5 text-xs text-amber-600"
          data-testid={`${testId}-aviso`}
        >
          <AlertTriangle className="h-3 w-3" />
          {rotuloAviso(documento.extracao_aviso)}
        </p>
      )}
      {aguardaDecisao && (onConfirmarExtracao || onDescartarExtracao) && (
        <div className="flex items-center gap-2" data-testid={`${testId}-decisao`}>
          {onConfirmarExtracao && (
            <Button
              size="sm"
              onClick={() => onConfirmarExtracao(documento.id)}
              disabled={loading || confirmandoExtracao || descartandoExtracao}
              data-testid={`${testId}-confirmar`}
            >
              Confirmar dados extraídos
            </Button>
          )}
          {onDescartarExtracao && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => onDescartarExtracao(documento.id)}
              disabled={loading || confirmandoExtracao || descartandoExtracao}
              // NOT `-descartar` — `DocumentoTipoSlot` already owns that
              // testid for its own "discard the FILE" button; this one
              // discards the READING only (the file and its remove button
              // both stay).
              data-testid={`${testId}-descartar-leitura`}
            >
              Descartar leitura
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
