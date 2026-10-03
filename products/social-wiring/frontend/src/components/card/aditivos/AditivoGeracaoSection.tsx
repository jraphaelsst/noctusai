/**
 * `<AditivoGeracaoSection/>` — "Gerar aditivo": the readiness check (`GET
 * …/aditivos/{id}/geracao`) and the generate action, mirroring the contract
 * generator (`GeradorContratoSection`). The readiness lists and the refusal
 * box ARE that section's (`ProntidaoListas`, `ErroGeracaoDetalhes`) — same
 * backend item shapes, same "Resolver" deep links; a falta about the aditivo
 * itself lands on the editor (`destino.alvo` = `aditivo-<id>`).
 *
 * Presentational (S3) — `AditivoGeracaoContainer` owns the query and the
 * mutation.
 */
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  ErroGeracaoDetalhes,
  ProntidaoListas,
  type GeracaoDestino,
} from "@/components/card/GeradorContratoSection";
import type { AditivoGeracao } from "@/hooks/useContratoAditivos";
import type { ContratoGeracaoError } from "@/hooks/useContratos";

export interface AditivoGeracaoSectionProps {
  aditivoId: string;
  geracao: AditivoGeracao | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
  assinaturaData: string;
  onAssinaturaDataChange: (value: string) => void;
  gerando: boolean;
  onGerar: () => void;
  erroGeracao: ContratoGeracaoError | null;
  avisosGerados: string[] | null;
  /** The editor has unsaved changes — generating would render the STORED
   *  aditivo, not what is on screen, so the button waits for a save. */
  temAlteracoesNaoSalvas?: boolean;
  onIrPara?: (destino: GeracaoDestino) => void;
}

export function AditivoGeracaoSection({
  aditivoId,
  geracao,
  showSkeleton,
  isRefreshing,
  isError,
  onRetry,
  assinaturaData,
  onAssinaturaDataChange,
  gerando,
  onGerar,
  erroGeracao,
  avisosGerados,
  temAlteracoesNaoSalvas = false,
  onIrPara,
}: AditivoGeracaoSectionProps) {
  const prefixo = `aditivo-geracao-${aditivoId}`;

  if (showSkeleton) {
    return (
      <div className="flex items-center gap-2 p-2 text-xs text-muted-foreground" data-testid={`${prefixo}-skeleton`}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Verificando dados do aditivo…
      </div>
    );
  }

  if (isError || !geracao) {
    return (
      <div
        className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
        data-testid={`${prefixo}-erro`}
      >
        <span className="text-destructive">Não foi possível verificar os dados para gerar o aditivo.</span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-testid={prefixo}>
      <div className="flex flex-wrap items-center gap-2">
        {geracao.pronto ? (
          <Badge
            className="gap-1 border-emerald-600/30 bg-emerald-600/10 text-[11px] text-emerald-700 hover:bg-emerald-600/10"
            data-testid={`${prefixo}-pronto`}
          >
            <CheckCircle2 className="h-3 w-3" />
            Pronto para gerar
          </Badge>
        ) : (
          <Badge variant="secondary" className="gap-1 text-[11px]" data-testid={`${prefixo}-faltam`}>
            <AlertTriangle className="h-3 w-3" />
            Faltam dados
          </Badge>
        )}
        {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        {geracao.revisao_juridica_exigida && (
          <span className="text-xs text-muted-foreground">
            A versão gerada passa pela revisão jurídica antes de assinar ou imprimir.
          </span>
        )}
      </div>

      <ProntidaoListas
        faltando={geracao.faltando}
        bloqueios={geracao.bloqueios}
        avisos={geracao.avisos}
        pronto={geracao.pronto}
        onIrPara={onIrPara}
        prefixo={prefixo}
      />

      {temAlteracoesNaoSalvas && (
        <p className="text-xs text-amber-700" data-testid={`${prefixo}-nao-salvo`}>
          Há alterações não salvas no aditivo — salve antes de gerar.
        </p>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor={`${prefixo}-data`} className="text-xs">
            Data do aditivo
          </Label>
          <Input
            id={`${prefixo}-data`}
            type="date"
            className="h-8 w-40"
            value={assinaturaData}
            onChange={(e) => onAssinaturaDataChange(e.target.value)}
            data-testid={`${prefixo}-data`}
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={!geracao.pronto || gerando || temAlteracoesNaoSalvas}
          onClick={onGerar}
          data-testid={`${prefixo}-btn`}
        >
          {gerando ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
          )}
          Gerar aditivo
        </Button>
      </div>

      {erroGeracao && <ErroGeracaoDetalhes erro={erroGeracao} prefixo={prefixo} />}

      {avisosGerados && avisosGerados.length > 0 && (
        <div
          className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs"
          data-testid={`${prefixo}-avisos-pos-geracao`}
        >
          {avisosGerados.map((msg, i) => (
            <p key={i} className="text-amber-800">
              {msg}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export default AditivoGeracaoSection;
