/**
 * Permutas — the property-swap match board (migration 101).
 *
 * The absorbed Permutas platform, rebuilt on the bilateral scorer promoted to
 * `noctusai_lib.domain.real_estate.matching`. The legacy app's own matching
 * was hard filters over near-empty columns; its funnel closed 74 of 82 matches
 * as rejected, which is what a filter producing noise looks like from the
 * inside.
 *
 * 🔴 THE BANNER IS NOT A NICETY. A run with no embeddings returns a full list
 * of perfectly plausible matches, scored on rules alone — and rules cannot
 * read the sentences this corpus keeps its real constraints in ("casa sem
 * escada", "rua do condomínio sem ladeira", "quintal amplo", "estuda permuta
 * de 30% a 50% do valor"). erp shipped exactly that state for months, because
 * a rule-only score looks completely normal. So `sem_semantica` is rendered as
 * a warning the user has to read, not logged where nobody will.
 *
 * 🔴 DESCARTAR IS PERMANENT-ISH, AND THE PAGE SAYS SO. Moving a match off
 * `sugerido` marks it as a human decision, and the generator will never
 * rewrite it again — that is what stops a re-scan from resurrecting every
 * discarded pair forever. Moving it BACK to sugerido hands it to the engine
 * again, which is why that transition is offered rather than hidden.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeftRight,
  Ban,
  Building2,
  Loader2,
  RefreshCw,
  Sparkles,
  TriangleAlert,
} from "lucide-react";

import {
  ETAPAS,
  ETAPA_LABELS,
  type AtivoResumo,
  type Etapa,
  type PermutaMatch,
  useGerarEmbeddings,
  useGerarMatches,
  useMoverEtapa,
  usePermutaAtivos,
  usePermutaMatches,
} from "@/hooks/usePermutas";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { TableSkeleton } from "@noctusai/lib/design-system";

const BRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
});

function moeda(v: number | null | undefined): string {
  return v == null ? "—" : BRL.format(v);
}

/** The server's own message wins — it names what actually happened. */
function erroDoServidor(err: unknown, fallback: string): string {
  const msg = (err as { message?: string } | null)?.message;
  return msg && msg.trim() ? msg : fallback;
}

/** Score bands. Deliberately three, not a gradient: the number is a heuristic
 *  and a 12-step colour ramp would imply a precision it does not have. */
