/**
 * Blocos do atendimento (`/atendimento-blocos`, status_pagina
 * `atendimento_blocos`) — maya-blocks CONTRACT §1 + §4.1/§4.2.
 *
 * Per-org config of the six blocks: who runs each one (an agent or the team),
 * whether Maya supervises it (`ativo`) and which pipeline stages it owns.
 * Owner/admin edit (`useIsOrgAdmin`, UX only — the server re-enforces);
 * everyone else reads.
 *
 * Not `ResourceManager`: the list is closed (exactly 6 rows, no create/delete)
 * and the write is ONE partial PUT of the whole config validated together
 * (stage disjointness spans rows), which ResourceManager's per-row
 * POST/PUT/DELETE-by-id shape cannot express.
 *
 * Stage overlap is refused SERVER-side (`etapa_em_dois_blocos`); the page
 * shows that refusal verbatim in an alert and only hints ownership in the
 * option labels — it never silently moves a stage between blocks.
 */
import { useMemo, useState } from "react";
import { AlertCircle, Info, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useIsOrgAdmin, MultiSelectPopover } from "@noctusai/lib/design-system";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  mensagemErroBlocos,
  rotuloAgente,
  useAtendimentoBlocos,
  useSalvarAtendimentoBlocos,
  type BlocoAlteracao,
  type BlocoAtendimento,
  type BlocosConfig,
  type PipelineBloco,
} from "@/hooks/useAtendimentoBlocos";
import { funilPipeline, processosPipeline } from "@/lib/pipelines";

const PIPELINE_ROTULO: Record<PipelineBloco, string> = {
  funil: "Funil de Vendas",
  processos_venda: "Processos de Venda",
};

type Rascunho = Record<string, BlocoAlteracao>;

function rascunhoDe(cfg: BlocosConfig): Rascunho {
  return Object.fromEntries(
    cfg.blocos.map((b) => [b.bloco, { bloco: b.bloco, agent_key: b.agent_key, ativo: b.ativo, etapas: [...b.etapas] }]),
  );
}

function mudou(a: BlocoAlteracao, b: BlocoAtendimento): boolean {
  return (
    a.agent_key !== b.agent_key ||
    a.ativo !== b.ativo ||
    a.etapas.length !== b.etapas.length ||
    a.etapas.some((e, i) => e !== b.etapas[i])
  );
}

/** slug → label per pipeline, from the boards' stage lists (+ the unowned list). */
function useRotulosEtapas(cfg: BlocosConfig | undefined) {
  const funil = funilPipeline.useStages();
  const processos = processosPipeline.useStages();
  return useMemo(() => {
    const mapa: Record<PipelineBloco, Map<string, string>> = { funil: new Map(), processos_venda: new Map() };
    for (const s of funil.data ?? []) if (s.ativo !== false) mapa.funil.set(s.slug, s.label);
    for (const s of processos.data ?? []) if (s.ativo !== false) mapa.processos_venda.set(s.slug, s.label);
    // Every slug the config names is an active stage of its pipeline (§4.1) —
    // keep it selectable even if the stage list has not loaded.
    for (const e of cfg?.etapas_sem_bloco ?? []) if (!mapa[e.pipeline].has(e.slug)) mapa[e.pipeline].set(e.slug, e.label);
    for (const b of cfg?.blocos ?? []) {
      if (!b.pipeline) continue;
      for (const slug of b.etapas) if (!mapa[b.pipeline].has(slug)) mapa[b.pipeline].set(slug, slug);
    }
    return mapa;
  }, [funil.data, processos.data, cfg]);
}

