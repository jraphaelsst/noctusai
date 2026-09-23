/**
 * `<ProvenienciaPanel/>` — the "Proveniência" section of a contract card:
 * for every field the "Gerar contrato" readiness check cares about, where
 * the value came from and what state it is in.
 *
 * Mobile-first (375px): one column of stacked cards, no side-by-side layout
 * assumed. Presentational (S3), same discipline as `GeradorContratoSection`
 * — `ProvenienciaContainer` (in `components/`, not `components/card/`) owns
 * the `useProveniencia` query; this file only renders what it is handed.
 *
 * 🔴 WHY THIS LIVES INSIDE Contratos, NOT AS ITS OWN CARD SUBPAGE — the
 * endpoint is keyed by `contrato_id`
 * (`/clientes/{cliente_id}/contratos/{contrato_id}/proveniencia`): it is
 * lineage for ONE contract's fields, not a card-wide concern, so it is a
 * per-contract collapsible next to "Gerar contrato" (same render-prop shape
 * — `ContratosPanel.renderProveniencia`), not a new entry in
 * `cardSubpages.CARD_SUBPAGES`. That registry's own header note already
 * rejects a standalone tab for a satellite concern ("`documentos` IS GONE,
 * and its absence is the point") — a lineage report about the contract's
 * data belongs where the contract's data already lives.
 */
import { AlertCircle, ArrowRight, Loader2, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { resolverDestino } from "./cardSubpages";
import {
  ESTADO_LABEL,
  destinoDoDocumento,
  rotuloDaEntrada,
  type ProvenienciaEstado,
  type ProvenienciaFontePossivel,
  type ProvenienciaItem,
} from "@/hooks/useProveniencia";

const ESTADO_CLASSNAME: Record<ProvenienciaEstado, string> = {
  vazio: "border-muted-foreground/30 bg-muted text-muted-foreground",
  maquina_pendente: "border-amber-300 bg-amber-50 text-amber-800",
  confirmado: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700",
  manual: "border-sky-300 bg-sky-50 text-sky-800",
  conflito: "border-destructive/40 bg-destructive/5 text-destructive",
};

function formatarValor(valor: unknown): string {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (typeof valor === "boolean") return valor ? "Sim" : "Não";
  if (typeof valor === "string" || typeof valor === "number") return String(valor);
  return JSON.stringify(valor);
}

/** Renders a plain-string `destino` as a real route `<Link>` or guidance
 *  naming the card subpage — never a fabricated deep link into a subpage
 *  the dialog owns in local state. `null`/unrecognized destino → nothing. */
function DestinoAcao({
  destino,
  label,
  testId,
}: {
  destino: string | null | undefined;
  label: string;
  testId: string;
}) {
  const { rota, subpageLabel } = resolverDestino(destino);
  if (rota) {
    return (
      <Button
        asChild
        type="button"
        variant="link"
        size="sm"
        className="h-auto shrink-0 gap-1 p-0 text-xs font-normal"
        data-testid={testId}
      >
        <Link to={rota}>
          {label}
          <ArrowRight className="h-3 w-3" />
        </Link>
      </Button>
    );
  }
  if (subpageLabel) {
    return (
      <span className="text-xs text-muted-foreground/70" data-testid={testId}>
        {label} — abra a aba &ldquo;{subpageLabel}&rdquo;.
      </span>
    );
  }
  return null;
}

function FontePossivelHint({ fonte, index }: { fonte: ProvenienciaFontePossivel; index: number }) {
  const documentoRotulo = fonte.tipo_documento ?? fonte.rotulo;
  return (
    <li
      className="flex flex-wrap items-center justify-between gap-1.5 text-xs text-muted-foreground"
      data-testid={`proveniencia-fonte-hint-${index}`}
    >
      <span>
        Envie {documentoRotulo}
        {fonte.entradas.length > 0 && (
          <span className="text-muted-foreground/70">
            {" "}
            ({fonte.entradas.map((e) => rotuloDaEntrada(e)).join(" ou ")})
          </span>
        )}
      </span>
      <DestinoAcao
        destino={fonte.destino}
        label="em"
        testId={`proveniencia-fonte-destino-${index}`}
      />
    </li>
  );
}

function ProvenienciaItemCard({ item }: { item: ProvenienciaItem }) {
  const testId = `proveniencia-item-${item.entidade}-${item.campo}`;
  const documento = item.documento;

  return (
    <div className="space-y-2 rounded-md border p-2.5" data-testid={testId}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <p className="text-xs font-medium">{item.rotulo}</p>
          <p className="truncate text-sm" data-testid={`proveniencia-valor-${item.campo}`}>
            {formatarValor(item.valor)}
          </p>
        </div>
        <Badge
          className={cn("shrink-0 gap-1 border text-[10px]", ESTADO_CLASSNAME[item.estado])}
          data-testid={`proveniencia-estado-${item.campo}`}
        >
          {ESTADO_LABEL[item.estado]}
        </Badge>
      </div>

      {documento && (
        <div
          className="flex flex-wrap items-center justify-between gap-1.5 rounded-md bg-muted/50 p-1.5 text-xs"
          data-testid={`proveniencia-documento-${item.campo}`}
        >
          <span className="text-muted-foreground">
            {documento.tipo}
            {documento.nome ? ` · ${documento.nome}` : ""} · {rotuloDaEntrada(documento.entrada)}
          </span>
          <DestinoAcao
            destino={destinoDoDocumento(documento.entrada)}
            label="Abrir"
            testId={`proveniencia-documento-link-${item.campo}`}
          />
        </div>
      )}

      {item.em && (
        <p className="text-[10px] text-muted-foreground/70" data-testid={`proveniencia-em-${item.campo}`}>
          {new Date(item.em).toLocaleString("pt-BR")}
        </p>
      )}

      {item.estado === "vazio" && item.fontes_possiveis.length > 0 && (
        <ul className="space-y-1" data-testid={`proveniencia-fontes-${item.campo}`}>
          {item.fontes_possiveis.map((fonte, i) => (
            <FontePossivelHint key={`${fonte.tipo_documento ?? fonte.rotulo}-${i}`} fonte={fonte} index={i} />
          ))}
        </ul>
      )}
    </div>
  );
}

interface Props {
  items: ProvenienciaItem[] | undefined;
  showSkeleton: boolean;
  isRefreshing: boolean;
  isError: boolean;
  onRetry: () => void;
}

export default function ProvenienciaPanel({
  items,
  showSkeleton,
  isRefreshing,
  isError,
  onRetry,
}: Props) {
  if (showSkeleton) {
    return (
      <div
        className="flex items-center gap-2 p-2 text-xs text-muted-foreground"
        data-testid="proveniencia-skeleton"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        Carregando proveniência…
      </div>
    );
  }

  if (isError || !items) {
    return (
      <div
        className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
        data-testid="proveniencia-erro"
      >
        <span className="flex items-center gap-1.5 text-destructive">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          Não foi possível carregar a proveniência dos dados.
        </span>
        <Button type="button" size="sm" variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <p className="text-xs text-muted-foreground" data-testid="proveniencia-vazio">
        Nenhum campo rastreado ainda.
      </p>
    );
  }

  return (
    <div className="space-y-2" data-testid="proveniencia-lista">
      {isRefreshing && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" />
          Atualizando…
        </p>
      )}
      {items.map((item) => (
        <ProvenienciaItemCard key={`${item.entidade}-${item.campo}`} item={item} />
      ))}
    </div>
  );
}
