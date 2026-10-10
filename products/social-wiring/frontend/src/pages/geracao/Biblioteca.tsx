/**
 * Biblioteca de virais (P3, `/media-creation/biblioteca`) — contract §7.3.
 * Filters live in the URL (`?viral=` opens the modal, `?perfil=` filters by
 * profile with no auto-filter banner). Loading: `showSkeleton` /
 * `isRefreshing` off `data`, never `.isLoading` (lying-loading-state.md).
 *
 * Empty states are honest: the monitoring (ingestion) ships OFF behind a kill
 * switch, so "nothing here yet" says why instead of pretending.
 */
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { FiltrosVirais } from "@/components/geracao/biblioteca/FiltrosVirais";
import { ViralCard } from "@/components/geracao/biblioteca/ViralCard";
import { ViralModal } from "@/components/geracao/biblioteca/ViralModal";
import {
  contarFiltrosAtivos,
  filtrosDeParams,
  filtrosParaParams,
  type FiltrosViral,
} from "@/components/geracao/biblioteca/filtros";
import {
  useCriarReferencias,
  usePerfisMonitorados,
  useViraisBiblioteca,
  VIRAIS_POR_PAGINA,
} from "@/hooks/geracao/useBiblioteca";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { ViralCard as ViralCardT } from "@/types/geracao";

const VIDEOS_MAX = 50;

