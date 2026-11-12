/**
 * Loop de refinamento — the Evals tab card for `products/agents/docs/eval-loop-gate-contract.md` (the UI slice
 * that document defers): start a loop per suite, see the target ("alvo") and floor ("piso"), the round counter, the
 * budget, the score series, the overcalls (rounds that did not raise the score), the 5/10/15 checkpoints and the
 * cases still failing; run the next round; stop. Every refusal the contract lists reaches the owner with its own
 * pt-BR `detail` (a refusal is never silent) — `hash_inalterado` is turned into the instruction to fix the
 * content first. Loading follows `KB § PATTERNS/frontend/lying-loading-state.md` (hooks expose `showSkeleton` /
 * `isRefreshing` from `data`, never `isLoading`).
 */
import { useState, type FormEvent } from "react";
import { Loader2, Play, Repeat, StopCircle } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Card, Field, FormError, Input, Select } from "@noctusai/lib/design-system";
import { ApiError, errorMessage } from "@/lib/errors";
import { formatUsdCost } from "@/lib/utils";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";
import {
  useLoopConfig,
  useUpdateLoopConfig,
  useCreateEvalLoop,
  useEvalLoops,
  useRunLoopRound,
  useStopEvalLoop,
  hasRoundInFlight,
} from "@/hooks/studio/useEvalLoops";
import type {
  EvalLoop,
  EvalLoopMotivoParada,
  EvalLoopConfig,
  EvalLoopSuite,
} from "@/api/studio/types-ke";
import { StudioError, StudioLoading } from "./StudioStates";

const SUITE_LABEL: Record<EvalLoopSuite, string> = { comportamento: "Comportamento", mecanismo: "Mecanismo" };
const SUITES: EvalLoopSuite[] = ["comportamento", "mecanismo"];

const MOTIVO_TEXT: Record<EvalLoopMotivoParada, string> = {
  alvo_atingido: "Concluído: a nota chegou ao alvo.",
  sem_melhora: "Parado: 2 rodadas seguidas sem melhora da nota.",
  orcamento_atingido: "Parado: o orçamento do loop foi atingido. Decisão do dono: abrir um novo loop com outro orçamento ou encerrar.",
  rodadas_esgotadas: "Encerrado: as rodadas planejadas acabaram sem chegar ao alvo.",
  parado_manualmente: "Parado manualmente.",
};

export const pct = (v: number | null | undefined): string => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** A refusal's own pt-BR text; `hash_inalterado` also carries the instruction the owner must follow. */
function RefusalNote({ error }: { error: unknown }) {
  const text = errorMessage(error);
  const hash = error instanceof ApiError && error.code === "hash_inalterado";
  return (
    <div role="alert" className="space-y-1 text-xs text-destructive" data-testid="loop-refusal">
      <p>{text}</p>
      {hash && (
        <p className="font-semibold" data-testid="loop-refusal-hash">
          Corrija o conteúdo antes da próxima rodada.
        </p>
      )}
    </div>
  );
}

/** Score per round against the floor and target. The SVG is decorative to assistive tech; the same numbers are in the
 * list below it (the accessible equivalent). */
