/**
 * Supervisão (`/supervisao`, status_pagina `supervisao`) — maya-blocks
 * CONTRACT §3 + §4.3/§4.4/§4.5. Owner only.
 *
 *   1. the supervision switch + `horas_para_assumir` (§4.5);
 *   2. Maya's daily scorecard per block/agent for a chosen SP day (§4.3) —
 *      `?dia=YYYY-MM-DD` deep-links it (the owner's daily notification, §3.4);
 *   3. handoff aging (§4.4): handoffs still `emitido`, the `atrasado` ones
 *      (past `horas_para_assumir` with nobody taking over) highlighted.
 *
 * Owner-only is enforced by the SERVER (403). The page asks the config first
 * and, on 403, explains instead of rendering the rest — there is no seed
 * "is owner" UX predicate to mirror the backend's `admin_roles={"owner"}`
 * client-side, and inventing one would be a second hand-copied role check.
 *
 * Missing metric data renders "sem dados", never 0.
 */
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AlertCircle, AlertTriangle, Info, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DEFINICOES,
  chavesDaRubrica,
  detalheRazao,
  formatarMetrica,
  SEM_DADOS,
} from "@/components/supervisao/metricas";
import { rotuloAgente, useAtendimentoBlocos } from "@/hooks/useAtendimentoBlocos";
import {
  DIA_RE,
  HORAS_MAX,
  HORAS_MIN,
  formatarDia,
  ontemSP,
  statusDe,
  useHandoffsPendentes,
  useSalvarSupervisaoConfig,
  useScorecards,
  useSupervisaoConfig,
  type Handoff,
  type Scorecard,
  type SupervisaoConfig,
} from "@/hooks/useSupervisao";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { formatarDataHoraSP } from "@noctusai/lib/components";

