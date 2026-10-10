/**
 * Esteira de Reels (`/media-creation/esteira`, route key `media-creation-esteira`) —
 * esteira-contract.md §6.1 (FE-1).
 *
 * Filters live in the URL: `?marca=<id|todas>` (first visit with no param falls back to
 * the remembered `sw.pesquisa.marca`, else Todas), `?busca=` (debounced), `?membro=`,
 * `?arquivados=1`. `?post=<id>` is the card deep link: this page only sets/clears it;
 * `PostCardDialog` (FE-2) is mounted here, driven by `?post=`; closing removes the param.
 */
import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { EquipeDialog } from "@/components/geracao/esteira/EquipeDialog";
import { EsteiraBoard } from "@/components/geracao/esteira/EsteiraBoard";
import { PostCardDialog } from "@/components/geracao/esteira/PostCardDialog";
import { NovoPostDialog } from "@/components/geracao/esteira/NovoPostDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useEquipe, type EsteiraFiltros } from "@/hooks/geracao/useEsteira";
import { useMarcas } from "@/hooks/useMarcas";
import { lerMarcaSalva, salvarMarca } from "@/hooks/useMarcaPesquisa";

const TODAS = "todas";
const SELECT = "h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm";

export interface EsteiraPageProps {
  /** Override (FE-2 / FE-Z): open the post dialog. Default sets `?post=<id>`. */
  onOpenPost?: (id: string) => void;
}

export default function Esteira({ onOpenPost }: EsteiraPageProps = {}) {
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const equipeQ = useEquipe();

  const marcaParam = params.get("marca");
  const salva = marcaParam === null ? lerMarcaSalva() : null;
  // A remembered marca must be validated against the loaded list before it filters anything.
  const aguardandoMarcas = marcaParam === null && salva !== null && marcasQ.isPending && !marcasQ.data;
  const marcaId =
    marcaParam !== null
      ? marcaParam === TODAS
        ? undefined
        : marcaParam
      : marcas.find((m) => m.id === salva)?.id;

  const membroId = params.get("membro") || undefined;
  const arquivados = params.get("arquivados") === "1";
  const buscaUrl = params.get("busca") ?? "";

  const [busca, setBusca] = useState(buscaUrl);
  const [equipeAberta, setEquipeAberta] = useState(false);
  const [novoAberto, setNovoAberto] = useState(false);

  useEffect(() => {
    if (busca === buscaUrl) return;
    const t = setTimeout(() => setParam("busca", busca || null), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  function setParam(chave: string, valor: string | null) {
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        if (valor === null || valor === "") n.delete(chave);
        else n.set(chave, valor);
        return n;
      },
      { replace: true },
    );
  }

  function escolherMarca(valor: string) {
    if (valor !== TODAS) salvarMarca(valor);
    setParam("marca", valor);
  }

  function abrirPost(id: string) {
    if (onOpenPost) onOpenPost(id);
    else setParam("post", id);
  }

  const postAberto = params.get("post");

  const filtros: EsteiraFiltros = {
    marca_id: marcaId,
    busca: buscaUrl || undefined,
    membro_id: membroId,
    incluir_arquivados: arquivados || undefined,
  };

  return (
    <div className="min-w-0 space-y-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Esteira</h1>
          <p className="text-sm text-muted-foreground">Do roteiro ao post: acompanhe cada reel por etapa.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2" data-testid="esteira-toolbar">
          <select
            aria-label="Marca"
            className={SELECT}
            value={marcaId ?? TODAS}
            onChange={(e) => escolherMarca(e.target.value)}
          >
            <option value={TODAS}>Todas as marcas</option>
            {marcas.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <Input
            aria-label="Buscar"
            className="h-9 w-44"
            placeholder="Buscar post"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          <select
            aria-label="Membro"
            className={SELECT}
            value={membroId ?? ""}
            onChange={(e) => setParam("membro", e.target.value || null)}
          >
            <option value="">Todos os membros</option>
            {(equipeQ.data ?? []).map((m) => (
              <option key={m.id} value={m.id}>
                {m.nome}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-sm">
            <input
              type="checkbox"
              checked={arquivados}
              onChange={(e) => setParam("arquivados", e.target.checked ? "1" : null)}
            />
            Mostrar arquivados
          </label>
          <Button size="sm" variant="outline" onClick={() => setEquipeAberta(true)}>
            <Users className="mr-1 h-4 w-4" />
            Equipe
          </Button>
          <Button size="sm" disabled={marcas.length === 0} onClick={() => setNovoAberto(true)}>
            Novo post
          </Button>
        </div>
      </header>

      {aguardandoMarcas ? (
        <Skeleton className="h-64 w-full" data-testid="esteira-skeleton" />
      ) : (
        <EsteiraBoard filtros={filtros} onOpenPost={abrirPost} />
      )}

      {postAberto && <PostCardDialog postId={postAberto} onClose={() => setParam("post", null)} />}
      <EquipeDialog open={equipeAberta} onClose={() => setEquipeAberta(false)} />
      <NovoPostDialog
        open={novoAberto}
        marcas={marcas}
        marcaIdInicial={marcaId}
        onClose={() => setNovoAberto(false)}
      />
    </div>
  );
}
