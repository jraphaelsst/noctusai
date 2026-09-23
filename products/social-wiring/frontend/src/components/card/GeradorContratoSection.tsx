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
  ArrowRight,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";

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

import { CARD_SUBPAGES, resolverDestino, type CardSubpageKey } from "./cardSubpages";

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

/**
 * `faltando[].destino` — `derivacao.py:100-193`'s `Destinos.para` output,
 * attached to EVERY `faltando` item so the UI can link instead of asking the
 * operator to find the screen. Not yet declared on `GeracaoFaltando` itself
 * (`useContratos.ts` is owned by a different slice in this drop); the
 * runtime payload already carries it, so this extends the type locally
 * rather than touch a file this slice doesn't own.
 */
export interface GeracaoDestino {
  tela: string;
  rota: string;
  ancora: string | null;
  ids: {
    cliente_id?: string;
    contrato_id?: string;
    parte_id?: string;
    imovel_codigo?: string;
  };
}

/**
 * `faltando[].sugestoes` — `sw-extraction-contract` (proveniência slice):
 * which document could fill this missing field and where to go send it.
 * Same "not yet declared on `GeracaoFaltando` itself" carve-out as
 * `destino` above — `sugestoes[].destino` is a PLAIN STRING (a route or a
 * `CardSubpageKey`), unlike `GeracaoFaltando.destino`'s richer object, the
 * same shape `ProvenienciaFontePossivel.destino` uses
 * (`hooks/useProveniencia.ts`) — both resolved through
 * `cardSubpages.resolverDestino`.
 */
export interface GeracaoSugestao {
  tipo_documento: string | null;
  rotulo: string;
  destino: string | null;
}

export type FaltandoComDestino = GeracaoFaltando & {
  destino?: GeracaoDestino;
  sugestoes?: GeracaoSugestao[];
};

/** Card subpage labels, canonical source (`cardSubpages.CARD_SUBPAGES`) —
 *  never a second hand-written copy of the rail's labels. */
const SUBPAGE_LABEL: Partial<Record<CardSubpageKey, string>> = Object.fromEntries(
  CARD_SUBPAGES.map((s) => [s.key, s.label]),
);

/** `configuracoes`' tab labels the way `Settings.tsx` writes its `TabsTrigger`
 *  text — that page owns tab selection (no `?tab=`/hash reader exists there
 *  today), so this is a caption next to the link, never a query param. */
const CONFIGURACOES_ABA_ROTULOS: Partial<Record<string, string>> = {
  imobiliaria: "Imobiliária",
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

/**
 * `faltando[].sugestoes` — actionable hints below the missing-field line:
 * "envie X em Y". Same routable-vs-card-scoped split `FaltandoLinha` already
 * runs for `destino`, generalized through `resolverDestino` since
 * `GeracaoSugestao.destino` is the narrower plain-string shape.
 */
function SugestoesLista({
  sugestoes,
  campo,
  parteId,
}: {
  sugestoes?: GeracaoSugestao[];
  campo: string;
  parteId: string | null;
}) {
  if (!sugestoes || sugestoes.length === 0) return null;
  return (
    <ul
      className="ml-3 mt-0.5 list-disc space-y-0.5 text-muted-foreground/80"
      data-testid={`gerador-contrato-faltando-sugestoes-${campo}-${parteId ?? ""}`}
    >
      {sugestoes.map((sugestao, i) => {
        const { rota, subpageLabel } = resolverDestino(sugestao.destino);
        const documentoRotulo = sugestao.tipo_documento ?? sugestao.rotulo;
        return (
          <li key={`${documentoRotulo}-${i}`}>
            Envie {documentoRotulo}
            {rota && (
              <>
                {" "}
                em{" "}
                <Link
                  to={rota}
                  className="text-primary hover:underline"
                  data-testid={`gerador-contrato-faltando-sugestao-link-${campo}-${parteId ?? ""}-${i}`}
                >
                  {sugestao.rotulo}
                </Link>
              </>
            )}
            {!rota && subpageLabel && ` em ${subpageLabel} (abra a aba do card).`}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * One `faltando` item, rendered actionable off its own `destino`.
 *
 * 🔴 A card-scoped destino (`tela` prefixed `card_`) points at a
 * `ClienteCardDialog` subpage the dialog owns in LOCAL STATE — there is no
 * URL that opens it (`derivacao.py:110-116`'s carve-out), and
 * `GeradorContratoContainer` has no callback wired down from the dialog to
 * switch it either. Inventing a query param the SPA ignores would be a dead
 * link wearing a link's clothes, so this renders guidance text naming the
 * subpage instead. A genuinely routable destino (its own SPA route) renders
 * a real `<Link>`.
 */
function FaltandoLinha({ item }: { item: FaltandoComDestino }) {
  const destino = item.destino;

  if (!destino) {
    // No `destino` on the payload — same rendering as before this slice.
    return (
      <li>
        {item.rotulo}
        <SugestoesLista sugestoes={item.sugestoes} campo={item.campo} parteId={item.parte_id} />
      </li>
    );
  }

  if (destino.tela.startsWith("card_")) {
    const subpageLabel = destino.ancora
      ? SUBPAGE_LABEL[destino.ancora as CardSubpageKey] ?? destino.ancora
      : null;
    return (
      <li data-testid={`gerador-contrato-faltando-guidance-${item.campo}-${item.parte_id ?? ""}`}>
        {item.rotulo}
        {subpageLabel && (
          <span className="block text-muted-foreground/70">
            Abra o card do cliente, aba &ldquo;{subpageLabel}&rdquo;.
          </span>
        )}
        <SugestoesLista sugestoes={item.sugestoes} campo={item.campo} parteId={item.parte_id} />
      </li>
    );
  }

  const abaRotulo = destino.ancora ? CONFIGURACOES_ABA_ROTULOS[destino.ancora] : undefined;
  return (
    <li>
      <div className="flex items-center justify-between gap-2">
        <span>
          {item.rotulo}
          {abaRotulo && <span className="text-muted-foreground/70"> (aba {abaRotulo})</span>}
        </span>
        <Button
          asChild
          type="button"
          variant="link"
          size="sm"
          className="h-auto shrink-0 gap-1 p-0 text-xs font-normal"
          data-testid={`gerador-contrato-faltando-link-${item.campo}-${item.parte_id ?? ""}`}
        >
          <Link to={destino.rota}>
            Resolver
            <ArrowRight className="h-3 w-3" />
          </Link>
        </Button>
      </div>
      <SugestoesLista sugestoes={item.sugestoes} campo={item.campo} parteId={item.parte_id} />
    </li>
  );
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

      {!status.modelo_confere && status.modelo_automatico && (
        <p className="text-xs text-muted-foreground" data-testid="gerador-contrato-modelo-atualiza">
          Os dados do card mudaram: ao gerar, o modelo do contrato passa a ser{" "}
          {MODELO_LABEL[status.modelo_derivado]}.
        </p>
      )}

      {!status.modelo_confere && !status.modelo_automatico && (
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
                  <FaltandoLinha key={`${item.campo}-${item.parte_id ?? ""}`} item={item} />
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