function ScoreSeries({ loop }: { loop: EvalLoop }) {
  const pts = loop.serie;
  if (pts.length === 0) return null;
  const W = 280;
  const H = 90;
  const x = (i: number) => (pts.length === 1 ? W / 2 : 8 + (i * (W - 16)) / (pts.length - 1));
  const y = (v: number) => H - 8 - v * (H - 16);
  const scored = pts.map((p, i) => ({ p, i })).filter(({ p }) => p.score != null);
  return (
    <div data-testid="loop-series">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full max-w-sm" aria-hidden="true" focusable="false">
        <line x1="0" x2={W} y1={y(loop.alvo)} y2={y(loop.alvo)} className="stroke-emerald-500" strokeDasharray="4 3" />
        <line x1="0" x2={W} y1={y(loop.piso)} y2={y(loop.piso)} className="stroke-amber-500" strokeDasharray="4 3" />
        {scored.length > 1 && (
          <polyline
            fill="none"
            className="stroke-primary"
            strokeWidth="1.5"
            points={scored.map(({ p, i }) => `${x(i)},${y(p.score as number)}`).join(" ")}
          />
        )}
        {scored.map(({ p, i }) => (
          <circle key={p.run_id} cx={x(i)} cy={y(p.score as number)} r="3" className={p.overcall ? "fill-destructive" : "fill-primary"} />
        ))}
      </svg>
      <ol className="mt-1 space-y-0.5 text-xs text-muted-foreground" aria-label="Nota por rodada">
        {pts.map((p) => (
          <li key={p.run_id} data-testid={`loop-rodada-${p.rodada}`}>
            Rodada {p.rodada}:{" "}
            {p.status === "executando" ? "em andamento" : p.score == null ? `sem nota (${p.status})` : pct(p.score)} ·{" "}
            {formatUsdCost(p.custo_usd)}
            {p.overcall && <span className="text-destructive"> · não melhorou (overcall)</span>}
          </li>
        ))}
      </ol>
      <p className="mt-1 text-[11px] text-muted-foreground">
        Linha tracejada verde: alvo {pct(loop.alvo)}. Âmbar: piso {pct(loop.piso)}.
      </p>
    </div>
  );
}

function StopDetail({ loop }: { loop: EvalLoop }) {
  const d = loop.detalhe_parada;
  const motivo = loop.motivo_parada;
  return (
    <div className="space-y-1 text-sm" data-testid="loop-encerrado">
      <p className="font-medium text-foreground">{motivo ? MOTIVO_TEXT[motivo] : "Loop encerrado."}</p>
      {motivo === "sem_melhora" && d && (
        <p className="text-xs text-muted-foreground" data-testid="loop-detalhe-parada">
          {d.conteudo_mudou === false ? (
            <span className="font-semibold text-destructive" data-testid="loop-hash-warning">
              O conteúdo não mudou entre as duas últimas rodadas (mesmo hash): a rodada foi repetida sem correção.
            </span>
          ) : d.partes_alteradas && d.partes_alteradas.length > 0 ? (
            <>Mudou entre as duas últimas rodadas: {d.partes_alteradas.join(", ")}, sem melhora na nota.</>
          ) : (
            <>O conteúdo mudou (hash diferente), sem melhora na nota.</>
          )}
        </p>
      )}
    </div>
  );
}

