/**
 * Edição de Fotos — Pool de referências (`/edicao-fotos/referencias`,
 * `status_pagina` row `edicao-fotos-referencias`, migration 128). The GLOBAL
 * before/after pool the style guide is built from (contract §5).
 *
 * Who: platform admin ∨ photo curator (`capacidades.pode_gerir_pool`). The
 * pair LIMIT (counted in pairs; blank = unlimited) is a platform setting, so
 * only a platform admin (`dashboard === "platform"`) sees its editor — a
 * curator sees the occupancy but cannot change the limit.
 *
 * Upload: `antes` + `depois` files, a room from the server's fixed list, edit
 * types, a note. A full pool disables the form; the server still answers 409
 * `pool_cheio` if a race fills it first. Removal ARCHIVES (kept for history,
 * no longer counted) through the seed `<ReferencePairCard/>`.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` and
 * `isRefreshing` come pre-computed off the seed hooks — never `.isLoading`.
 */
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AlertCircle, ImageOff, Lock, RefreshCw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@noctusai/lib/api";
import { ReferencePairCard } from "@noctusai/lib/photo-editing/ReferencePairCard";

import {
  fotosPermissions,
  useArquivarReferencia,
  useAtualizarConfiguracoesPlataforma,
  useCapacidades,
  useConfiguracoesPlataforma,
  useCriarReferencia,
  useReferencias,
  type PoolReferencias,
} from "@/hooks/useEdicaoFotos";
import { rotuloComodo, rotuloTipoEdicao } from "./rotulos";

const PAGE_SIZE = 24;

function mensagemErro(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.code === "pool_cheio") {
    return "O pool está cheio — arquive um par ou aumente o limite.";
  }
  return err instanceof Error ? err.message : fallback;
}

export default function Referencias() {
  const { capacidades, showSkeleton: capsCarregando } = useCapacidades();
  const podeGerir = fotosPermissions.podeGerirPool(capacidades);
  const ehPlataforma = fotosPermissions.dashboardScope(capacidades) === "platform";

  if (capsCarregando) return <PageSkeleton />;
  if (!podeGerir) return <AcessoRestrito />;
  return <PoolReferenciasView ehPlataforma={ehPlataforma} />;
}