export default function Biblioteca() {
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [params, setParams] = useSearchParams();
  const filtros = useMemo(() => filtrosDeParams(params), [params]);
  const viralAberto = params.get("viral");
  const [painel, setPainel] = useState(false);
  const [selecionados, setSelecionados] = useState<Map<string, ViralCardT>>(new Map());

  const viraisQ = useViraisBiblioteca(marcaId, filtros);
  const perfisQ = usePerfisMonitorados();
  const criarRef = useCriarReferencias();

  function aplicar(f: FiltrosViral) {
    const next = filtrosParaParams(f);
    const viral = params.get("viral");
    if (viral) next.set("viral", viral);
    setParams(next);
  }

  function abrirViral(v: ViralCardT) {
    const next = new URLSearchParams(params);
    next.set("viral", v.id);
    setParams(next);
  }
  function fecharViral() {
    const next = new URLSearchParams(params);
    next.delete("viral");
    setParams(next, { replace: true });
  }

  function selecionar(v: ViralCardT, marcado: boolean) {
    setSelecionados((cur) => {
      const n = new Map(cur);
      if (marcado) {
        if (n.size >= VIDEOS_MAX) {
          toast.info(`Selecione no máximo ${VIDEOS_MAX} vídeos por vez.`);
          return cur;
        }
        n.set(v.id, v);
      } else n.delete(v.id);
      return n;
    });
  }

  async function adicionar() {
    if (!marcaId || selecionados.size === 0) return;
    try {
      const r = await criarRef.mutateAsync({
        marca_id: marcaId,
        modo: "video",
        viral_ids: [...selecionados.keys()],
      });
      toast.success(
        r.ja_existentes > 0
          ? `${r.criadas} adicionado(s); ${r.ja_existentes} já estavam na sua biblioteca.`
          : `${r.criadas} vídeo(s) adicionado(s) à Minha Biblioteca.`,
      );
      setSelecionados(new Map());
    } catch (e) {
      toast.error(
        e instanceof Error && e.message ? e.message : "Não foi possível adicionar à biblioteca.",
      );
    }
  }

  const data = viraisQ.data;
  const total = data?.total ?? 0;
  const paginas = Math.max(1, Math.ceil(total / VIRAIS_POR_PAGINA));
  const ativos = contarFiltrosAtivos(filtros);
  const perfis = perfisQ.data ?? [];
  const semPerfis = !perfisQ.showSkeleton && !perfisQ.isError && perfis.length === 0;
  const monitoramentoOff =
    data?.ingestao_ativa === false || perfis.some((p) => p.ingestao_ativa === false);
  const filtroAuto = !!data?.filtro_automatico && !filtros.perfilId;

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Biblioteca de virais</h1>
          <p className="text-sm text-muted-foreground">Biblioteca de virais disponíveis</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button
            variant="outline"
            onClick={() =>
              aplicar({
                ...filtros,
                ordem: filtros.ordem === "mais_vistos" ? "mais_recentes" : "mais_vistos",
                page: 1,
              })
            }
          >
            {filtros.ordem === "mais_vistos" ? "Mais vistos" : "Mais recentes"}
          </Button>
          <Button variant="outline" onClick={() => setPainel((v) => !v)} aria-expanded={painel}>
            Filtros{ativos > 0 ? ` (${ativos})` : ""}
          </Button>
        </div>
      </header>

      {filtroAuto && (
        <div role="status" className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">
          <p className="font-medium">Filtros aplicados automaticamente</p>
          <p className="text-muted-foreground">
            Estamos mostrando virais dos nichos e profissões desta marca. Para ver todos os virais da
            biblioteca, clique em "Ver todos os virais".
          </p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={!filtros.verTodos ? "default" : "outline"}
          onClick={() =>
            aplicar({ ...filtros, verTodos: false, nichos: [], profissoes: [], page: 1 })
          }
        >
          Meus nichos e profissões
        </Button>
        <Button
          size="sm"
          variant={filtros.verTodos ? "default" : "outline"}
          onClick={() => aplicar({ ...filtros, verTodos: true, page: 1 })}
        >
          Ver todos os virais
        </Button>
        {filtros.perfilId && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => aplicar({ ...filtros, perfilId: "", page: 1 })}
          >
            Limpar filtro de perfil
          </Button>
        )}
      </div>

      {selecionados.size > 0 && (
        <div
          role="region"
          aria-label="Seleção"
          className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/50 p-3 text-sm"
        >
          <span>{selecionados.size} vídeo(s) selecionado(s)</span>
          <Button size="sm" variant="ghost" onClick={() => setSelecionados(new Map())}>
            Limpar seleção
          </Button>
          <Button size="sm" onClick={adicionar} disabled={criarRef.isPending}>
            {criarRef.isPending ? "Adicionando..." : "Adicionar à Minha Biblioteca"}
          </Button>
        </div>
      )}

      <div className={cn("grid gap-6", painel && "lg:grid-cols-[320px_1fr]")}>
        {painel && <FiltrosVirais filtros={filtros} onAplicar={aplicar} />}

        <section aria-label="Virais Encontrados" className="flex flex-col gap-4">
          <h2 className="text-lg font-semibold">
            Virais Encontrados{data ? ` (${total})` : ""}
          </h2>

          {!marcaId && !marcasQ.isPending ? (
            <p className="text-sm text-muted-foreground">
              Cadastre uma marca para usar a biblioteca.
            </p>
          ) : viraisQ.showSkeleton || marcasQ.isPending ? (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6">
              {Array.from({ length: 12 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[9/16] w-full" />
              ))}
            </div>
          ) : viraisQ.isError ? (
            <div className="text-sm text-destructive">
              Não foi possível carregar os virais.{" "}
              <Button variant="link" className="h-auto p-0" onClick={() => viraisQ.refetch()}>
                Tentar novamente
              </Button>
            </div>
          ) : total === 0 ? (
            <EstadoVazio semPerfis={semPerfis} monitoramentoOff={monitoramentoOff} filtrado={ativos > 0 || filtroAuto} />
          ) : (
            <>
              <div
                className={cn(
                  "grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6",
                  viraisQ.isRefreshing && "opacity-70",
                )}
              >
                {data?.items.map((v) => (
                  <ViralCard
                    key={v.id}
                    viral={v}
                    selecionado={selecionados.has(v.id)}
                    onSelecionar={selecionar}
                    onAbrir={abrirViral}
                  />
                ))}
              </div>
              {paginas > 1 && (
                <nav aria-label="Paginação" className="flex items-center justify-center gap-3 text-sm">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={filtros.page <= 1}
                    onClick={() => aplicar({ ...filtros, page: filtros.page - 1 })}
                  >
                    Anterior
                  </Button>
                  <span>
                    Página {filtros.page} de {paginas}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={filtros.page >= paginas}
                    onClick={() => aplicar({ ...filtros, page: filtros.page + 1 })}
                  >
                    Próxima
                  </Button>
                </nav>
              )}
            </>
          )}
        </section>
      </div>

      <ViralModal
        open={!!viralAberto}
        onOpenChange={(o) => !o && fecharViral()}
        marcaId={marcaId}
        viralId={viralAberto}
      />
    </div>
  );
}

function EstadoVazio({
  semPerfis,
  monitoramentoOff,
  filtrado,
}: {
  semPerfis: boolean;
  monitoramentoOff: boolean;
  filtrado: boolean;
}) {
  return (
    <div className="rounded-md border border-dashed p-8 text-center text-sm">
      <p className="font-medium">Nenhum viral encontrado</p>
      {semPerfis ? (
        <p className="mt-1 text-muted-foreground">
          Sua biblioteca ainda está vazia — cadastre perfis em{" "}
          <Link className="text-primary hover:underline" to="/media-creation/minha-biblioteca">
            Minha Biblioteca › Solicitar Perfil
          </Link>
          .
        </p>
      ) : monitoramentoOff ? (
        <p className="mt-1 text-muted-foreground">
          Monitoramento ainda não ativado: os perfis só são sincronizados depois que a ingestão da
          biblioteca for ligada.
        </p>
      ) : filtrado ? (
        <p className="mt-1 text-muted-foreground">
          Nenhum viral corresponde aos filtros atuais. Tente "Ver todos os virais" ou limpe os
          filtros.
        </p>
      ) : (
        <p className="mt-1 text-muted-foreground">
          Ainda não há virais detectados nos perfis monitorados.
        </p>
      )}
    </div>
  );
}
