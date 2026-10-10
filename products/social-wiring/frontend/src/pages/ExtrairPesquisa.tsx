/**
 * Extrair Pesquisa (`/media-creation/pesquisa/extrair`) — pick the marca's own
 * posts and extract research items and/or viral topics from them. Contract:
 * projects/core-studio/specs/pesquisa-wave2-contract.md §4.3.
 *
 * - Job progress is polled by React Query (`useExtracaoJob`, 2 s while
 *   queued/running, stops on terminal); an active job resumes on mount through
 *   `/extracoes/limites.extracao_ativa_id`.
 * - Loading: two signals off `data` (`showSkeleton` / `isRefreshing`), never
 *   `.isLoading` (lying-loading-state.md).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ExtracoesRecentes } from "@/components/pesquisa/extrair/ExtracoesRecentes";
import { TIPO_ROTULO } from "@/components/pesquisa/extrair/format";
import { PostCard, postKey } from "@/components/pesquisa/extrair/PostCard";
import { ProgressPanel } from "@/components/pesquisa/extrair/ProgressPanel";
import { SelectionBar } from "@/components/pesquisa/extrair/SelectionBar";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import {
  isJobActive,
  useCancelarExtracao,
  useExtracaoJob,
  useExtracaoLimites,
  useExtracoesRecentes,
  useFontes,
  useInvalidarExtracao,
  usePostsFonte,
  useSubmeterExtracao,
  type ExtracaoTipo,
  type Fonte,
  type PostFonte,
  type PostRef,
} from "@/hooks/usePesquisaExtracao";

const TIPOS: ExtracaoTipo[] = ["pesquisa", "assuntos_virais"];

const rotuloFonte = (f: Fonte) =>
  f.kind === "mc_post" ? "Posts criados" : f.kind === "instagram_media" ? `@${f.label.replace(/^@/, "")}` : f.label;

const fonteKey = (f: Fonte) => `${f.kind}:${f.account_id ?? ""}`;

function tiposDoQuery(raw: string | null): ExtracaoTipo[] {
  if (!raw) return ["pesquisa"];
  const sel = TIPOS.filter((t) => raw.split(",").includes(t));
  return sel.length > 0 ? sel : ["pesquisa"];
}

const TOAST_TERMINAL: Record<string, (m: string) => void> = {
  completed: (m) => toast.success(m),
  completed_with_errors: (m) => toast.info(m),
  failed: (m) => toast.error(m),
  cancelled: (m) => toast.info(m),
};
const TOAST_TEXTO: Record<string, string> = {
  completed: "Extração concluída!",
  completed_with_errors: "Extração concluída com avisos",
  failed: "A extração falhou",
  cancelled: "Extração cancelada",
};

export default function ExtrairPesquisa() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [params, setParams] = useSearchParams();
  const tipos = tiposDoQuery(params.get("tipo"));

  const [fonteSel, setFonteSel] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [selecionados, setSelecionados] = useState<Map<string, PostRef>>(new Map());
  const [reextrair, setReextrair] = useState(false);
  const [jobLocalId, setJobLocalId] = useState<string | null>(null);

  const fontesQ = useFontes(marcaId);
  const fontes = fontesQ.data ?? [];
  const fonte = fontes.find((f) => fonteKey(f) === fonteSel) ?? fontes[0] ?? null;

  const postsQ = usePostsFonte(marcaId, fonte, busca);
  const limitesQ = useExtracaoLimites(marcaId);
  const limites = limitesQ.data;
  const recentesQ = useExtracoesRecentes(marcaId);

  const jobId = jobLocalId ?? limites?.extracao_ativa_id ?? null;
  const jobQ = useExtracaoJob(jobId);
  const job = jobQ.data ?? null;

  const submeter = useSubmeterExtracao();
  const cancelar = useCancelarExtracao();
  const invalidar = useInvalidarExtracao();

  // Terminal transition: toast once per job+status and refresh lists/counts/limits.
  const notificado = useRef<string | null>(null);
  useEffect(() => {
    if (!job || isJobActive(job.status)) return;
    const k = `${job.id}:${job.status}`;
    if (notificado.current === k) return;
    notificado.current = k;
    TOAST_TERMINAL[job.status]?.(TOAST_TEXTO[job.status] ?? "Extração finalizada");
    invalidar();
  }, [job, invalidar]);

  // Selection never outlives the marca it was made for.
  useEffect(() => {
    setSelecionados(new Map());
    setJobLocalId(null);
    setFonteSel(null);
  }, [marcaId]);

  const max = limites?.max_posts_por_job ?? 0;
  const jobAtivo = !!job && isJobActive(job.status);

  function alternarTipo(t: ExtracaoTipo) {
    const next = tipos.includes(t) ? tipos.filter((x) => x !== t) : [...tipos, t];
    if (next.length === 0) return; // at least one stays checked
    const p = new URLSearchParams(params);
    p.set("tipo", TIPOS.filter((x) => next.includes(x)).join(","));
    setParams(p, { replace: true });
  }

  function alternarPost(post: PostFonte) {
    const k = postKey(post);
    setSelecionados((prev) => {
      const next = new Map(prev);
      if (next.has(k)) next.delete(k);
      else if (max === 0 || next.size < max) next.set(k, { kind: post.kind, account_id: post.account_id, id: post.id });
      return next;
    });
  }

  function selecionarRecentes() {
    const recentes = postsQ.posts.filter((p) => p.analisavel).slice(0, max);
    setSelecionados(new Map(recentes.map((p) => [postKey(p), { kind: p.kind, account_id: p.account_id, id: p.id }])));
  }

  const bloqueio = useMemo(() => {
    if (!limites) return null;
    if (!limites.worker_ativo) return "Extração indisponível no momento";
    if (limites.extracao_ativa_id || jobAtivo) return "Já existe uma extração em andamento";
    if (limites.extracoes_restantes_hoje <= 0) return "Limite diário de extrações atingido";
    if (limites.tarefas_restantes_hoje_org <= 0) return "Limite diário de posts da organização atingido";
    return null;
  }, [limites, jobAtivo]);

  async function extrair() {
    if (!marcaId || selecionados.size === 0) return;
    try {
      const novo = await submeter.mutateAsync({
        marca_id: marcaId,
        tipos,
        posts: [...selecionados.values()],
        reextrair,
      });
      setJobLocalId(novo.id);
      setSelecionados(new Map());
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "Não foi possível iniciar a extração.");
    }
  }

  async function cancelarJob() {
    if (!job) return;
    try {
      await cancelar.mutateAsync(job.id);
    } catch (err) {
      toast.error(err instanceof Error && err.message ? err.message : "Não foi possível cancelar.");
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Extrair Pesquisa</h1>
          <p className="text-sm text-muted-foreground">
            Selecione posts do seu conteúdo para extrair itens de pesquisa e assuntos virais.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button asChild variant="outline">
            <Link to="/media-creation/pesquisa">Minha Pesquisa</Link>
          </Button>
        </div>
      </header>

      <fieldset className="flex flex-wrap items-center gap-4 text-sm">
        <legend className="sr-only">Extrair</legend>
        <span className="font-medium">Extrair:</span>
        {TIPOS.map((t) => (
          <label key={t} className="flex items-center gap-2">
            <Checkbox checked={tipos.includes(t)} onCheckedChange={() => alternarTipo(t)} />
            {TIPO_ROTULO[t]}
          </label>
        ))}
      </fieldset>

      {job && (
        <ProgressPanel
          job={job}
          onCancelar={cancelarJob}
          cancelando={cancelar.isPending}
          onTentarNovamente={() => setJobLocalId(null)}
        />
      )}

      {marcasQ.isError || fontesQ.isError ? (
        <div role="alert" className="rounded-lg border border-destructive/40 p-4 text-sm">
          Não foi possível carregar as fontes.{" "}
          <Button type="button" variant="link" size="sm" onClick={() => fontesQ.refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : fontesQ.showSkeleton ? (
        <Skeleton className="h-40 w-full" aria-label="Carregando fontes" />
      ) : fontes.length === 0 ? (
        <div className="rounded-lg border p-6 text-center text-sm">
          <p>Nenhuma conta conectada para esta marca</p>
          <Link to="/marcas" className="text-primary hover:underline">
            Conectar contas
          </Link>
        </div>
      ) : (
        <>
          <div role="tablist" className="flex flex-wrap gap-2">
            {fontes.map((f) => (
              <Button
                key={fonteKey(f)}
                role="tab"
                aria-selected={fonte ? fonteKey(f) === fonteKey(fonte) : false}
                variant={fonte && fonteKey(f) === fonteKey(fonte) ? "default" : "outline"}
                size="sm"
                onClick={() => setFonteSel(fonteKey(f))}
              >
                {rotuloFonte(f)} ({f.total_posts})
              </Button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Input
              placeholder="Buscar no texto do post..."
              aria-label="Buscar no texto do post"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="max-w-md"
            />
            {(postsQ.isRefreshing || fontesQ.isRefreshing) && (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-label="Atualizando" />
            )}
          </div>

          {postsQ.isError ? (
            <div role="alert" className="rounded-lg border border-destructive/40 p-4 text-sm">
              Não foi possível carregar os posts.{" "}
              <Button type="button" variant="link" size="sm" onClick={() => postsQ.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : postsQ.showSkeleton ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-40" />
              ))}
            </div>
          ) : postsQ.posts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {busca.trim()
                ? "Nenhum post encontrado para esta busca."
                : fonte?.kind === "instagram_media" && fonte.total_posts === 0
                  ? "Conta ainda não sincronizada"
                  : "Nenhum post nesta fonte."}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {postsQ.posts.map((p) => (
                  <PostCard
                    key={postKey(p)}
                    post={p}
                    tipos={tipos}
                    selecionado={selecionados.has(postKey(p))}
                    onToggle={alternarPost}
                  />
                ))}
              </div>
              {postsQ.hasNextPage && (
                <Button
                  type="button"
                  variant="outline"
                  className="self-center"
                  onClick={() => postsQ.fetchNextPage()}
                  disabled={postsQ.isFetchingNextPage}
                >
                  {postsQ.isFetchingNextPage ? "Carregando..." : "Carregar mais"}
                </Button>
              )}
            </>
          )}

          <SelectionBar
            selecionados={selecionados.size}
            max={max}
            reextrair={reextrair}
            onReextrair={setReextrair}
            onSelecionarRecentes={selecionarRecentes}
            onLimpar={() => setSelecionados(new Map())}
            onExtrair={extrair}
            submitting={submeter.isPending}
            bloqueio={bloqueio}
          />
        </>
      )}

      <ExtracoesRecentes jobs={recentesQ.data ?? []} />
    </div>
  );
}
