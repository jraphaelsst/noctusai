/**
 * `<GeradorContratoSection/>` — the "Gerar contrato" section of a contract
 * card: readiness check (what is missing, where to go fill it) plus the
 * "Gerar versão" action itself.
 *
 * Presentational (S3), same discipline as the rest of `card/**` —
 * `GeradorContratoContainer` (in `components/`, not `components/card/`) owns
 * the readiness query and the generate mutation; this file only renders what
 * it is handed. See `ContratosPanel`'s header note on why `renderMatriculaAtos`
 * (and now `renderGeradorContrato`) stays a render prop rather than an import.
 */
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  MODELO_LABEL,
  type ContratoGeracaoError,
  type ContratoGeracaoStatus,
  type GeracaoFaltando,
  type GeracaoOnde,
} from "@/hooks/useContratos";

/** pt-BR group headers for `faltando[].onde` — the readiness list is grouped
 *  by WHERE to go fill the field, not just what field it is. */
const ONDE_ROTULOS: Record<GeracaoOnde, string> = {
  partes: "Partes envolvidas",
  certidoes: "Certidões",
  imovel: "Imóvel",
  matricula: "Matrícula",
  negociacao: "Negociação",
  financiamento: "Financiamento",
  imobiliaria: "Imobiliária",
  contrato: "Contrato",
};

function agruparPorOnde(faltando: GeracaoFaltando[]): [GeracaoOnde, GeracaoFaltando[]][] {
  const grupos = new Map<GeracaoOnde, GeracaoFaltando[]>();
  for (const item of faltando) {
    const lista = grupos.get(item.onde) ?? [];
    lista.push(item);
    grupos.set(item.onde, lista);
  }
  return Array.from(grupos.entries());
}

interface Props {
  status: ContratoGeracaoStatus | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
  assinaturaData: string;
  onAssinaturaDataChange: (value: string) => void;
  gerando: boolean;
  onGerar: () => void;
  /** The last attempt's `400 CONTRATO_INCOMPLETO` — `null` once cleared by a
   *  new attempt or once cleared by success. */
  erroGeracao: ContratoGeracaoError | null;
  /** The `avisos` a `201` returned — `null` before any successful generation
   *  in this session. */
  avisosGerados: string[] | null;
}

export default function GeradorContratoSection({
  status,
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
}: Props) {
  if (showSkeleton) {
    return (
      <div
        className="flex items-center gap-2 p-2 text-xs text-muted-foreground"
        data-testid="gerador-contrato-skeleton"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Verificando dados do contrato…
      </div>
    );
  }

  if (isError || !status) {
    return (
      <div
        className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
        data-testid="gerador-contrato-erro"
      >
        <span className="text-destructive">
          Não foi possível verificar os dados para gerar o contrato.
        </span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  const grupos = agruparPorOnde(status.faltando);

  return (
    <div className="space-y-3" data-testid="gerador-contrato-section">
      <div className="flex flex-wrap items-center gap-2">
        {status.pronto ? (
          <Badge
            className="gap-1 border-emerald-600/30 bg-emerald-600/10 text-[11px] text-emerald-700 hover:bg-emerald-600/10"
            data-testid="gerador-contrato-pronto"
          >
            <CheckCircle2 className="h-3 w-3" />
            Pronto para gerar
          </Badge>
        ) : (
          <Badge variant="secondary" className="gap-1 text-[11px]" data-testid="gerador-contrato-faltam">
            <AlertTriangle className="h-3 w-3" />
            Faltam dados
          </Badge>
        )}
        {isRefreshing && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
        <span className="text-xs text-muted-foreground" data-testid="gerador-contrato-modelo">
          Modelo detectado: {MODELO_LABEL[status.modelo_derivado]}
        </span>
      </div>

      {!status.modelo_confere && (
        <p className="text-xs text-amber-700" data-testid="gerador-contrato-modelo-diverge">
          O modelo detectado ({MODELO_LABEL[status.modelo_derivado]}) é diferente do modelo
          atual do contrato. Confira antes de gerar.
        </p>
      )}

      {status.bloqueios.length > 0 && (
        <ul className="space-y-1" data-testid="gerador-contrato-bloqueios">
          {status.bloqueios.map((b) => (
            <li key={b.codigo} className="text-xs text-destructive">
              {b.mensagem}
            </li>
          ))}
        </ul>
      )}

      {status.avisos.length > 0 && (
        <ul className="space-y-1" data-testid="gerador-contrato-avisos">
          {status.avisos.map((a) => (
            <li key={a.codigo} className="text-xs text-amber-700">
              {a.mensagem}
            </li>
          ))}
        </ul>
      )}

      {!status.pronto && grupos.length > 0 && (
        <div className="space-y-2" data-testid="gerador-contrato-faltando">
          {grupos.map(([onde, itens]) => (
            <div key={onde}>
              <p className="text-xs font-medium">{ONDE_ROTULOS[onde] ?? onde}</p>
              <ul className="ml-3 list-disc text-xs text-muted-foreground">
                {itens.map((item) => (
                  <li key={`${item.campo}-${item.parte_id ?? ""}`}>{item.rotulo}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="gerador-contrato-data" className="text-xs">
            Data da assinatura
          </Label>
          <Input
            id="gerador-contrato-data"
            type="date"
            className="h-8 w-40"
            value={assinaturaData}
            onChange={(e) => onAssinaturaDataChange(e.target.value)}
            data-testid="gerador-contrato-data"
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={!status.pronto || gerando}
          onClick={onGerar}
          data-testid="gerador-contrato-btn"
        >
          {gerando ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Sparkles className="mr-1.5 h-3.5 w-3.5" />
          )}
          Gerar versão
        </Button>
      </div>

      {erroGeracao && (
        <div
          className="space-y-1 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
          data-testid="gerador-contrato-erro-incompleto"
        >
          <p className="text-destructive">{erroGeracao.message}</p>
          {erroGeracao.details?.faltando?.map((item) => (
            <p key={`f-${item.campo}-${item.parte_id ?? ""}`} className="text-muted-foreground">
              • {item.rotulo}
            </p>
          ))}
          {erroGeracao.details?.bloqueios?.map((b) => (
            <p key={`b-${b.codigo}`} className="text-muted-foreground">
              • {b.mensagem}
            </p>
          ))}
          {erroGeracao.details?.lint?.map((l, i) => (
            <p key={`l-${l.codigo}-${i}`} className="text-muted-foreground">
              • {l.mensagem}
            </p>
          ))}
        </div>
      )}

      {avisosGerados && avisosGerados.length > 0 && (
        <div
          className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2.5 text-xs"
          data-testid="gerador-contrato-avisos-pos-geracao"
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