export default function AtendimentoBlocos() {
  const isAdmin = useIsOrgAdmin();
  const q = useAtendimentoBlocos();
  const salvar = useSalvarAtendimentoBlocos();
  const rotulos = useRotulosEtapas(q.data);
  const [rascunho, setRascunho] = useState<Rascunho | null>(null);
  const [erroSalvar, setErroSalvar] = useState<string | null>(null);

  const editando = rascunho !== null && isAdmin;
  const cfg = q.data;

  const alterados = useMemo(
    () => (cfg && rascunho ? cfg.blocos.filter((b) => mudou(rascunho[b.bloco], b)).map((b) => rascunho[b.bloco]) : []),
    [cfg, rascunho],
  );

  const atualizar = (bloco: string, patch: Partial<BlocoAlteracao>) => {
    setErroSalvar(null);
    setRascunho((r) => (r ? { ...r, [bloco]: { ...r[bloco], ...patch } } : r));
  };

  const onSalvar = () => {
    if (!alterados.length) return;
    setErroSalvar(null);
    salvar.mutate(alterados, {
      onSuccess: () => {
        setRascunho(null);
        toast.success("Blocos salvos.");
      },
      onError: (err) => setErroSalvar(mensagemErroBlocos(err)),
    });
  };

  /** Which block owns a slug in the CURRENT draft (option hint only). */
  const donoNoRascunho = (pipeline: PipelineBloco, slug: string, exceto: string): string | null => {
    if (!cfg || !rascunho) return null;
    const dono = cfg.blocos.find((b) => b.pipeline === pipeline && b.bloco !== exceto && rascunho[b.bloco].etapas.includes(slug));
    return dono?.rotulo ?? null;
  };

  return (
    <div className="container max-w-6xl space-y-6 py-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Blocos do atendimento</h1>
          <p className="text-sm text-muted-foreground">
            Cada bloco tem um responsável — um agente ou a equipe — e as etapas do funil que ele cuida. A Maya
            supervisiona os blocos marcados como supervisionados.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {q.isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="blocos-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          {isAdmin && cfg && !editando && (
            <Button size="sm" onClick={() => setRascunho(rascunhoDe(cfg))} data-testid="blocos-editar">
              Editar blocos
            </Button>
          )}
          {editando && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setRascunho(null);
                  setErroSalvar(null);
                }}
                data-testid="blocos-descartar"
              >
                Descartar
              </Button>
              <Button size="sm" onClick={onSalvar} disabled={!alterados.length || salvar.isPending} data-testid="blocos-salvar">
                {salvar.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                Salvar alterações
              </Button>
            </>
          )}
        </div>
      </header>

      {q.showSkeleton ? (
        <div className="space-y-2" data-testid="blocos-skeleton">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : q.isError && !cfg ? (
        <Card>
          <CardContent className="flex items-center justify-between gap-3 py-6" data-testid="blocos-erro-carregar">
            <span className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" /> Não foi possível carregar os blocos.
            </span>
            <Button size="sm" variant="outline" onClick={() => void q.refetch()}>
              Tentar de novo
            </Button>
          </CardContent>
        </Card>
      ) : cfg ? (
        <>
          {!isAdmin && (
            <p className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm" data-testid="blocos-readonly">
              <Info className="h-4 w-4" /> Somente leitura — apenas o proprietário ou um administrador altera os blocos.
            </p>
          )}
          {!cfg.supervisao_ativa && (
            <p className="flex items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-sm" data-testid="blocos-supervisao-off">
              <Info className="h-4 w-4" /> A supervisão está desligada. Marcar um bloco como supervisionado só passa a
              valer quando o proprietário ligar a Supervisão.
            </p>
          )}
          {erroSalvar && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              data-testid="blocos-erro"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{erroSalvar}</span>
            </div>
          )}

          <Card>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full text-sm" data-testid="blocos-tabela">
                <thead className="border-b bg-muted/40 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Bloco</th>
                    <th className="px-3 py-2">Responsável</th>
                    <th className="px-3 py-2">Supervisionado</th>
                    <th className="px-3 py-2">Etapas</th>
                  </tr>
                </thead>
                <tbody>
                  {cfg.blocos.map((b) => {
                    const r = editando ? rascunho![b.bloco] : b;
                    const agentes = cfg.agentes_por_bloco[b.bloco] ?? [];
                    return (
                      <tr key={b.bloco} className="border-b last:border-0 align-top" data-testid={`bloco-${b.bloco}`}>
                        <td className="px-3 py-3 text-muted-foreground">{b.ordem}</td>
                        <td className="px-3 py-3">
                          <div className="font-medium">{b.rotulo}</div>
                          <div className="text-xs text-muted-foreground">
                            {b.pipeline ? PIPELINE_ROTULO[b.pipeline] : "Antes do card"}
                            {b.origem === "padrao" && " · padrão"}
                          </div>
                        </td>
                        <td className="px-3 py-3">
                          {editando ? (
                            <select
                              aria-label={`Responsável — ${b.rotulo}`}
                              className="h-8 rounded-md border bg-background px-2 text-sm"
                              value={r.agent_key ?? ""}
                              onChange={(e) => atualizar(b.bloco, { agent_key: e.target.value || null })}
                              data-testid={`agente-${b.bloco}`}
                            >
                              <option value="">{rotuloAgente(null)}</option>
                              {agentes.map((k) => (
                                <option key={k} value={k}>
                                  {rotuloAgente(k)}
                                </option>
                              ))}
                            </select>
                          ) : (
                            rotuloAgente(r.agent_key)
                          )}
                        </td>
                        <td className="px-3 py-3">
                          {editando ? (
                            <Switch
                              aria-label={`Supervisionado — ${b.rotulo}`}
                              checked={r.ativo}
                              onCheckedChange={(v) => atualizar(b.bloco, { ativo: v })}
                              data-testid={`ativo-${b.bloco}`}
                            />
                          ) : (
                            <Badge variant={r.ativo ? "default" : "outline"}>{r.ativo ? "Sim" : "Não"}</Badge>
                          )}
                        </td>
                        <td className="px-3 py-3">
                          {!b.pipeline ? (
                            <span className="text-xs text-muted-foreground">
                              Primeiro contato e qualificação — sem etapas de funil.
                            </span>
                          ) : (
                            <div className="flex flex-wrap items-center gap-1">
                              {r.etapas.length === 0 && <span className="text-xs text-muted-foreground">Nenhuma etapa</span>}
                              {r.etapas.map((slug) => (
                                <Badge key={slug} variant="secondary">
                                  {rotulos[b.pipeline!].get(slug) ?? slug}
                                </Badge>
                              ))}
                              {editando && (
                                <MultiSelectPopover
                                  label="Etapas"
                                  triggerLabel="Escolher etapas"
                                  testId={`etapas-${b.bloco}`}
                                  options={[...rotulos[b.pipeline].entries()].map(([slug, label]) => {
                                    const dono = donoNoRascunho(b.pipeline!, slug, b.bloco);
                                    return { value: slug, label: dono ? `${label} (em ${dono})` : label };
                                  })}
                                  selected={r.etapas}
                                  onToggle={(slug) =>
                                    atualizar(b.bloco, {
                                      etapas: r.etapas.includes(slug) ? r.etapas.filter((e) => e !== slug) : [...r.etapas, slug],
                                    })
                                  }
                                />
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-2 py-4" data-testid="etapas-sem-bloco">
              <h2 className="text-sm font-semibold">Etapas sem bloco</h2>
              {cfg.etapas_sem_bloco.length === 0 ? (
                <p className="text-sm text-muted-foreground">Todas as etapas do funil têm um bloco responsável.</p>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">
                    Estas etapas não pertencem a nenhum bloco, então a Maya não registra passagens por elas. Atribua cada
                    uma a um bloco{isAdmin ? " em “Editar blocos”" : " (peça ao proprietário ou a um administrador)"}.
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {cfg.etapas_sem_bloco.map((e) => (
                      <Badge key={`${e.pipeline}:${e.slug}`} variant="outline">
                        {e.label} · {PIPELINE_ROTULO[e.pipeline]}
                      </Badge>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}