function faixaDoScore(score: number): { rotulo: string; classe: string } {
  if (score >= 75) return { rotulo: "Forte", classe: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" };
  if (score >= 55) return { rotulo: "Bom", classe: "bg-amber-500/15 text-amber-600 dark:text-amber-400" };
  return { rotulo: "Parcial", classe: "bg-muted text-muted-foreground" };
}

function LadoDoMatch({ ativo, papel }: { ativo: AtivoResumo | null; papel: string }) {
  if (!ativo) {
    // The row exists but its ativo was deleted — say that, rather than
    // rendering an empty card that reads as a loading state.
    return (
      <div className="flex-1 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        {papel}: imóvel removido do registro
      </div>
    );
  }

  const codigo = ativo.imovel_codigo || ativo.codigo || "—";
  const local = [ativo.bairro, ativo.cidade, ativo.uf].filter(Boolean).join(", ");
  const specs = [
    ativo.quartos ? `${ativo.quartos} dorm.` : null,
    ativo.vagas ? `${ativo.vagas} vaga${ativo.vagas > 1 ? "s" : ""}` : null,
    ativo.area_total ? `${ativo.area_total} m²` : null,
  ].filter(Boolean);

  return (
    <div className="flex-1 rounded-md border p-3">
      <div className="mb-1 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
        <Building2 className="h-3.5 w-3.5" />
        {papel}
        <span className="font-mono normal-case tracking-normal">{codigo}</span>
      </div>
      <div className="font-medium">{ativo.titulo || ativo.tipo_imovel || "Imóvel"}</div>
      {local && <div className="text-sm text-muted-foreground">{local}</div>}
      {ativo.condominio_nome && (
        <div className="text-sm text-muted-foreground">{ativo.condominio_nome}</div>
      )}
      <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-semibold tabular-nums">{moeda(ativo.valor)}</span>
        {specs.length > 0 && (
          <span className="text-sm text-muted-foreground">{specs.join(" · ")}</span>
        )}
      </div>
      {ativo.proprietario_nome && (
        <div className="mt-1 text-sm text-muted-foreground">
          Proprietário: {ativo.proprietario_nome}
        </div>
      )}
      {ativo.observacoes && (
        <p className="mt-2 border-l-2 pl-2 text-sm italic text-muted-foreground">
          “{ativo.observacoes}”
        </p>
      )}
    </div>
  );
}

function LinhaDeMatch({
  match,
  onMover,
  movendo,
}: {
  match: PermutaMatch;
  onMover: (etapa: Etapa) => void;
  movendo: boolean;
}) {
  const faixa = faixaDoScore(match.score);
  const herdado = match.origem === "permutas_legacy";
  const semSemantica = match.detalhes?.semantica_disponivel === false;

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {herdado ? (
            // Score 0 on these rows is not a judgement — they were never run
            // through this engine. Rendering "0" beside real scores would
            // read as "we scored this and it is terrible".
            <Badge variant="outline">Decisão herdada do Permutas</Badge>
          ) : (
            <>
              <span className={`rounded px-2 py-0.5 text-sm font-semibold tabular-nums ${faixa.classe}`}>
                {match.score.toFixed(0)} · {faixa.rotulo}
              </span>
              {match.is_bilateral && (
                <Badge variant="secondary" className="gap-1">
                  <Sparkles className="h-3 w-3" />
                  Bilateral
                </Badge>
              )}
              {semSemantica && (
                <Badge variant="outline" className="gap-1 text-amber-600 dark:text-amber-400">
                  <TriangleAlert className="h-3 w-3" />
                  Sem análise semântica
                </Badge>
              )}
            </>
          )}
          <Badge variant="outline" className="ml-auto">
            {ETAPA_LABELS[match.etapa]}
          </Badge>
        </div>

        {match.justificativa && !herdado && (
          <p className="text-sm text-muted-foreground">{match.justificativa}</p>
        )}

        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <LadoDoMatch ativo={match.ativo_origem} papel="Oferece" />
          <ArrowLeftRight className="mx-auto h-5 w-5 shrink-0 text-muted-foreground" />
          <LadoDoMatch ativo={match.ativo_destino} papel="Recebe" />
        </div>

        <div className="flex flex-wrap gap-2">
          {ETAPAS.filter((e) => e !== match.etapa).map((etapa) => (
            <Button
              key={etapa}
              size="sm"
              variant={etapa === "rejeitado" ? "outline" : "secondary"}
              disabled={movendo}
              onClick={() => onMover(etapa)}
            >
              {etapa === "rejeitado" && <Ban className="mr-1 h-3.5 w-3.5" />}
              {ETAPA_LABELS[etapa]}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function Permutas() {
  const [etapa, setEtapa] = useState<Etapa | undefined>(undefined);
  const [aviso, setAviso] = useState<string | null>(null);

  const matchesQuery = usePermutaMatches(etapa);
  const ativosQuery = usePermutaAtivos();
  const gerar = useGerarMatches();
  const embutir = useGerarEmbeddings();
  const mover = useMoverEtapa();

  const matches = matchesQuery.data ?? [];
  const ativos = ativosQuery.data ?? [];

  // Two signals, never `isLoading`, and never a bare `isFetching` gating an
  // early return — that unmounts a list that already exists on every refetch.
  // → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = matchesQuery.isPending && !matchesQuery.data;
  const isRefreshing = matchesQuery.isFetching && !!matchesQuery.data;

  const semVetores = useMemo(
    () => ativos.filter((a) => !a.tem_embedding || !a.tem_embedding_interesses).length,
    [ativos],
  );

  async function handleGerar() {
    try {
      const r = await gerar.mutateAsync({});
      const partes = [
        `${r.gravados} match(es) gravado(s) de ${r.encontrados} encontrado(s)`,
      ];
      if (r.protegidos > 0) {
        partes.push(`${r.protegidos} preservado(s) por já terem decisão`);
      }
      toast.success("Matching concluído", { description: partes.join(" · ") });

      // 🔴 SURFACED, NOT LOGGED. See the file header — a rule-only run looks
      // exactly like a good one from the output alone.
      const avisos: string[] = [];
      if (r.sem_semantica > 0) {
        avisos.push(
          `${r.sem_semantica} par(es) foram pontuados só por regras — sem os vetores, ` +
            `o texto livre das intenções não é lido. Gere os embeddings para incluir a análise semântica.`,
        );
      }
      if (r.imoveis_nao_resolvidos.length > 0) {
        avisos.push(
          `${r.imoveis_nao_resolvidos.length} intenção(ões) ficaram de fora porque o imóvel ` +
            `não está mais no catálogo: ${r.imoveis_nao_resolvidos.slice(0, 5).join(", ")}` +
            `${r.imoveis_nao_resolvidos.length > 5 ? "…" : ""}`,
        );
      }
      setAviso(avisos.length ? avisos.join(" ") : null);
    } catch (err) {
      toast.error("Erro ao gerar matches", {
        description: erroDoServidor(err, "Tente novamente"),
      });
    }
  }

  async function handleEmbeddings() {
    try {
      const r = await embutir.mutateAsync({});
      toast.success("Embeddings gerados", {
        description:
          `${r.processados} ativo(s) vetorizado(s)` +
          (r.sem_texto > 0 ? ` · ${r.sem_texto} sem texto suficiente` : ""),
      });
    } catch (err) {
      toast.error("Erro ao gerar embeddings", {
        description: erroDoServidor(err, "Verifique a chave da OpenAI em Configurações"),
      });
    }
  }

  async function handleMover(matchId: string, novaEtapa: Etapa) {
    try {
      await mover.mutateAsync({ matchId, etapa: novaEtapa });
      toast.success(`Movido para ${ETAPA_LABELS[novaEtapa]}`);
    } catch (err) {
      toast.error("Erro ao mover", {
        description: erroDoServidor(err, "Tente novamente"),
      });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <ArrowLeftRight className="h-6 w-6 text-primary" />
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
              Permutas
              {isRefreshing && (
                <Loader2
                  className="h-4 w-4 animate-spin text-muted-foreground"
                  data-testid="permutas-refreshing"
                />
              )}
            </h1>
            <p className="text-sm text-muted-foreground">
              {ativos.length} imóve{ativos.length === 1 ? "l" : "is"} aberto
              {ativos.length === 1 ? "" : "s"} a permuta · {matches.length} match
              {matches.length === 1 ? "" : "es"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={handleEmbeddings}
            disabled={embutir.isPending}
          >
            {embutir.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 h-4 w-4" />
            )}
            Gerar embeddings
            {semVetores > 0 && (
              <Badge variant="secondary" className="ml-2">
                {semVetores}
              </Badge>
            )}
          </Button>
          <Button onClick={handleGerar} disabled={gerar.isPending}>
            {gerar.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Gerar matches
          </Button>
        </div>
      </div>

      {aviso && (
        <div className="flex gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p>{aviso}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={etapa === undefined ? "default" : "outline"}
          onClick={() => setEtapa(undefined)}
        >
          Todos
        </Button>
        {ETAPAS.map((e) => (
          <Button
            key={e}
            size="sm"
            variant={etapa === e ? "default" : "outline"}
            onClick={() => setEtapa(e)}
          >
            {ETAPA_LABELS[e]}
          </Button>
        ))}
      </div>

      {showSkeleton ? (
        <TableSkeleton rows={5} />
      ) : matchesQuery.isError ? (
        // An empty list and a failed request are DIFFERENT states. Conflating
        // them is how a 500 hides behind "nenhum match".
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Não foi possível carregar os matches.{" "}
            {erroDoServidor(matchesQuery.error, "Tente recarregar a página.")}
          </CardContent>
        </Card>
      ) : matches.length === 0 ? (
        <Card>
          <CardContent className="space-y-2 p-6 text-sm text-muted-foreground">
            <p>Nenhum match {etapa ? `em “${ETAPA_LABELS[etapa]}”` : "ainda"}.</p>
            {!etapa && (
              <p>
                Gere os embeddings e rode o matching — o motor cruza cada imóvel
                aberto a permuta com os demais e com as permutas registradas.
              </p>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {matches.map((m) => (
            <LinhaDeMatch
              key={m.id}
              match={m}
              movendo={mover.isPending}
              onMover={(novaEtapa) => handleMover(m.id, novaEtapa)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