function PoolReferenciasView({ ehPlataforma }: { ehPlataforma: boolean }) {
  const [page, setPage] = useState(1);
  const [incluirArquivadas, setIncluirArquivadas] = useState(false);
  const { referencias, total, pool, opcoes, showSkeleton, isRefreshing, error, refetch } =
    useReferencias({ page, pageSize: PAGE_SIZE, incluirArquivadas });
  const arquivar = useArquivarReferencia();
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function handleArquivar(id: string) {
    try {
      await arquivar.mutateAsync(id);
      toast.success("Par arquivado.");
    } catch (err) {
      toast.error("Não foi possível arquivar o par.", { description: mensagemErro(err, "") });
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Pool de referências</h1>
          <p className="text-sm text-muted-foreground">
            Pares antes/depois que definem o padrão da empresa. O guia de estilo é gerado a partir deles.
          </p>
        </div>
        {isRefreshing && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="referencias-atualizando">
            <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
          </span>
        )}
      </div>

      {pool && <OcupacaoPool pool={pool} />}
      {ehPlataforma && <LimitePool />}

      {opcoes && <NovoParForm opcoes={opcoes} bloqueado={!!pool?.cheio} />}

      <div className="flex items-center gap-2">
        <Switch
          id="incluir-arquivadas"
          checked={incluirArquivadas}
          onCheckedChange={(v) => {
            setIncluirArquivadas(v);
            setPage(1);
          }}
        />
        <Label htmlFor="incluir-arquivadas">Mostrar arquivadas</Label>
      </div>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <GridSkeleton />
      ) : referencias.length === 0 ? (
        <Card data-testid="referencias-vazio">
          <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
            <ImageOff className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Nenhum par de referência ainda.</p>
            <p className="text-sm text-muted-foreground">Envie o primeiro par antes/depois acima.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="referencias-grid">
            {referencias.map((ref) => (
              <ReferencePairCard
                key={ref.id}
                referencia={ref}
                onArquivar={handleArquivar}
                isArquivando={arquivar.isPending && arquivar.variables === ref.id}
                formatComodo={rotuloComodo}
                formatTipoEdicao={rotuloTipoEdicao}
              />
            ))}
          </div>
          {totalPaginas > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {page} de {totalPaginas}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPaginas}
                onClick={() => setPage(page + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function OcupacaoPool({ pool }: { pool: PoolReferencias }) {
  return (
    <Card className={pool.cheio ? "border-amber-500/40 bg-amber-500/5" : undefined} data-testid="pool-ocupacao">
      <CardContent className="flex items-center gap-3 p-4 text-sm">
        {pool.cheio && <AlertCircle className="h-5 w-5 shrink-0 text-amber-600" />}
        <span>
          {pool.limite_pares === null
            ? `${pool.pares_ativos} pares ativos · sem limite`
            : `${pool.pares_ativos} de ${pool.limite_pares} pares ativos`}
          {pool.cheio && " — pool cheio: novos envios estão bloqueados."}
        </span>
      </CardContent>
    </Card>
  );
}

function LimitePool() {
  const { configuracoes, showSkeleton } = useConfiguracoesPlataforma();
  const atualizar = useAtualizarConfiguracoesPlataforma();
  const [valor, setValor] = useState("");

  useEffect(() => {
    if (configuracoes) setValor(configuracoes.limite_pares_referencia?.toString() ?? "");
  }, [configuracoes]);

  if (showSkeleton || !configuracoes) return <Skeleton className="h-16 w-full" />;

  const numero = valor.trim() === "" ? 0 : Number(valor);
  const invalido = !Number.isInteger(numero) || numero < 0;

  async function handleSalvar(e: FormEvent) {
    e.preventDefault();
    if (!configuracoes || invalido) return;
    try {
      await atualizar.mutateAsync({ ...configuracoes, limite_pares_referencia: numero });
      toast.success(numero === 0 ? "Pool sem limite." : `Limite definido em ${numero} pares.`);
    } catch (err) {
      toast.error("Não foi possível salvar o limite.", { description: mensagemErro(err, "") });
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <form className="flex flex-wrap items-end gap-3" onSubmit={handleSalvar}>
          <div className="space-y-1.5">
            <Label htmlFor="limite-pares">Limite do pool (em pares)</Label>
            <Input
              id="limite-pares"
              type="number"
              min={0}
              step={1}
              placeholder="Sem limite"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              className="w-40"
            />
          </div>
          <Button type="submit" variant="outline" disabled={invalido || atualizar.isPending}>
            {atualizar.isPending ? "Salvando…" : "Salvar limite"}
          </Button>
          <p className="text-xs text-muted-foreground">Vazio ou 0 = sem limite. Pares arquivados não contam.</p>
        </form>
      </CardContent>
    </Card>
  );
}

function NovoParForm({
  opcoes,
  bloqueado,
}: {
  opcoes: { comodos: string[]; tipos_edicao: string[] };
  bloqueado: boolean;
}) {
  const criar = useCriarReferencia();
  const [antes, setAntes] = useState<File | null>(null);
  const [depois, setDepois] = useState<File | null>(null);
  const [comodo, setComodo] = useState<string>("");
  const [tipos, setTipos] = useState<string[]>([]);
  const [nota, setNota] = useState("");
  const [formKey, setFormKey] = useState(0);

  const podeEnviar = !bloqueado && !!antes && !!depois && !!comodo && !criar.isPending;

  function toggleTipo(value: string) {
    setTipos((atual) => (atual.includes(value) ? atual.filter((t) => t !== value) : [...atual, value]));
  }

  async function handleEnviar(e: FormEvent) {
    e.preventDefault();
    if (!antes || !depois || !comodo) return;
    try {
      await criar.mutateAsync({ antes, depois, comodo, tipos_edicao: tipos, nota: nota.trim() || null });
      toast.success("Par de referência enviado.");
      setAntes(null);
      setDepois(null);
      setComodo("");
      setTipos([]);
      setNota("");
      setFormKey((k) => k + 1); // clears the file inputs
    } catch (err) {
      toast.error("Não foi possível enviar o par.", { description: mensagemErro(err, "") });
    }
  }

  return (
    <Card>
      <CardContent className="p-6">
        <form key={formKey} className="grid gap-4 md:grid-cols-2" onSubmit={handleEnviar} data-testid="novo-par-form">
          <div className="space-y-1.5">
            <Label htmlFor="ref-antes">Antes</Label>
            <Input
              id="ref-antes"
              type="file"
              accept="image/*"
              disabled={bloqueado}
              onChange={(e) => setAntes(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ref-depois">Depois</Label>
            <Input
              id="ref-depois"
              type="file"
              accept="image/*"
              disabled={bloqueado}
              onChange={(e) => setDepois(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ref-comodo">Cômodo</Label>
            {/* Native select: a required choice from a short fixed list, no default. */}
            <select
              id="ref-comodo"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
              value={comodo}
              disabled={bloqueado}
              onChange={(e) => setComodo(e.target.value)}
            >
              <option value="" disabled>
                Selecione o cômodo
              </option>
              {opcoes.comodos.map((c) => (
                <option key={c} value={c}>
                  {rotuloComodo(c)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label>Tipos de edição mostrados</Label>
            <div className="grid grid-cols-2 gap-2">
              {opcoes.tipos_edicao.map((t) => (
                <label key={t} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={tipos.includes(t)}
                    disabled={bloqueado}
                    onCheckedChange={() => toggleTipo(t)}
                    aria-label={rotuloTipoEdicao(t)}
                  />
                  {rotuloTipoEdicao(t)}
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="ref-nota">Nota</Label>
            <Textarea
              id="ref-nota"
              maxLength={2000}
              placeholder="O que este par ensina (ex.: céu azul limpo, sem saturar a madeira)"
              value={nota}
              disabled={bloqueado}
              onChange={(e) => setNota(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <Button type="submit" disabled={!podeEnviar}>
              <Upload className="mr-2 h-4 w-4" />
              {criar.isPending ? "Enviando…" : "Enviar par"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="referencias-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da plataforma e curadores de fotos.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6" data-testid="referencias-carregando">
      <Skeleton className="h-8 w-1/3" />
      <GridSkeleton />
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="referencias-loading">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-56 w-full" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar o pool de referências.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