function Alerta({ children, testId }: { children: React.ReactNode; testId: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
      data-testid={testId}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function Aviso({ children, testId }: { children: React.ReactNode; testId: string }) {
  return (
    <p className="flex items-start gap-2 rounded-md border bg-muted/40 px-3 py-3 text-sm" data-testid={testId}>
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </p>
  );
}

// ── 1. Config ────────────────────────────────────────────────────────────

function ConfigCard({ config }: { config: SupervisaoConfig }) {
  const salvar = useSalvarSupervisaoConfig();
  const [ativa, setAtiva] = useState(config.supervisao_ativa);
  const [horas, setHoras] = useState(String(config.horas_para_assumir));
  const [erro, setErro] = useState<string | null>(null);

  const horasNum = Number(horas);
  const horasValidas = Number.isInteger(horasNum) && horasNum >= HORAS_MIN && horasNum <= HORAS_MAX;
  const sujo = ativa !== config.supervisao_ativa || horasNum !== config.horas_para_assumir;

  const onSalvar = () => {
    if (!horasValidas) return;
    setErro(null);
    salvar.mutate(
      { supervisao_ativa: ativa, horas_para_assumir: horasNum },
      {
        onSuccess: (s) => toast.success(s.supervisao_ativa ? "Supervisão ligada." : "Supervisão salva."),
        onError: (err) => setErro(mensagemErroServidor(err, "Não foi possível salvar a supervisão.")),
      },
    );
  };

  return (
    <Card>
      <CardContent className="space-y-4 py-4" data-testid="supervisao-config">
        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-3 text-sm font-medium">
            <Switch checked={ativa} onCheckedChange={setAtiva} aria-label="Supervisão ativa" data-testid="config-ativa" />
            Supervisão ativa
          </label>
          <label className="flex items-center gap-2 text-sm">
            Prazo para assumir um handoff
            <Input
              type="number"
              min={HORAS_MIN}
              max={HORAS_MAX}
              value={horas}
              onChange={(e) => setHoras(e.target.value)}
              className="h-8 w-20"
              aria-label="Prazo para assumir (horas)"
              data-testid="config-horas"
            />
            horas
          </label>
          <Button size="sm" onClick={onSalvar} disabled={!sujo || !horasValidas || salvar.isPending} data-testid="config-salvar">
            {salvar.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            Salvar
          </Button>
        </div>
        {!horasValidas && (
          <p className="text-xs text-destructive" data-testid="config-horas-invalida">
            Use um número inteiro de {HORAS_MIN} a {HORAS_MAX} horas.
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Ligada, a Maya passa a registrar as passagens entre blocos a partir de agora (sem retroativo) e calcula os
          scorecards toda noite. Desligada, nada é registrado e o histórico é mantido. Nada disso envia mensagem a leads.
        </p>
        {config.updated_at && (
          <p className="text-xs text-muted-foreground">Última alteração: {formatarDataHoraSP(config.updated_at)}</p>
        )}
        {erro && <Alerta testId="config-erro">{erro}</Alerta>}
      </CardContent>
    </Card>
  );
}

// ── 2. Scorecards ────────────────────────────────────────────────────────

function ScorecardCard({ sc, rotuloBloco }: { sc: Scorecard; rotuloBloco: (b: string) => string }) {
  const chaves = chavesDaRubrica(sc.rubrica_versao, sc.metricas);
  return (
    <Card data-testid={`scorecard-${sc.bloco}`}>
      <CardContent className="space-y-3 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold">
            {rotuloBloco(sc.bloco)} · {rotuloAgente(sc.agent_key)}
          </h3>
          <span className="text-xs text-muted-foreground">
            Rubrica {sc.rubrica_versao} · calculado em {formatarDataHoraSP(sc.calculado_at)}
          </span>
        </div>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {chaves.map((k) => {
            const def = DEFINICOES[k];
            const valor = formatarMetrica(k, sc.metricas[k]);
            const razao = detalheRazao(k, sc.metricas);
            return (
              <div key={k} className="flex items-baseline justify-between gap-2 border-b py-1" data-testid={`metrica-${sc.bloco}-${k}`}>
                <dt className="flex items-center gap-1 text-sm text-muted-foreground">
                  {def?.rotulo ?? k}
                  {def && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button type="button" aria-label={`Definição: ${def.definicao}`} className="text-muted-foreground">
                          <Info className="h-3 w-3" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-xs">{def.definicao}</TooltipContent>
                    </Tooltip>
                  )}
                </dt>
                <dd className={valor === SEM_DADOS ? "text-sm italic text-muted-foreground" : "text-sm font-semibold"}>
                  {valor}
                  {razao && <span className="ml-1 text-xs font-normal text-muted-foreground">({razao})</span>}
                </dd>
              </div>
            );
          })}
        </dl>
      </CardContent>
    </Card>
  );
}

function ScorecardsSecao({ rotuloBloco }: { rotuloBloco: (b: string) => string }) {
  const [params, setParams] = useSearchParams();
  const maxDia = ontemSP();
  const pedido = params.get("dia");
  const dia = pedido && DIA_RE.test(pedido) && pedido <= maxDia ? pedido : maxDia;
  const q = useScorecards(dia);

  const trocarDia = (novo: string) => {
    if (!DIA_RE.test(novo) || novo > maxDia) return;
    const p = new URLSearchParams(params);
    p.set("dia", novo);
    setParams(p, { replace: true });
  };

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Scorecards do dia</h2>
        <div className="flex items-center gap-2">
          {q.isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="scorecards-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <Input
            type="date"
            max={maxDia}
            value={dia}
            onChange={(e) => trocarDia(e.target.value)}
            className="h-8 w-40"
            aria-label="Dia do scorecard"
            data-testid="scorecards-dia"
          />
        </div>
      </div>
      {q.showSkeleton ? (
        <div data-testid="scorecards-skeleton"><Skeleton className="h-40 w-full" /></div>
      ) : q.isError && !q.data ? (
        <Alerta testId="scorecards-erro">
          {mensagemErroServidor(q.error, "Não foi possível carregar os scorecards.")}{" "}
          <button type="button" className="underline" onClick={() => void q.refetch()}>
            Tentar de novo
          </button>
        </Alerta>
      ) : q.data && !q.data.supervisao_ativa ? (
        <Aviso testId="scorecards-off">Supervisão desligada — ative para a Maya começar a avaliar.</Aviso>
      ) : q.data && q.data.scorecards.length === 0 ? (
        <Aviso testId="scorecards-vazio">
          Ainda não há scorecard para {formatarDia(q.data.dia)}. A Maya calcula os scorecards toda noite para os blocos
          supervisionados — confira se algum bloco está marcado como supervisionado em “Blocos do atendimento”.
        </Aviso>
      ) : q.data ? (
        <TooltipProvider delayDuration={150}>
          <div className="space-y-3" data-testid="scorecards-lista">
            {q.data.scorecards.map((sc) => (
              <ScorecardCard key={`${sc.bloco}:${sc.agent_key ?? "humanos"}`} sc={sc} rotuloBloco={rotuloBloco} />
            ))}
          </div>
        </TooltipProvider>
      ) : null}
    </section>
  );
}

// ── 3. Handoff aging ("babá") ────────────────────────────────────────────

function horasDesde(iso: string, agora: number): number {
  return Math.max(0, Math.floor((agora - new Date(iso).getTime()) / 3_600_000));
}

function HandoffsSecao({ horasPrazo, rotuloBloco }: { horasPrazo: number; rotuloBloco: (b: string) => string }) {
  const q = useHandoffsPendentes();
  const itens: Handoff[] = useMemo(() => q.data?.pages.flatMap((p) => p.itens) ?? [], [q.data]);
  const atrasados = itens.filter((h) => h.atrasado).length;
  const agora = Date.now();

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Handoffs aguardando</h2>
          <p className="text-xs text-muted-foreground">
            Passagens entre blocos que ninguém assumiu ainda. Em destaque, as que passaram de {horasPrazo} h.
          </p>
        </div>
        {q.isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="handoffs-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </div>
      {q.showSkeleton ? (
        <div data-testid="handoffs-skeleton"><Skeleton className="h-24 w-full" /></div>
      ) : q.isError && !q.data ? (
        <Alerta testId="handoffs-erro">
          {mensagemErroServidor(q.error, "Não foi possível carregar os handoffs.")}{" "}
          <button type="button" className="underline" onClick={() => void q.refetch()}>
            Tentar de novo
          </button>
        </Alerta>
      ) : itens.length === 0 ? (
        <Aviso testId="handoffs-vazio">Nenhum handoff aguardando — todas as passagens recentes foram assumidas.</Aviso>
      ) : (
        <>
          {atrasados > 0 && (
            <p className="flex items-center gap-2 text-sm font-medium text-destructive" data-testid="handoffs-atrasados">
              <AlertTriangle className="h-4 w-4" />
              {atrasados === 1 ? "1 handoff passou" : `${atrasados} handoffs passaram`} do prazo de {horasPrazo} h sem
              ninguém assumir.
            </p>
          )}
          <Card>
            <CardContent className="divide-y p-0" data-testid="handoffs-lista">
              {itens.map((h) => (
                <div
                  key={h.id}
                  className={`flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm ${h.atrasado ? "border-l-4 border-l-destructive bg-destructive/5" : ""}`}
                  data-testid={`handoff-${h.id}`}
                  data-atrasado={h.atrasado ? "true" : "false"}
                >
                  <div>
                    <div className="font-medium">
                      {rotuloBloco(h.de_bloco)} → {rotuloBloco(h.para_bloco)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {h.card ? (
                        <a href={h.card.link} className="underline">
                          {h.card.titulo}
                        </a>
                      ) : (
                        "Card removido"
                      )}{" "}
                      · emitido em {formatarDataHoraSP(h.created_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">há {horasDesde(h.created_at, agora)} h</span>
                    {h.atrasado && <Badge variant="destructive">Atrasado</Badge>}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          {q.hasNextPage && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => void q.fetchNextPage()}
              disabled={q.isFetchingNextPage}
              data-testid="handoffs-mais"
            >
              Carregar mais
            </Button>
          )}
        </>
      )}
    </section>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────

export default function Supervisao() {
  const config = useSupervisaoConfig();
  const blocos = useAtendimentoBlocos();
  const rotuloBloco = (b: string) => blocos.data?.blocos.find((x) => x.bloco === b)?.rotulo ?? b;
  const proibido = statusDe(config.error) === 403;

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Supervisão</h1>
          <p className="text-sm text-muted-foreground">
            A Maya acompanha cada bloco do atendimento, avalia o responsável e reporta a você.
          </p>
        </div>
        {config.isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="supervisao-refreshing">
            <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </header>

      {config.showSkeleton ? (
        <div data-testid="supervisao-skeleton"><Skeleton className="h-28 w-full" /></div>
      ) : proibido && !config.data ? (
        <Aviso testId="supervisao-proibido">
          A Supervisão é exclusiva do proprietário da organização. Peça ao proprietário para consultar os relatórios da
          Maya.
        </Aviso>
      ) : config.isError && !config.data ? (
        <Alerta testId="supervisao-erro">
          {mensagemErroServidor(config.error, "Não foi possível carregar a supervisão.")}{" "}
          <button type="button" className="underline" onClick={() => void config.refetch()}>
            Tentar de novo
          </button>
        </Alerta>
      ) : config.data ? (
        <>
          <ConfigCard key={`${config.data.updated_at ?? "padrao"}:${String(config.data.supervisao_ativa)}`} config={config.data} />
          {config.data.supervisao_ativa ? (
            <>
              <ScorecardsSecao rotuloBloco={rotuloBloco} />
              <HandoffsSecao horasPrazo={config.data.horas_para_assumir} rotuloBloco={rotuloBloco} />
            </>
          ) : (
            // Off ⇒ the API returns no scorecards and no handoffs (§4.3/§4.4): nothing to ask for.
            <Aviso testId="supervisao-desligada">Supervisão desligada — ative para a Maya começar a avaliar.</Aviso>
          )}
        </>
      ) : null}
    </div>
  );
}