function ActiveLoop({ loop, versionId }: { loop: EvalLoop; versionId: string | null }) {
  const agentKey = loop.agente_chave;
  const round = useRunLoopRound(agentKey, loop.suite);
  const stop = useStopEvalLoop(agentKey);
  const [refusal, setRefusal] = useState<unknown>(null);
  const emAndamento = hasRoundInFlight(loop);
  const falhas = [...loop.serie].reverse().find((r) => r.status === "concluida")?.falhas ?? [];
  const faltaVersao = loop.suite === "comportamento" && !versionId;

  async function runNext() {
    setRefusal(null);
    try {
      await round.mutateAsync({ loopId: loop.id, versionId: versionId ?? "" });
      toast.success("Rodada iniciada.");
    } catch (err) {
      setRefusal(err);
    }
  }
  async function doStop() {
    setRefusal(null);
    try {
      await stop.mutateAsync({ loopId: loop.id });
      toast.success("Loop parado.");
    } catch (err) {
      setRefusal(err);
    }
  }

  return (
    <div className="space-y-3" data-testid={`loop-ativo-${loop.suite}`}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge variant="default">ativo</Badge>
        <span className="font-medium text-foreground">
          Alvo {pct(loop.alvo)} / piso {pct(loop.piso)}
        </span>
        <span className="text-muted-foreground" data-testid="loop-contagem">
          Rodada {loop.rodadas_feitas} de {loop.rodadas_planejadas}
        </span>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="loop-gasto">
        Gasto {formatUsdCost(loop.gasto_usd)} · restante {formatUsdCost(loop.restante_usd)} (orçamento {formatUsdCost(loop.orcamento_usd)}).
        Nota atual {pct(loop.score_atual)} · melhor {pct(loop.melhor_score)}
        {loop.acima_do_piso != null && (loop.acima_do_piso ? " · acima do piso" : " · abaixo do piso")}.
      </p>
      <ScoreSeries loop={loop} />
      {loop.overcalls.length > 0 && (
        <div data-testid="loop-overcalls">
          <p className="text-xs font-semibold text-foreground">
            Rodadas que não melhoraram a nota ({loop.overcalls.length}) · {formatUsdCost(loop.custo_overcalls_usd)} gastos
          </p>
          <ul className="list-disc pl-5 text-xs text-muted-foreground">
            {loop.overcalls.map((o) => (
              <li key={o.run_id}>
                Rodada {o.rodada}: {pct(o.score)} · {formatUsdCost(o.custo_usd)}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ul className="flex flex-wrap gap-2 text-xs" aria-label="Checkpoints" data-testid="loop-checkpoints">
        {loop.checkpoints.map((c) => (
          <li key={c.rodada} className="rounded border border-border px-2 py-0.5 text-muted-foreground">
            Rodada {c.rodada}:{" "}
            {c.atingido ? `${pct(c.score)} · gasto ${formatUsdCost(c.gasto_usd)}` : "ainda não atingido"}
          </li>
        ))}
      </ul>
      {falhas.length > 0 && (
        <div data-testid="loop-falhas">
          <p className="text-xs font-semibold text-foreground">Casos ainda falhando na última rodada ({falhas.length})</p>
          <p className="text-xs text-muted-foreground">{falhas.join(", ")}</p>
        </div>
      )}
      {refusal != null && <RefusalNote error={refusal} />}
      {faltaVersao && (
        <p className="text-xs text-muted-foreground" data-testid="loop-sem-rascunho">
          Crie um rascunho para rodar uma rodada de comportamento.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="primary"
          onClick={runNext}
          disabled={round.isPending || emAndamento || faltaVersao}
          data-testid="loop-proxima"
        >
          {emAndamento || round.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <Play className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          )}
          {emAndamento ? "Rodada em andamento…" : round.isPending ? "Iniciando…" : "Rodar próxima rodada"}
        </Button>
        <Button size="sm" variant="outline" onClick={doStop} disabled={stop.isPending} data-testid="loop-parar">
          <StopCircle className="mr-1.5 h-3.5 w-3.5" aria-hidden />
          {stop.isPending ? "Parando…" : "Parar loop"}
        </Button>
      </div>
      {emAndamento && (
        <p role="status" className="text-xs text-muted-foreground">
          Uma rodada está sendo medida. Parar o loop agora não cancela a rodada em andamento; ela termina e é registrada.
        </p>
      )}
    </div>
  );
}

function EndedLoop({ loop }: { loop: EvalLoop }) {
  const falhas = [...loop.serie].reverse().find((r) => r.status === "concluida")?.falhas ?? [];
  return (
    <div className="space-y-2" data-testid={`loop-fim-${loop.suite}`}>
      <StopDetail loop={loop} />
      <p className="text-xs text-muted-foreground">
        {loop.rodadas_feitas} de {loop.rodadas_planejadas} rodadas · melhor nota {pct(loop.melhor_score)} · gasto{" "}
        {formatUsdCost(loop.gasto_usd)} de {formatUsdCost(loop.orcamento_usd)}.
      </p>
      <ScoreSeries loop={loop} />
      {falhas.length > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="loop-falhas">
          Casos ainda falhando: {falhas.join(", ")}.
        </p>
      )}
    </div>
  );
}

function StartForm({ agentKey, suites, config }: { agentKey: string; suites: EvalLoopSuite[]; config: EvalLoopConfig | undefined }) {
  const [suite, setSuite] = useState<EvalLoopSuite>(suites[0]);
  // Empty = "use the platform config" (the field is omitted); the config is shown as placeholder and cap.
  const [rodadas, setRodadas] = useState("");
  const [orcamento, setOrcamento] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [local, setLocal] = useState<string | null>(null);
  const create = useCreateEvalLoop(agentKey);
  const suiteAtual = suites.includes(suite) ? suite : suites[0];
  const maxRodadas = config?.rodadas_max;
  const maxOrc = config?.orcamento_usd;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLocal(null);
    let n: number | undefined;
    if (rodadas.trim()) {
      n = Number(rodadas);
      if (!Number.isInteger(n) || n < 1 || (maxRodadas != null && n > maxRodadas)) {
        setLocal(`Informe de 1 a ${maxRodadas ?? 100} rodadas.`);
        return;
      }
    }
    let orc: number | undefined;
    if (orcamento.trim()) {
      orc = Number(orcamento.replace(",", "."));
      if (!Number.isFinite(orc) || orc <= 0 || (maxOrc != null && orc > maxOrc)) {
        setLocal(`O orçamento deve ser maior que zero e no máximo ${formatUsdCost(maxOrc ?? 500)}.`);
        return;
      }
    }
    try {
      await create.mutateAsync({ suite: suiteAtual, rodadas_planejadas: n, orcamento_usd: orc });
      toast.success("Loop iniciado.");
      setRodadas("");
      setOrcamento("");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-2" data-testid="loop-form">
      <FormError message={local} />
      <div className="grid gap-2 sm:grid-cols-3">
        <Field label="Suíte">
          <Select value={suiteAtual} onChange={(e) => setSuite(e.target.value as EvalLoopSuite)} data-testid="loop-suite">
            {suites.map((s) => (
              <option key={s} value={s}>
                {SUITE_LABEL[s]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Rodadas planejadas">
          <Input
            type="number"
            min={1}
            max={maxRodadas}
            step={1}
            placeholder={maxRodadas != null ? String(maxRodadas) : undefined}
            value={rodadas}
            onChange={(e) => setRodadas(e.target.value)}
            data-testid="loop-rodadas"
          />
        </Field>
        <Field label="Orçamento (US$)">
          <Input
            type="number"
            min="0.01"
            max={maxOrc}
            step="0.01"
            placeholder={maxOrc != null ? String(maxOrc) : undefined}
            value={orcamento}
            onChange={(e) => setOrcamento(e.target.value)}
            data-testid="loop-orcamento"
          />
        </Field>
      </div>
      <p className="text-xs text-muted-foreground" data-testid="loop-config-resumo">
        {config
          ? `Em branco usa a configuração dos loops: até ${config.rodadas_max} rodadas e ${formatUsdCost(config.orcamento_usd)} (teto), alvo ${pct(config.alvo)}.`
          : "Em branco usa a configuração dos loops."}{" "}
        O loop para sozinho ao chegar ao alvo, após 2 rodadas seguidas sem melhora, ao esgotar o orçamento ou as rodadas.
      </p>
      {error != null && <RefusalNote error={error} />}
      <Button type="submit" size="sm" variant="primary" disabled={create.isPending} data-testid="loop-iniciar">
        <Repeat className="mr-1.5 h-3.5 w-3.5" aria-hidden />
        {create.isPending ? "Iniciando…" : "Iniciar loop de refinamento"}
      </Button>
    </form>
  );
}

/** Platform admins edit the config every loop uses (target, budget cap, max rounds). */
function ConfigEditor({ config }: { config: EvalLoopConfig }) {
  const update = useUpdateLoopConfig();
  const [alvo, setAlvo] = useState(String(Math.round(config.alvo * 100)));
  const [orc, setOrc] = useState(String(config.orcamento_usd));
  const [rod, setRod] = useState(String(config.rodadas_max));
  const [error, setError] = useState<unknown>(null);
  const [local, setLocal] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLocal(null);
    const a = Number(alvo);
    const o = Number(orc.replace(",", "."));
    const r = Number(rod);
    if (!Number.isFinite(a) || a <= 0 || a > 100) return setLocal("O alvo deve estar entre 1% e 100%.");
    if (!Number.isFinite(o) || o <= 0) return setLocal("O orçamento deve ser maior que zero.");
    if (!Number.isInteger(r) || r < 1) return setLocal("As rodadas máximas devem ser um número inteiro de 1 ou mais.");
    try {
      await update.mutateAsync({ alvo: a / 100, orcamento_usd: o, rodadas_max: r });
      toast.success("Configuração dos loops salva.");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <details className="text-sm" data-testid="loop-config">
      <summary className="cursor-pointer text-xs font-semibold text-muted-foreground">Configuração dos loops</summary>
      <form onSubmit={submit} noValidate className="mt-2 space-y-2">
        <FormError message={local} />
        <div className="grid gap-2 sm:grid-cols-3">
          <Field label="Alvo (%)">
            <Input type="number" min={1} max={100} step={1} value={alvo} onChange={(e) => setAlvo(e.target.value)} data-testid="loop-config-alvo" />
          </Field>
          <Field label="Orçamento máximo (US$)">
            <Input type="number" min="0.01" step="0.01" value={orc} onChange={(e) => setOrc(e.target.value)} data-testid="loop-config-orcamento" />
          </Field>
          <Field label="Rodadas máximas">
            <Input type="number" min={1} step={1} value={rod} onChange={(e) => setRod(e.target.value)} data-testid="loop-config-rodadas" />
          </Field>
        </div>
        {error != null && <RefusalNote error={error} />}
        <Button type="submit" size="sm" variant="outline" disabled={update.isPending} data-testid="loop-config-salvar">
          {update.isPending ? "Salvando…" : "Salvar configuração"}
        </Button>
      </form>
    </details>
  );
}

export function EvalLoopCard({ agentKey, versionId }: { agentKey: string; versionId: string | null }) {
  const loops = useEvalLoops(agentKey);
  const platformAdmin = useIsPlatformAdmin();
  const config = useLoopConfig();
  const body = (() => {
    if (loops.showSkeleton) return <StudioLoading rows={2} testId="loop-loading" />;
    if (loops.isError && !loops.data)
      return <StudioError error={loops.error} onRetry={loops.refetch} mensagem="Não foi possível carregar os loops de refinamento." />;
    const items = loops.data ?? [];
    const ativoPor = (s: EvalLoopSuite) => items.find((l) => l.suite === s && l.status === "ativo");
    const ultimoPor = (s: EvalLoopSuite) => items.find((l) => l.suite === s);
    const livres = SUITES.filter((s) => !ativoPor(s));
    return (
      <div className="space-y-4">
        {SUITES.map((s) => {
          const l = ativoPor(s) ?? ultimoPor(s);
          if (!l) return null;
          return (
            <section key={s} aria-label={`Loop da suíte ${SUITE_LABEL[s]}`} className="space-y-1 border-t border-border pt-3 first:border-0 first:pt-0">
              <h4 className="text-xs font-semibold uppercase text-muted-foreground">Suíte {SUITE_LABEL[s]}</h4>
              {l.status === "ativo" ? <ActiveLoop loop={l} versionId={versionId} /> : <EndedLoop loop={l} />}
            </section>
          );
        })}
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="loop-vazio">
            Nenhum loop ainda. Um loop roda a suíte inteira em rodadas, mede a nota de cada uma e para sozinho quando a
            nota deixa de melhorar.
          </p>
        )}
        {livres.length > 0 ? (
          <StartForm key={livres.join()} agentKey={agentKey} suites={livres} config={config.data} />
        ) : (
          <p className="text-xs text-muted-foreground">Já há um loop ativo em cada suíte.</p>
        )}
      </div>
    );
  })();

  return (
    <Card className="space-y-2" data-testid="evals-loop-card" aria-busy={loops.isRefreshing || undefined}>
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        <Repeat className="h-4 w-4" aria-hidden /> Loop de refinamento
        {loops.isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-label="Atualizando" />}
      </h3>
      {body}
      {platformAdmin && config.data && <ConfigEditor key={config.data.atualizado_em ?? "cfg"} config={config.data} />}
    </Card>
  );
}
