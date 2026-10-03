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
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  MODELO_LABEL,
  type ContratoGeracaoError,
  type ContratoGeracaoStatus,
  type GeracaoAviso,
  type GeracaoBloqueio,
  type GeracaoFaltando,
  type GeracaoOnde,
} from "@/hooks/useContratos";

import type { CienciaPcenResult } from "@/types/certidoesPartes";

import { PcenCiencia } from "./certidoes/PcenCiencia";
import { CARD_SUBPAGES, type CardSubpageKey } from "./cardSubpages";

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
  /** The CONTROL on that screen that answers the falta — a DOM id the screen
   *  renders (`derivacao.ALVO_*`). `null`/absent = the screen itself. */
  alvo?: string | null;
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
 * `destino` above.
 *
 * 🔴 `sugestoes[].destino` is the SAME `GeracaoDestino` OBJECT as the
 * faltando's own `destino` — `derivacao.py`'s `Avaliacao.falta` builds ONE
 * `destino` and injects it into every suggestion verbatim
 * (`"sugestoes": [{**s, "destino": destino} ...]`), it never re-derives a
 * narrower plain-string shape. A prior version of this file declared it as
 * `string | null` (the `ProvenienciaFontePossivel.destino` shape instead —
 * a different endpoint, genuinely a plain string, see
 * `hooks/useProveniencia.ts`) and resolved it through
 * `cardSubpages.resolverDestino`; that mismatch crashed prod on 2026-09-25
 * (`destino.startsWith is not a function`) the first time a suggestion's
 * destino reached the card's own subpage rail. Resolve THIS shape through
 * `resolverDestinoRico` below — the same routable-vs-card-scoped split
 * `FaltandoLinha` uses for its own `destino`.
 */
