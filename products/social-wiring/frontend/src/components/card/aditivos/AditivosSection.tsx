/**
 * `<AditivosSection/>` — the "Aditivos" block of a SIGNED contract's card
 * (contrato-aditivos-CONTRACT): list the contract's aditivos, create one
 * (estilo house | formal), and per aditivo — the structured amendments
 * (`AditivoEditor`), status, the generate section (render prop, lazy), the
 * versions (PDF / .docx) and the final legal review (`RevisaoJuridicaSection`,
 * the contract's own, in aditivo mode).
 *
 * Every aditivo block carries the DOM id `aditivo-<id>` (`aditivoDomId`) —
 * the readiness list's "Resolver" for a falta about the aditivo itself
 * (`destino.alvo`) scrolls there.
 *
 * Presentational (S3) — `AditivosContainer` owns every query and mutation;
 * the per-aditivo readiness section comes in through `renderGeracao` for the
 * same reason `ContratosPanel.renderGeradorContrato` does.
 */
import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { AlertCircle, ChevronDown, FileDown, Loader2, Plus, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { FavorecidoOpcao } from "@/components/card/negociacao/ParcelaFormDialog";
import { RevisaoJuridicaSection } from "@/components/card/RevisaoJuridicaSection";
import { VersaoRow } from "@/components/card/VersaoRow";
import {
  ADITIVO_ESTILO_LABEL,
  ADITIVO_ESTILO_OPTIONS,
  aditivoDomId,
  rotuloAditivo,
  type AditivoEstilo,
  type AditivoOut,
  type AditivoPatchBody,
} from "@/hooks/useContratoAditivos";
import {
  CONTRATO_STATUS_OPTIONS,
  STATUS_LABEL,
  aguardandoRevisaoJuridica,
  type ContratoStatus,
  type DownloadOpcoes,
} from "@/hooks/useContratos";

import { AditivoEditor } from "./AditivoEditor";

export interface AditivosSectionProps {
  aditivos: AditivoOut[] | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
  onCriar: (estilo: AditivoEstilo) => void;
  criando: boolean;
  /** The deal's favorecidos — the parcela payee picker. */
  favorecidos: FavorecidoOpcao[];
  onSalvar: (aditivoId: string, patch: AditivoPatchBody) => void;
  salvandoAditivoId: string | null;
  /** The last content save's refusal, for the aditivo it belongs to. */
  erroSalvar: { aditivoId: string; mensagem: string } | null;
  onPatchStatus: (aditivoId: string, status: ContratoStatus) => void;
  /** Readiness + "Gerar aditivo" for one aditivo — `aberto` gates the fetch;
   *  `temAlteracoesNaoSalvas` holds the button until the editor is saved. */
  renderGeracao?: (aditivo: AditivoOut, aberto: boolean, temAlteracoesNaoSalvas: boolean) => ReactNode;
  onOpenVersao: (aditivoId: string, versaoId: string, formato?: "pdf" | "docx") => void;
  onDownloadVersao: (
    aditivoId: string,
    versaoId: string,
    formato?: "pdf" | "docx",
    opcoes?: DownloadOpcoes,
  ) => void;
  baixandoDocxVersaoId?: string | null;
  /** UI convenience only — the server re-checks the trusted role. */
  podeAprovarRevisao: boolean;
  onAprovarRevisao?: (aditivoId: string, versaoId: string) => void;
  aprovandoAditivoId?: string | null;
}

export function AditivosSection({
  aditivos,
  showSkeleton,
  isRefreshing,
  isError,
  onRetry,
  onCriar,
  criando,
  favorecidos,
  onSalvar,
  salvandoAditivoId,
  erroSalvar,
  onPatchStatus,
  renderGeracao,
  onOpenVersao,
  onDownloadVersao,
  baixandoDocxVersaoId,
  podeAprovarRevisao,
  onAprovarRevisao,
  aprovandoAditivoId,
}: AditivosSectionProps) {
  const [estiloNovo, setEstiloNovo] = useState<AditivoEstilo>("house");
  const lista = aditivos ?? [];

  return (
    <div className="space-y-3" data-testid="aditivos-section">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Um aditivo altera este contrato assinado; as demais cláusulas seguem inalteradas.
        </p>
        <div className="flex items-center gap-1.5">
          {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          <Select value={estiloNovo} onValueChange={(v) => setEstiloNovo(v as AditivoEstilo)}>
            <SelectTrigger className="h-8 w-[190px]" data-testid="aditivo-novo-estilo" aria-label="Estilo do novo aditivo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ADITIVO_ESTILO_OPTIONS.map((e) => (
                <SelectItem key={e} value={e}>
                  {ADITIVO_ESTILO_LABEL[e]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            size="sm"
            disabled={criando}
            onClick={() => onCriar(estiloNovo)}
            data-testid="aditivo-novo-btn"
          >
            {criando ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="mr-1.5 h-3.5 w-3.5" />
            )}
            Novo aditivo
          </Button>
        </div>
      </div>

      {isError && !aditivos && (
        <div
          className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5"
          data-testid="aditivos-erro"
        >
          <p className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            Não foi possível carregar os aditivos.
          </p>
          <Button type="button" size="sm" variant="outline" onClick={onRetry}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
            Tentar novamente
          </Button>
        </div>
      )}

      {showSkeleton && (
        <div className="space-y-2" data-testid="aditivos-skeleton">
          <div className="h-16 animate-pulse rounded-md border bg-muted/40" />
        </div>
      )}

      {!showSkeleton && aditivos && lista.length === 0 && (
        <p className="text-xs text-muted-foreground" data-testid="aditivos-vazio">
          Nenhum aditivo para este contrato. Escolha o estilo e clique em “Novo aditivo”.
        </p>
      )}

      {!showSkeleton && lista.length > 0 && (
        <div className="space-y-3" data-testid="aditivos-lista">
          {lista.map((aditivo) => (
            <AditivoItem
              key={aditivo.id}
              aditivo={aditivo}
              favorecidos={favorecidos}
              salvando={salvandoAditivoId === aditivo.id}
              erroSalvar={erroSalvar?.aditivoId === aditivo.id ? erroSalvar.mensagem : null}
              onSalvar={(patch) => onSalvar(aditivo.id, patch)}
              onPatchStatus={(status) => onPatchStatus(aditivo.id, status)}
              renderGeracao={renderGeracao}
              onOpenVersao={(versaoId, formato) => onOpenVersao(aditivo.id, versaoId, formato)}
              onDownloadVersao={(versaoId, formato, opcoes) =>
                onDownloadVersao(aditivo.id, versaoId, formato, opcoes)
              }
              baixandoDocxVersaoId={baixandoDocxVersaoId}
              podeAprovarRevisao={podeAprovarRevisao}
              onAprovarRevisao={
                onAprovarRevisao ? (versaoId) => onAprovarRevisao(aditivo.id, versaoId) : undefined
              }
              aprovando={aprovandoAditivoId === aditivo.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AditivoItem({
  aditivo,
  favorecidos,
  salvando,
  erroSalvar,
  onSalvar,
  onPatchStatus,
  renderGeracao,
  onOpenVersao,
  onDownloadVersao,
  baixandoDocxVersaoId,
  podeAprovarRevisao,
  onAprovarRevisao,
  aprovando,
}: {
  aditivo: AditivoOut;
  favorecidos: FavorecidoOpcao[];
  salvando: boolean;
  erroSalvar: string | null;
  onSalvar: (patch: AditivoPatchBody) => void;
  onPatchStatus: (status: ContratoStatus) => void;
  renderGeracao?: AditivosSectionProps["renderGeracao"];
  onOpenVersao: (versaoId: string, formato?: "pdf" | "docx") => void;
  onDownloadVersao: (versaoId: string, formato?: "pdf" | "docx", opcoes?: DownloadOpcoes) => void;
  baixandoDocxVersaoId?: string | null;
  podeAprovarRevisao: boolean;
  onAprovarRevisao?: (versaoId: string) => void;
  aprovando: boolean;
}) {
  const atual = aditivo.versao_atual;
  // A fresh aditivo (no version yet) opens on the generate step — it is the
  // next thing to do once the amendments are in.
  const [geracaoAberta, setGeracaoAberta] = useState(!atual);
  const [versoesAbertas, setVersoesAbertas] = useState(false);
  const [sujo, setSujo] = useState(false);
  const onDirtyChange = useCallback((v: boolean) => setSujo(v), []);
  const aguardando = aguardandoRevisaoJuridica(atual);
  // The current version is shown above; the history lists the older ones.
  const anteriores = [...aditivo.versoes]
    .filter((v) => v.id !== atual?.id)
    .sort((a, b) => b.numero - a.numero);

  return (
    <div
      id={aditivoDomId(aditivo.id)}
      tabIndex={-1}
      className="space-y-3 rounded-md border p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring"
      data-testid={`aditivo-${aditivo.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-sm font-medium">{rotuloAditivo(aditivo.ordinal)}</p>
          <p className="text-xs text-muted-foreground">{ADITIVO_ESTILO_LABEL[aditivo.estilo]}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          {aguardando && (
            <Badge
              variant="outline"
              className="border-amber-300 bg-amber-50 text-[10px] text-amber-800"
              data-testid={`aditivo-rascunho-${aditivo.id}`}
            >
              Rascunho — aguardando revisão jurídica
            </Badge>
          )}
          <Select value={aditivo.status} onValueChange={(v) => onPatchStatus(v as ContratoStatus)}>
            <SelectTrigger className="h-8 w-[200px]" data-testid={`aditivo-status-${aditivo.id}`}>
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

      {atual && (
        <div className="space-y-2">
          <VersaoRow
            versao={atual}
            deleting={false}
            podeExcluir={false}
            baixandoDocx={baixandoDocxVersaoId === atual.id}
            onOpen={() => onOpenVersao(atual.id)}
            onDownload={() => onDownloadVersao(atual.id)}
            onDownloadDocx={() => onDownloadVersao(atual.id, "docx")}
            testIdPrefix="aditivo-versao"
          />
          <RevisaoJuridicaSection
            contratoId={aditivo.id}
            versao={atual}
            podeAprovarRevisao={podeAprovarRevisao}
            onAprovar={onAprovarRevisao}
            aprovando={aprovando}
            documento="aditivo"
            testIdPrefix="aditivo-revisao"
          />
          {aditivo.modalidade_assinatura === "fisica" && atual.origem === "gerado" && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={aguardando}
                onClick={() => onDownloadVersao(atual.id, "pdf", { impressao: true })}
                data-testid={`aditivo-imprimir-${aditivo.id}`}
              >
                <FileDown className="mr-1.5 h-3.5 w-3.5" />
                Baixar para impressão
              </Button>
              {aguardando && (
                <span className="text-xs text-muted-foreground">
                  Liberado após a aprovação da revisão jurídica.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      <AditivoEditor
        aditivo={aditivo}
        favorecidos={favorecidos}
        salvando={salvando}
        erro={erroSalvar}
        onSalvar={onSalvar}
        onDirtyChange={onDirtyChange}
      />

      {renderGeracao && aditivo.status !== "cancelado" && (
        <Collapsible open={geracaoAberta} onOpenChange={setGeracaoAberta}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              data-testid={`aditivo-geracao-toggle-${aditivo.id}`}
            >
              <ChevronDown className={`h-3 w-3 transition-transform ${geracaoAberta ? "rotate-180" : ""}`} />
              Gerar aditivo
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2">
            {renderGeracao(aditivo, geracaoAberta, sujo)}
          </CollapsibleContent>
        </Collapsible>
      )}

      {anteriores.length > 0 && (
        <Collapsible open={versoesAbertas} onOpenChange={setVersoesAbertas}>
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              data-testid={`aditivo-versoes-toggle-${aditivo.id}`}
            >
              <ChevronDown className={`h-3 w-3 transition-transform ${versoesAbertas ? "rotate-180" : ""}`} />
              {anteriores.length === 1 ? "1 versão anterior" : `${anteriores.length} versões anteriores`}
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 space-y-1.5">
            {anteriores.map((v) => (
              <VersaoRow
                key={v.id}
                versao={v}
                deleting={false}
                podeExcluir={false}
                baixandoDocx={baixandoDocxVersaoId === v.id}
                onOpen={() => onOpenVersao(v.id)}
                onDownload={() => onDownloadVersao(v.id)}
                onDownloadDocx={() => onDownloadVersao(v.id, "docx")}
                testIdPrefix="aditivo-versao"
              />
            ))}
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

export default AditivosSection;
