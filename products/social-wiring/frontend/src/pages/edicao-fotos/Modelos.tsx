/**
 * Edição de Fotos — Modelos (`/edicao-fotos/modelos`, `status_pagina` row
 * `edicao-fotos-modelos`, migration 128). Platform admin only
 * (`capacidades.pode_administrar_plataforma`).
 *
 * Every model spec is editable here (W8):
 * - the catalog rows — name, snapshot, per-1M prices (text in/out, image
 *   in/out), batch capability, performance/cheap tag, enabled. Each save is
 *   a new immutable version (history per row). An empty price means "no
 *   rate": that model is refused where it would be billed. This is where
 *   `gpt-image-2` gets its price and batch flag (C8);
 * - the model each engine step calls (style guide, evaluator, rule
 *   proposer, note writer) — the image editor stays per org (Configurações);
 * - live metrics + the daily AI note per image model, and a "rewrite now"
 *   button (it runs on the worker, so only while processing is active).
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` /
 * `isRefreshing` come pre-computed off the seed hooks — never `.isLoading`.
 */
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, History, Lock, Pencil, Plus, RefreshCw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@noctusai/lib/api";

import {
  fotosPermissions,
  useAtualizarModelosEtapas,
  useCapacidades,
  useGerarNotasModelos,
  useModeloVersoes,
  useModelos,
  useModelosCatalogo,
  useModelosEtapas,
  useSalvarModeloCatalogo,
  type EtapaModelo,
  type ModeloCatalogoAdmin,
  type ModeloCatalogoBody,
  type ModeloCatalogoItem,
  type ModeloKind,
  type ModeloPrecos,
  type TagPerformance,
} from "@/hooks/useEdicaoFotos";

const KIND_ROTULO: Record<ModeloKind, string> = {
  image_edit: "Edição de imagem",
  vision: "Visão (texto + imagem)",
  chat: "Texto",
};

const ETAPA_ROTULO: Record<EtapaModelo, string> = {
  guia: "Construtor do guia de estilo",
  avaliador: "Avaliador das edições",
  regras: "Propositor de regras",
  notas: "Redator das notas diárias",
};

const PRECO_CAMPOS: { key: keyof ModeloPrecos; body: keyof ModeloCatalogoBody; label: string }[] = [
  { key: "entrada_texto", body: "preco_entrada_texto_1m", label: "Texto — entrada" },
  { key: "saida_texto", body: "preco_saida_texto_1m", label: "Texto — saída" },
  { key: "entrada_imagem", body: "preco_entrada_imagem_1m", label: "Imagem — entrada" },
  { key: "saida_imagem", body: "preco_saida_imagem_1m", label: "Imagem — saída" },
];

const SEM_TAG = "__nenhuma__";
const MODEL_ID_RE = /^[a-z0-9][a-z0-9._-]{0,119}$/;

function descricaoErro(err: unknown): string | undefined {
  if (err instanceof ApiError) {
    if (err.code === "modelo_em_uso") return "O modelo está em uso por uma etapa — troque a etapa antes de desativar.";
    if (err.code === "modelo_sem_preco") return "O modelo não tem todos os preços cadastrados.";
    if (err.code === "modelo_desconhecido") return "Modelo desativado ou de outro tipo.";
    if (err.code === "modelo_versao_conflito") return "Outra pessoa salvou este modelo agora — recarregue.";
  }
  return err instanceof Error ? err.message : undefined;
}

function formatarPreco(valor: number | null): string {
  return valor === null ? "—" : `US$ ${valor.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}`;
}

function formatarPercentual(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "—" : `${(valor * 100).toFixed(1)}%`;
}

function formatarData(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("pt-BR") : "—";
}

export default function Modelos() {
  const { capacidades, showSkeleton } = useCapacidades();
  if (showSkeleton) return <ListaSkeleton />;
  if (!fotosPermissions.podeAdministrarPlataforma(capacidades)) return <AcessoRestrito />;
  return <ModelosView />;
}