export interface GeracaoSugestao {
  tipo_documento: string | null;
  rotulo: string;
  destino: GeracaoDestino | null;
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

/** The route a routable destino links to — with `#alvo` when it names a
 *  control, which the target page scrolls to (`useRolarAteHash`). */
export function rotaDoDestino(destino: GeracaoDestino): string {
  return destino.alvo ? `${destino.rota}#${destino.alvo}` : destino.rota;
}

/**
 * The routable-vs-card-scoped classification a `GeracaoDestino` renders
 * through — ONE decision, shared by `FaltandoLinha`'s own line AND
 * `SugestoesLista`'s `sugestoes[].destino` (same rich object, see
 * `GeracaoSugestao`'s docstring for why they must never diverge). Each call
 * site keeps its own JSX shape (a standalone action row vs. an inline
 * "em X" phrase) — only the classification itself is shared, so it can
 * never drift between the two.
 */
interface DestinoResolvido {
  kind: "card" | "routable";
  /** `kind: "card"` only — the subpage's pt-BR label, `null` when
   *  `destino.ancora` names none `SUBPAGE_LABEL` knows. */
  subpageLabel: string | null;
  /** `kind: "card"` only — `onIrPara` is wired AND `destino.ancora` names a
   *  control, so the caller can jump the dialog there directly instead of
   *  only naming the subpage in guidance text. */
  podeIrDireto: boolean;
  /** `kind: "routable"` only — `rotaDoDestino(destino)`. */
  href: string | null;
}

function resolverDestinoRico(
  destino: GeracaoDestino,
  onIrPara?: (destino: GeracaoDestino) => void,
): DestinoResolvido {
  if (destino.tela.startsWith("card_")) {
    const subpageLabel = destino.ancora
      ? SUBPAGE_LABEL[destino.ancora as CardSubpageKey] ?? destino.ancora
      : null;
    return {
      kind: "card",
      subpageLabel,
      podeIrDireto: Boolean(onIrPara && destino.ancora),
      href: null,
    };
  }
  return {
    kind: "routable",
    subpageLabel: null,
    podeIrDireto: false,
    href: rotaDoDestino(destino),
  };
}

/**
 * `faltando[].sugestoes` — actionable hints below the missing-field line:
 * "envie X em Y". Resolved through the SAME `resolverDestinoRico` split
 * `FaltandoLinha` uses for its own `destino` — `sugestao.destino` is that
 * identical rich object (`GeracaoSugestao`'s docstring), never a narrower
 * plain-string shape.
 */
function SugestoesLista({
  sugestoes,
  campo,
  parteId,
  onIrPara,
  prefixo,
}: {
  sugestoes?: GeracaoSugestao[];
  campo: string;
  parteId: string | null;
  onIrPara?: (destino: GeracaoDestino) => void;
  prefixo: string;
}) {
  if (!sugestoes || sugestoes.length === 0) return null;
  return (
    <ul
      className="ml-3 mt-0.5 list-disc space-y-0.5 text-muted-foreground/80"
      data-testid={`${prefixo}-faltando-sugestoes-${campo}-${parteId ?? ""}`}
    >
      {sugestoes.map((sugestao, i) => {
        const documentoRotulo = sugestao.tipo_documento ?? sugestao.rotulo;
        const resolved = sugestao.destino
          ? resolverDestinoRico(sugestao.destino, onIrPara)
          : null;
        return (
          <li key={`${documentoRotulo}-${i}`}>
            Envie {documentoRotulo}
            {resolved?.kind === "routable" && resolved.href && (
              <>
                {" "}
                em{" "}
                <Link
                  to={resolved.href}
                  className="text-primary hover:underline"
                  data-testid={`${prefixo}-faltando-sugestao-link-${campo}-${parteId ?? ""}-${i}`}
                >
                  {sugestao.rotulo}
                </Link>
              </>
            )}
            {resolved?.kind === "card" && resolved.podeIrDireto && sugestao.destino && (
              <>
                {" "}
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs font-normal"
                  data-testid={`${prefixo}-faltando-sugestao-ir-${campo}-${parteId ?? ""}-${i}`}
                  onClick={() => onIrPara?.(sugestao.destino!)}
                >
                  Resolver
                </Button>
              </>
            )}
            {resolved?.kind === "card" &&
              !resolved.podeIrDireto &&
              resolved.subpageLabel &&
              ` em ${resolved.subpageLabel} (abra a aba do card).`}
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
 * URL that opens it (`derivacao.py`'s carve-out). When the dialog hands down
 * `onIrPara` (it does since 2026-09-23 — the render ctx's `select`), the line
 * gets a real "Resolver" that switches the subpage and lands on `destino.alvo`.
 * Without it, guidance text names the subpage — never a query param the SPA
 * would ignore. A genuinely routable destino renders a real `<Link>`.
 */
function FaltandoLinha({
  item,
  onIrPara,
  prefixo,
}: {
  item: FaltandoComDestino;
  onIrPara?: (destino: GeracaoDestino) => void;
  prefixo: string;
}) {
  const destino = item.destino;

  if (!destino) {
    // No `destino` on the payload — same rendering as before this slice.
    return (
      <li>
        {item.rotulo}
        <SugestoesLista
          sugestoes={item.sugestoes}
          campo={item.campo}
          parteId={item.parte_id}
          onIrPara={onIrPara}
          prefixo={prefixo}
        />
      </li>
    );
  }

  const resolved = resolverDestinoRico(destino, onIrPara);

  if (resolved.kind === "card") {
    if (resolved.podeIrDireto) {
      return (
        <li>
          <div className="flex items-center justify-between gap-2">
            <span>
              {item.rotulo}
              {resolved.subpageLabel && (
                <span className="text-muted-foreground/70"> (aba {resolved.subpageLabel})</span>
              )}
            </span>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto shrink-0 gap-1 p-0 text-xs font-normal"
              data-testid={`${prefixo}-faltando-ir-${item.campo}-${item.parte_id ?? ""}`}
              onClick={() => onIrPara?.(destino)}
            >
              Resolver
              <ArrowRight className="h-3 w-3" />
            </Button>
          </div>
          <SugestoesLista
            sugestoes={item.sugestoes}
            campo={item.campo}
            parteId={item.parte_id}
            onIrPara={onIrPara}
            prefixo={prefixo}
          />
        </li>
      );
    }
    return (
      <li data-testid={`${prefixo}-faltando-guidance-${item.campo}-${item.parte_id ?? ""}`}>
        {item.rotulo}
        {resolved.subpageLabel && (
          <span className="block text-muted-foreground/70">
            Abra o card do cliente, aba &ldquo;{resolved.subpageLabel}&rdquo;.
          </span>
        )}
        <SugestoesLista
          sugestoes={item.sugestoes}
          campo={item.campo}
          parteId={item.parte_id}
          onIrPara={onIrPara}
          prefixo={prefixo}
        />
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
          data-testid={`${prefixo}-faltando-link-${item.campo}-${item.parte_id ?? ""}`}
        >
          <Link to={resolved.href ?? rotaDoDestino(destino)}>
            Resolver
            <ArrowRight className="h-3 w-3" />
          </Link>
        </Button>
      </div>
      <SugestoesLista
        sugestoes={item.sugestoes}
        campo={item.campo}
        parteId={item.parte_id}
        onIrPara={onIrPara}
        prefixo={prefixo}
      />
    </li>
  );
}

/**
 * The readiness lists — `bloqueios` (red), `avisos` (amber) and `faltando`
 * grouped by WHERE to go fill it, each line actionable off its `destino`.
 * Shared by the contract generator (below) and the aditivo generator
 * (`aditivos/AditivoGeracaoSection`): the backend answers the SAME item
 * shapes for both, so one renderer keeps "Resolver" behaving identically.
 * `entreBloqueiosEAvisos` is the contract's PCEN acknowledgment slot.
 * `prefixo` namespaces every test id.
 */
export function ProntidaoListas({
  faltando,
  bloqueios,
  avisos,
  pronto,
  onIrPara,
  entreBloqueiosEAvisos,
  prefixo = "gerador-contrato",
}: {
  faltando: GeracaoFaltando[];
  bloqueios: GeracaoBloqueio[];
  avisos: GeracaoAviso[];
  pronto: boolean;
  onIrPara?: (destino: GeracaoDestino) => void;
  entreBloqueiosEAvisos?: ReactNode;
  prefixo?: string;
}) {
  const grupos = agruparPorOnde(faltando);
  return (
    <>
      {bloqueios.length > 0 && (
        <ul className="space-y-1" data-testid={`${prefixo}-bloqueios`}>
          {bloqueios.map((b) => (
            <li key={b.codigo} className="text-xs text-destructive">
              {b.mensagem}
            </li>
          ))}
        </ul>
      )}

      {entreBloqueiosEAvisos}

      {avisos.length > 0 && (
        <ul className="space-y-1" data-testid={`${prefixo}-avisos`}>
          {avisos.map((a) => (
            <li key={a.codigo} className="text-xs text-amber-700">
              {a.mensagem}
            </li>
          ))}
        </ul>
      )}

      {!pronto && grupos.length > 0 && (
        <div className="space-y-2" data-testid={`${prefixo}-faltando`}>
          {grupos.map(([onde, itens]) => (
            <div key={onde}>
              <p className="text-xs font-medium">{ONDE_ROTULOS[onde] ?? onde}</p>
              <ul className="ml-3 list-disc text-xs text-muted-foreground">
                {itens.map((item) => (
                  <FaltandoLinha
                    key={`${item.campo}-${item.parte_id ?? ""}`}
                    item={item}
                    onIrPara={onIrPara}
                    prefixo={prefixo}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

/**
 * The last generate attempt's refusal (`400 *_INCOMPLETO` / `422
 * CONTRATO_LINT`), with each `details` item on its own line — shared by the
 * contract and the aditivo generator for the same reason as `ProntidaoListas`.
 */
export function ErroGeracaoDetalhes({
  erro,
  prefixo = "gerador-contrato",
}: {
  erro: ContratoGeracaoError;
  prefixo?: string;
}) {
  return (
    <div
      className="space-y-1 rounded-md border border-destructive/30 bg-destructive/5 p-2.5 text-xs"
      data-testid={`${prefixo}-erro-incompleto`}
    >
      <p className="text-destructive">{erro.message}</p>
      {erro.details?.faltando?.map((item) => (
        <p key={`f-${item.campo}-${item.parte_id ?? ""}`} className="text-muted-foreground">
          • {item.rotulo}
        </p>
      ))}
      {erro.details?.confirmacoes?.map((c) => (
        <p key={`c-${c.resultado_id ?? c.rotulo}`} className="text-muted-foreground">
          • Aguardando ciência: {c.mensagem}
        </p>
      ))}
      {erro.details?.bloqueios?.map((b) => (
        <p key={`b-${b.codigo}`} className="text-muted-foreground">
          • {b.mensagem}
        </p>
      ))}
      {erro.details?.lint?.map((l, i) => (
        <p key={`l-${l.codigo}-${i}`} className="text-muted-foreground">
          • {l.mensagem}
        </p>
      ))}
    </div>
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
  /** Switches the card to a card-scoped destino's subpage and lands on its
   *  `alvo`. Omitted outside the card dialog — card destinos then render as
   *  guidance text. */
  onIrPara?: (destino: GeracaoDestino) => void;
  /** Receita PCEN 2ª via: the operator's acknowledgment / support question
   *  (the container owns the mutation — this file stays presentational). */
  onCienciaPcen?: (resultadoId: string, acao: "entendi" | "duvida") => Promise<CienciaPcenResult>;
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
  onIrPara,
  onCienciaPcen,
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

  const confirmacoes = status.confirmacoes ?? [];
  const aguardandoCiencia = confirmacoes.some((c) => !c.ciente);
  // "Faltam dados" is for missing/blocking data; a deal that is only waiting
  // for the operator's acknowledgment says so instead.
  const soCiencia = !status.pronto && aguardandoCiencia && status.faltando.length === 0 && status.bloqueios.length === 0;

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
        ) : soCiencia ? (
          <Badge variant="secondary" className="gap-1 text-[11px]" data-testid="gerador-contrato-aguardando-ciencia">
            <AlertTriangle className="h-3 w-3" />
            Aguardando sua ciência
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

      <ProntidaoListas
        faltando={status.faltando}
        bloqueios={status.bloqueios}
        avisos={status.avisos}
        pronto={status.pronto}
        onIrPara={onIrPara}
        entreBloqueiosEAvisos={
          <>
            {confirmacoes.length > 0 && onCienciaPcen && (
              <div className="space-y-2" data-testid="gerador-contrato-confirmacoes">
                {confirmacoes.map((c) => (
                  <div key={`${c.codigo}-${c.resultado_id ?? c.parte_id ?? c.rotulo}`} className="space-y-1">
                    <p className="text-xs font-medium">{c.rotulo}</p>
                    <PcenCiencia
                      testId={`gerador-contrato-confirmacao-${c.resultado_id ?? c.rotulo}`}
                      titulo={c.titulo}
                      explicacao={c.explicacao}
                      validadeAte={c.validade_ate}
                      ciente={c.ciente}
                      acoes={c.acoes}
                      contexto={c.rotulo}
                      onEntendi={() => onCienciaPcen(c.resultado_id as string, "entendi")}
                      onDuvida={() => onCienciaPcen(c.resultado_id as string, "duvida")}
                    />
                  </div>
                ))}
              </div>
            )}
          </>
        }
      />

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

      {erroGeracao && <ErroGeracaoDetalhes erro={erroGeracao} />}

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
