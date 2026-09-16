/**
 * Edição de Fotos — Processamento (`/edicao-fotos/processamento`,
 * `status_pagina` row `edicao-fotos-processamento`, migration 130). Platform
 * admin only (`capacidades.pode_administrar_plataforma`).
 *
 * - "Processamento ativo" is the LIVE pause switch: the worker is always
 *   running (unless the EDICAO_FOTOS_WORKER_ENABLED kill switch is off) and
 *   claims nothing while this is off — no redeploy either way.
 * - Health: queue depth, running / expired / dead jobs, the last error, and
 *   whether the OpenAI account has credit ("Sem créditos" is shown loudly,
 *   from the last probe or from a job error).
 * - "Testar chave OpenAI" runs a one-token call — on click only.
 *
 * The panel refreshes every 15 s; a background refresh shows "Atualizando…",
 * never a skeleton (CLAUDE.md §1 / contract §9 — never `.isLoading`).
 */
import { toast } from "sonner";
import { AlertCircle, AlertTriangle, CheckCircle2, Lock, PauseCircle, PlayCircle, RefreshCw, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";

import {
  fotosPermissions,
  useAtualizarProcessamento,
  useCapacidades,
  useProcessamento,
  useSondarOpenAI,
  type ProcessamentoPainel,
  type SondaStatus,
} from "@/hooks/useEdicaoFotos";

const REFRESH_MS = 15_000;

const SONDA_ROTULO: Record<SondaStatus, string> = {
  ok: "Chave válida e com créditos",
  sem_credito: "Sem créditos",
  chave_invalida: "Chave inválida",
  sem_chave: "Nenhuma chave configurada",
  limite: "Limite de requisições",
  erro: "Erro ao consultar",
};

function formatarData(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("pt-BR") : "—";
}

export default function Processamento() {
  const { capacidades, showSkeleton } = useCapacidades();
  if (showSkeleton) return <PainelSkeleton />;
  if (!fotosPermissions.podeAdministrarPlataforma(capacidades)) return <AcessoRestrito />;
  return <ProcessamentoView />;
}

function ProcessamentoView() {
  const { painel, showSkeleton, isRefreshing, error, refetch } = useProcessamento({ refetchInterval: REFRESH_MS });
  const atualizar = useAtualizarProcessamento();
  const sondar = useSondarOpenAI();

  async function handleToggle(ativo: boolean) {
    try {
      await atualizar.mutateAsync({ ativo });
      toast.success(ativo ? "Processamento ativado." : "Processamento pausado.");
    } catch (err) {
      toast.error("Não foi possível alterar o processamento.", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
  }

  async function handleSonda() {
    try {
      const r = await sondar.mutateAsync();
      if (r.status === "ok") toast.success(r.mensagem);
      else toast.error(SONDA_ROTULO[r.status], { description: r.mensagem });
    } catch (err) {
      toast.error("Não foi possível testar a chave.", { description: err instanceof Error ? err.message : undefined });
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Processamento</h1>
          <p className="text-sm text-muted-foreground">Liga/desliga o processamento e mostra a saúde da fila.</p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="processamento-atualizando">
            <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </div>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton || !painel ? (
        <PainelSkeleton />
      ) : (
        <>
          {painel.sem_creditos && (
            <Card className="border-destructive bg-destructive/5" data-testid="sem-creditos">
              <CardContent className="flex items-start gap-3 p-4">
                <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                <div className="text-sm">
                  <p className="font-semibold text-destructive">Sem créditos na OpenAI</p>
                  <p>
                    A conta não tem saldo: nenhuma edição, avaliação ou nota roda até créditos serem adicionados no
                    painel de cobrança da OpenAI.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          <Card data-testid="interruptor">
            <CardContent className="flex items-center justify-between gap-4 p-6">
              <div>
                <Label htmlFor="processamento-ativo" className="text-base">
                  Processamento ativo
                </Label>
                <p className="text-sm text-muted-foreground">
                  {painel.ativo
                    ? "O worker está pegando jobs da fila."
                    : "Pausado: lotes podem ser enviados, mas os jobs esperam na fila (nada é gasto)."}
                </p>
              </div>
              <Switch
                id="processamento-ativo"
                checked={painel.ativo}
                disabled={atualizar.isPending}
                onCheckedChange={handleToggle}
              />
            </CardContent>
          </Card>

          <WorkerCard painel={painel} />
          <FilaCard painel={painel} />

          <Card data-testid="sonda">
            <CardContent className="space-y-3 p-6">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="font-medium">Chave OpenAI</h2>
                  <p className="text-sm text-muted-foreground">O teste faz uma chamada de 1 token.</p>
                </div>
                <Button variant="outline" onClick={handleSonda} disabled={sondar.isPending}>
                  <Zap className="mr-2 h-4 w-4" />
                  {sondar.isPending ? "Testando…" : "Testar chave OpenAI"}
                </Button>
              </div>
              {painel.sonda ? (
                <div className="flex items-center gap-2 text-sm" data-testid="sonda-resultado">
                  {painel.sonda.status === "ok" ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-destructive" />
                  )}
                  <span className="font-medium">{SONDA_ROTULO[painel.sonda.status]}</span>
                  <span className="text-muted-foreground">
                    — {painel.sonda.mensagem} ({formatarData(painel.sonda.verificado_em)})
                  </span>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Ainda não testada neste servidor.</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function WorkerCard({ painel }: { painel: ProcessamentoPainel }) {
  const w = painel.worker;
  const estado = !w.kill_switch_ativo
    ? { rotulo: "Desligado (variável de ambiente)", icone: <PauseCircle className="h-4 w-4" /> }
    : !w.rodando
      ? { rotulo: "Parado", icone: <AlertCircle className="h-4 w-4 text-destructive" /> }
      : w.pausado
        ? { rotulo: "Rodando — pausado", icone: <PauseCircle className="h-4 w-4 text-amber-600" /> }
        : { rotulo: "Rodando — processando", icone: <PlayCircle className="h-4 w-4 text-emerald-600" /> };
  return (
    <Card data-testid="worker">
      <CardContent className="space-y-2 p-6 text-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Worker (este servidor)</h2>
          <span className="flex items-center gap-1.5" data-testid="worker-estado">
            {estado.icone} {estado.rotulo}
          </span>
        </div>
        <p className="text-muted-foreground">
          {w.worker_id ?? "—"} · iniciado em {formatarData(w.iniciado_em)} · catálogo recarregado em{" "}
          {formatarData(w.catalogo_atualizado_em)}
        </p>
        {w.motivo_parado && <p>Motivo: {w.motivo_parado}</p>}
        {w.erro_gate && <p className="text-destructive">Falha ao ler o interruptor (pausado por segurança): {w.erro_gate}</p>}
        {w.erro_catalogo && <p className="text-destructive">Catálogo não recarregado: {w.erro_catalogo}</p>}
      </CardContent>
    </Card>
  );
}

function FilaCard({ painel }: { painel: ProcessamentoPainel }) {
  const f = painel.fila;
  const itens: [string, number, string?][] = [
    ["Na fila", f.pendentes],
    ["Prontos para rodar", f.prontos_para_rodar],
    ["Em execução", f.em_execucao],
    ["Lease expirado", f.lease_expirado, f.lease_expirado > 0 ? "text-amber-600" : undefined],
    ["Mortos (dead-letter)", f.mortos, f.mortos > 0 ? "text-destructive" : undefined],
  ];
  return (
    <Card data-testid="fila">
      <CardContent className="space-y-4 p-6">
        <h2 className="font-medium">Fila (todos os servidores)</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {itens.map(([rotulo, valor, cor]) => (
            <div key={rotulo}>
              <p className="text-xs text-muted-foreground">{rotulo}</p>
              <p className={`text-2xl font-semibold ${cor ?? ""}`}>{valor}</p>
            </div>
          ))}
        </div>
        {f.workers_ativos.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {f.workers_ativos.map((id) => (
              <Badge key={id} variant="outline">
                {id}
              </Badge>
            ))}
          </div>
        )}
        {painel.ultimo_erro ? (
          <div className="rounded-md bg-destructive/5 p-3 text-sm" data-testid="ultimo-erro">
            <p className="font-medium">
              Último erro {painel.ultimo_erro.tipo_job ? `(${painel.ultimo_erro.tipo_job})` : ""} ·{" "}
              {formatarData(painel.ultimo_erro.em)}
            </p>
            <p className="break-words font-mono text-xs">{painel.ultimo_erro.mensagem}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Nenhum erro registrado.</p>
        )}
      </CardContent>
    </Card>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="processamento-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da plataforma.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function PainelSkeleton() {
  return (
    <div className="space-y-3" data-testid="processamento-loading">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-28 w-full" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar o painel de processamento.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