function ModelosView() {
  const catalogo = useModelosCatalogo();
  const visao = useModelos();
  const gerarNotas = useGerarNotasModelos();
  const [kind, setKind] = useState<ModeloKind>("image_edit");
  const [editando, setEditando] = useState<ModeloCatalogoAdmin | "novo" | null>(null);
  const [historico, setHistorico] = useState<ModeloCatalogoAdmin | null>(null);

  const visaoPorId = useMemo(
    () => new Map(visao.modelos.map((m) => [m.id, m] as const)),
    [visao.modelos],
  );

  async function handleGerarNotas() {
    try {
      await gerarNotas.mutateAsync();
      toast.success("Reescrita das notas enfileirada — roda quando o processamento estiver ativo.");
    } catch (err) {
      toast.error("Não foi possível enfileirar as notas.", { description: descricaoErro(err) });
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Modelos</h1>
          <p className="text-sm text-muted-foreground">
            Preços, capacidades e modelos por etapa. Cada alteração vira uma nova versão.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {catalogo.isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="modelos-atualizando">
              <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <Button variant="outline" onClick={handleGerarNotas} disabled={gerarNotas.isPending}>
            <Sparkles className="mr-2 h-4 w-4" />
            {gerarNotas.isPending ? "Enfileirando…" : "Reescrever notas agora"}
          </Button>
          <Button onClick={() => setEditando("novo")}>
            <Plus className="mr-2 h-4 w-4" /> Adicionar modelo
          </Button>
        </div>
      </div>

      <EtapasCard catalogo={catalogo.modelos} carregandoCatalogo={catalogo.showSkeleton} />

      {catalogo.error ? (
        <ErrorState onRetry={() => catalogo.refetch()} />
      ) : catalogo.showSkeleton ? (
        <ListaSkeleton />
      ) : (
        <Tabs value={kind} onValueChange={(v) => setKind(v as ModeloKind)}>
          <TabsList>
            {(Object.keys(KIND_ROTULO) as ModeloKind[]).map((k) => (
              <TabsTrigger key={k} value={k}>
                {KIND_ROTULO[k]}
              </TabsTrigger>
            ))}
          </TabsList>
          {(Object.keys(KIND_ROTULO) as ModeloKind[]).map((k) => {
            const linhas = catalogo.modelos.filter((m) => m.kind === k);
            return (
              <TabsContent key={k} value={k} className="space-y-3">
                {linhas.length === 0 ? (
                  <Card data-testid={`modelos-vazio-${k}`}>
                    <CardContent className="py-10 text-center text-sm text-muted-foreground">
                      Nenhum modelo deste tipo.
                    </CardContent>
                  </Card>
                ) : (
                  linhas.map((m) => (
                    <ModeloCard
                      key={`${m.kind}-${m.id}`}
                      modelo={m}
                      visao={m.kind === "image_edit" ? visaoPorId.get(m.id) : undefined}
                      carregandoVisao={visao.showSkeleton}
                      onEditar={() => setEditando(m)}
                      onHistorico={() => setHistorico(m)}
                    />
                  ))
                )}
              </TabsContent>
            );
          })}
        </Tabs>
      )}

      {editando !== null && (
        <ModeloDialog
          modelo={editando === "novo" ? null : editando}
          kindInicial={kind}
          onClose={() => setEditando(null)}
        />
      )}
      {historico !== null && <HistoricoDialog modelo={historico} onClose={() => setHistorico(null)} />}
    </div>
  );
}

function EtapasCard({
  catalogo,
  carregandoCatalogo,
}: {
  catalogo: ModeloCatalogoAdmin[];
  carregandoCatalogo: boolean;
}) {
  const { etapas, showSkeleton, error, refetch } = useModelosEtapas();
  const atualizar = useAtualizarModelosEtapas();

  async function salvar(etapa: EtapaModelo, modelo: string | null) {
    try {
      await atualizar.mutateAsync({ [etapa]: modelo });
      toast.success(modelo ? "Modelo da etapa atualizado." : "Etapa voltou ao modelo padrão.");
    } catch (err) {
      toast.error("Não foi possível trocar o modelo da etapa.", { description: descricaoErro(err) });
    }
  }

  return (
    <Card data-testid="etapas-card">
      <CardContent className="space-y-4 p-6">
        <div>
          <h2 className="font-medium">Modelos por etapa</h2>
          <p className="text-sm text-muted-foreground">
            O modelo de edição de imagem é escolhido por organização, em Configurações.
          </p>
        </div>
        {error ? (
          <ErrorState onRetry={() => refetch()} />
        ) : showSkeleton || carregandoCatalogo ? (
          <Skeleton className="h-40 w-full" data-testid="etapas-loading" />
        ) : (
          <div className="space-y-3">
            {etapas.map((e) => {
              const opcoes = catalogo.filter((m) => m.kind === e.tipo && m.habilitado && m.com_preco);
              return (
                <div key={e.etapa} className="flex flex-wrap items-center gap-3" data-testid={`etapa-${e.etapa}`}>
                  <Label className="w-56 shrink-0">{ETAPA_ROTULO[e.etapa]}</Label>
                  <Select
                    value={e.modelo}
                    onValueChange={(valor) => salvar(e.etapa, valor)}
                    disabled={atualizar.isPending}
                  >
                    <SelectTrigger className="w-72" aria-label={ETAPA_ROTULO[e.etapa]}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {!opcoes.some((m) => m.id === e.modelo) && (
                        <SelectItem value={e.modelo} disabled>
                          {e.modelo} (indisponível)
                        </SelectItem>
                      )}
                      {opcoes.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.nome}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {e.personalizado ? (
                    <Button variant="ghost" size="sm" onClick={() => salvar(e.etapa, null)} disabled={atualizar.isPending}>
                      Voltar ao padrão ({e.padrao})
                    </Button>
                  ) : (
                    <Badge variant="outline">padrão</Badge>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ModeloCard({
  modelo,
  visao,
  carregandoVisao,
  onEditar,
  onHistorico,
}: {
  modelo: ModeloCatalogoAdmin;
  visao: ModeloCatalogoItem | undefined;
  carregandoVisao: boolean;
  onEditar: () => void;
  onHistorico: () => void;
}) {
  return (
    <Card data-testid={`modelo-${modelo.id}`} className={modelo.habilitado ? undefined : "opacity-70"}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-medium">{modelo.nome}</p>
            <p className="font-mono text-xs text-muted-foreground">{modelo.versao}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {!modelo.habilitado && <Badge variant="secondary">Desativado</Badge>}
            {!modelo.com_preco && <Badge variant="destructive">Sem preço</Badge>}
            {modelo.suporta_batch && <Badge variant="outline">Batch (Econômico)</Badge>}
            {modelo.tag_performance && (
              <Badge variant="outline">{modelo.tag_performance === "performance" ? "Performance" : "Econômico"}</Badge>
            )}
            {modelo.origem !== "catalogo" && (
              <Badge variant="outline">{modelo.origem === "adicionado" ? "Adicionado" : "Personalizado"} · v{modelo.revisao}</Badge>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          {PRECO_CAMPOS.map((c) => (
            <div key={c.key}>
              <p className="text-xs text-muted-foreground">{c.label} /1M</p>
              <p>{formatarPreco(modelo.precos[c.key])}</p>
            </div>
          ))}
        </div>

        {modelo.kind === "image_edit" && modelo.habilitado && (
          carregandoVisao ? (
            <Skeleton className="h-12 w-full" />
          ) : visao?.metricas ? (
            <div className="rounded-md bg-muted/40 p-3 text-sm" data-testid={`metricas-${modelo.id}`}>
              <p>
                Fotos decididas: {visao.metricas.total_fotos ?? 0} · Aprovação:{" "}
                {formatarPercentual(visao.metricas.taxa_aprovacao)} · Nota média da IA:{" "}
                {visao.metricas.score_medio_ia === null ? "—" : visao.metricas.score_medio_ia.toFixed(2)} · Custo por
                foto aprovada: {formatarPreco(visao.metricas.custo_por_foto_aprovada)}
              </p>
              <p className="mt-1 text-muted-foreground">
                {visao.nota_recomendacao
                  ? `${visao.nota_recomendacao} (${formatarData(visao.nota_gerada_em)})`
                  : "Sem nota da IA ainda."}
              </p>
            </div>
          ) : null
        )}

        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onEditar}>
            <Pencil className="mr-1.5 h-3.5 w-3.5" /> Editar
          </Button>
          <Button variant="ghost" size="sm" onClick={onHistorico} disabled={modelo.revisao === null}>
            <History className="mr-1.5 h-3.5 w-3.5" /> Histórico
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function precoTexto(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? "" : String(valor);
}

function formInicial(modelo: ModeloCatalogoAdmin | null, kind: ModeloKind): ModeloCatalogoBody {
  if (!modelo) {
    return {
      kind,
      nome: "",
      descricao: null,
      snapshot: null,
      habilitado: true,
      preco_entrada_texto_1m: null,
      preco_saida_texto_1m: null,
      preco_entrada_imagem_1m: null,
      preco_saida_imagem_1m: null,
      suporta_batch: false,
      tag_performance: null,
    };
  }
  return {
    kind: modelo.kind,
    nome: modelo.nome,
    descricao: modelo.descricao,
    snapshot: modelo.snapshot,
    habilitado: modelo.habilitado,
    preco_entrada_texto_1m: precoTexto(modelo.precos.entrada_texto) || null,
    preco_saida_texto_1m: precoTexto(modelo.precos.saida_texto) || null,
    preco_entrada_imagem_1m: precoTexto(modelo.precos.entrada_imagem) || null,
    preco_saida_imagem_1m: precoTexto(modelo.precos.saida_imagem) || null,
    suporta_batch: modelo.suporta_batch,
    tag_performance: modelo.tag_performance,
  };
}

function precoValido(valor: string | null): boolean {
  return valor === null || /^\d+(\.\d+)?$/.test(valor);
}

function ModeloDialog({
  modelo,
  kindInicial,
  onClose,
}: {
  modelo: ModeloCatalogoAdmin | null;
  kindInicial: ModeloKind;
  onClose: () => void;
}) {
  const salvar = useSalvarModeloCatalogo();
  const [id, setId] = useState(modelo?.id ?? "");
  const [form, setForm] = useState<ModeloCatalogoBody>(() => formInicial(modelo, kindInicial));

  const idValido = MODEL_ID_RE.test(id);
  const precosValidos = PRECO_CAMPOS.every((c) => precoValido(form[c.body] as string | null));
  const semPreco =
    form.kind === "image_edit"
      ? !form.preco_entrada_texto_1m || !form.preco_entrada_imagem_1m || !form.preco_saida_imagem_1m
      : !form.preco_entrada_texto_1m || !form.preco_saida_texto_1m;

  function setPreco(campo: keyof ModeloCatalogoBody, valor: string) {
    const limpo = valor.trim().replace(",", ".");
    setForm({ ...form, [campo]: limpo === "" ? null : limpo });
  }

  async function handleSalvar() {
    try {
      const salvo = await salvar.mutateAsync({ id, body: form });
      if (salvo.recarregado) {
        toast.success("Modelo salvo.");
      } else {
        toast.warning("Modelo salvo, mas este servidor ainda não recarregou o catálogo — veja Processamento.");
      }
      onClose();
    } catch (err) {
      toast.error("Não foi possível salvar o modelo.", { description: descricaoErro(err) });
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{modelo ? `Editar ${modelo.nome}` : "Adicionar modelo"}</DialogTitle>
          <DialogDescription>
            Preços em US$ por 1 milhão de tokens. Campo vazio = sem preço: o modelo fica bloqueado onde seria cobrado.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {!modelo && (
            <>
              <div className="space-y-1">
                <Label htmlFor="modelo-id">Identificador (OpenAI)</Label>
                <Input id="modelo-id" value={id} onChange={(e) => setId(e.target.value.trim())} placeholder="gpt-image-2" />
                {id !== "" && !idValido && (
                  <p className="text-xs text-destructive">Use letras minúsculas, números, ponto, hífen ou sublinhado.</p>
                )}
              </div>
              <div className="space-y-1">
                <Label htmlFor="modelo-kind">Tipo</Label>
                <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v as ModeloKind })}>
                  <SelectTrigger id="modelo-kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(KIND_ROTULO) as ModeloKind[]).map((k) => (
                      <SelectItem key={k} value={k}>
                        {KIND_ROTULO[k]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="modelo-nome">Nome</Label>
              <Input id="modelo-nome" value={form.nome ?? ""} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="modelo-snapshot">Snapshot/versão</Label>
              <Input
                id="modelo-snapshot"
                value={form.snapshot ?? ""}
                placeholder="-2026-09-08"
                onChange={(e) => setForm({ ...form, snapshot: e.target.value || null })}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {PRECO_CAMPOS.map((c) => (
              <div key={c.body} className="space-y-1">
                <Label htmlFor={`preco-${c.key}`}>{c.label}</Label>
                <Input
                  id={`preco-${c.key}`}
                  inputMode="decimal"
                  value={(form[c.body] as string | null) ?? ""}
                  onChange={(e) => setPreco(c.body, e.target.value)}
                />
              </div>
            ))}
          </div>
          {!precosValidos && <p className="text-xs text-destructive">Preços devem ser números não negativos.</p>}
          {precosValidos && semPreco && (
            <p className="text-xs text-amber-600" data-testid="aviso-sem-preco">
              Faltam preços: este modelo não poderá ser usado até eles serem preenchidos.
            </p>
          )}
          <div className="flex items-center justify-between">
            <Label htmlFor="modelo-habilitado">Habilitado</Label>
            <Switch
              id="modelo-habilitado"
              checked={form.habilitado}
              onCheckedChange={(v) => setForm({ ...form, habilitado: v })}
            />
          </div>
          {form.kind === "image_edit" && (
            <div className="flex items-center justify-between">
              <Label htmlFor="modelo-batch">Suporta Batch API (modo Econômico)</Label>
              <Switch
                id="modelo-batch"
                checked={form.suporta_batch}
                onCheckedChange={(v) => setForm({ ...form, suporta_batch: v })}
              />
            </div>
          )}
          <div className="space-y-1">
            <Label htmlFor="modelo-tag">Recomendação</Label>
            <Select
              value={form.tag_performance ?? SEM_TAG}
              onValueChange={(v) => setForm({ ...form, tag_performance: v === SEM_TAG ? null : (v as TagPerformance) })}
            >
              <SelectTrigger id="modelo-tag">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SEM_TAG}>Nenhuma</SelectItem>
                <SelectItem value="performance">Performance</SelectItem>
                <SelectItem value="economico">Econômico</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSalvar} disabled={salvar.isPending || !idValido || !precosValidos}>
            {salvar.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function HistoricoDialog({ modelo, onClose }: { modelo: ModeloCatalogoAdmin; onClose: () => void }) {
  const { versoes, showSkeleton, error } = useModeloVersoes(modelo.id, modelo.kind);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Histórico — {modelo.nome}</DialogTitle>
          <DialogDescription>Cada versão é imutável; custos já registrados guardam o valor da época.</DialogDescription>
        </DialogHeader>
        {error ? (
          <p className="text-sm text-destructive">Não foi possível carregar o histórico.</p>
        ) : showSkeleton ? (
          <Skeleton className="h-24 w-full" data-testid="historico-loading" />
        ) : versoes.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sem versões salvas.</p>
        ) : (
          <ul className="max-h-80 space-y-2 overflow-y-auto text-sm" data-testid="historico-lista">
            {versoes.map((v) => (
              <li key={v.revisao} className="rounded-md border p-2">
                <p className="font-medium">
                  v{v.revisao} · {formatarData(v.atualizado_em)} {v.habilitado ? "" : "· desativado"}
                </p>
                <p className="text-muted-foreground">
                  {PRECO_CAMPOS.map((c) => `${c.label}: ${formatarPreco(v.precos[c.key])}`).join(" · ")}
                  {v.suporta_batch ? " · batch" : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="modelos-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da plataforma.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function ListaSkeleton() {
  return (
    <div className="space-y-3" data-testid="modelos-loading">
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
        <p className="font-medium">Não foi possível carregar os modelos.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
