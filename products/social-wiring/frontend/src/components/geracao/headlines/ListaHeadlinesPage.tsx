/**
 * Shared body of "Headlines Favoritas" (P8) and "Headline sugeridas" (P9),
 * contract §7.7. `?hid=` highlights + scrolls to that headline (fetched by id
 * when it is not on the current page). Criar roteiro opens the shared
 * RoteiroAvancadoModal prefilled with the headline.
 */
import { useEffect, useRef, useState } from "react";
import { AlertCircle, ExternalLink, Heart, Pencil, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { MetricaPill } from "@/components/geracao/MetricaPill";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { dataPtBr } from "@/components/pesquisa/format";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useExcluirHeadlines, useFavoritarHeadline } from "@/hooks/geracao/useHeadlineMutations";
import {
  HEADLINES_PAGE_SIZE,
  useGerarSugestoesAgora,
  useHeadline,
  useHeadlinesLista,
  type ListaHeadlines,
} from "@/hooks/geracao/useHeadlines";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import { cn } from "@/lib/utils";
import type { Headline } from "@/types/geracao";
import { MODO_ROTULO } from "../labels";
import { EditarHeadlineRoteiroModal } from "./EditarHeadlineRoteiroModal";
import { mensagemErro } from "./lote";

const ROTEIROS = "/media-creation/roteiros";

const TEXTOS: Record<ListaHeadlines, { titulo: string; descricao: string; vazio: string }> = {
  favoritas: {
    titulo: "Headlines Favoritas",
    descricao: "As headlines que você favoritou. Crie roteiros a partir delas.",
    vazio: "Você ainda não tem headlines favoritas. Favorite headlines em Gerar headlines.",
  },
  sugeridas: {
    titulo: "Headline sugeridas",
    descricao: "Headlines geradas para você automaticamente (todo dia) ou pela Biblioteca.",
    vazio: "Ainda não há headlines sugeridas. Elas são geradas todos os dias — ou use Gerar sugestões agora.",
  },
};

export function ListaHeadlinesPage({ lista }: { lista: ListaHeadlines }) {
  const t = TEXTOS[lista];
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 300);
  const [modo, setModo] = useState<"" | "manual" | "automatico">("");
  const [offset, setOffset] = useState(0);
  const dados = useHeadlinesLista(marcaId, lista, { q, modo, offset });
  const items = dados.data?.items ?? [];
  const total = dados.data?.total ?? 0;

  const favoritar = useFavoritarHeadline();
  const excluir = useExcluirHeadlines();
  const gerarAgora = useGerarSugestoesAgora();

  const [sel, setSel] = useState<Set<string>>(new Set());
  const [confirmar, setConfirmar] = useState<string[] | null>(null);
  const [editando, setEditando] = useState<Headline | null>(null);
  const [roteiroDe, setRoteiroDe] = useState<Headline | null>(null);

  useEffect(() => {
    setOffset(0);
    setSel(new Set());
  }, [marcaId, q, modo]);

  // ?hid= : highlight + scroll. Kept in state so consuming nothing from the URL (deep links stay shareable).
  const hid = params.get("hid");
  const naPagina = !!hid && items.some((h) => h.id === hid);
  const avulsa = useHeadline(hid && dados.data && !naPagina ? hid : null);
  const linhaRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (hid && (naPagina || avulsa.data)) linhaRef.current?.scrollIntoView?.({ block: "center", behavior: "smooth" });
  }, [hid, naPagina, avulsa.data]);

  const todos = items.length > 0 && items.every((h) => sel.has(h.id));

  async function alternarFavorita(h: Headline) {
    try {
      await favoritar.mutateAsync({ id: h.id, favoritar: !h.favorita });
      toast.success(h.favorita ? "Removida das favoritas." : "Adicionada às favoritas.");
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível atualizar a favorita."));
    }
  }

  async function confirmarExclusao() {
    const ids = confirmar;
    if (!ids?.length) return;
    try {
      const r = await excluir.mutateAsync(ids);
      toast.success(r.excluidos === 1 ? "1 headline excluída." : `${r.excluidos} headlines excluídas.`);
      setSel(new Set());
      setConfirmar(null);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível excluir."));
    }
  }

  async function sugerirAgora() {
    if (!marcaId) return;
    try {
      await gerarAgora.mutateAsync(marcaId);
      toast.success("Gerando sugestões — elas aparecem aqui quando o lote terminar.");
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível gerar sugestões agora."));
    }
  }

  function linha(h: Headline, destacada: boolean) {
    return (
      <tr
        key={h.id}
        ref={destacada ? (el) => (linhaRef.current = el) : undefined}
        data-testid={`headline-${h.id}`}
        data-destacada={destacada || undefined}
        className={cn("border-b", destacada && "bg-amber-50 ring-2 ring-inset ring-amber-300")}
      >
        <td className="p-2">
          <Checkbox
            aria-label={`Selecionar headline de ${dataPtBr(h.created_at)}`}
            checked={sel.has(h.id)}
            onCheckedChange={() =>
              setSel((s) => {
                const n = new Set(s);
                if (n.has(h.id)) n.delete(h.id);
                else n.add(h.id);
                return n;
              })
            }
          />
        </td>
        <td className="whitespace-nowrap p-2">{dataPtBr(h.created_at)}</td>
        <td className="max-w-md p-2">
          <p className="whitespace-pre-wrap">{h.texto}</p>
          {h.roteiro_id && (
            <Link to={`${ROTEIROS}?open=${encodeURIComponent(h.roteiro_id)}`}>
              <Badge variant="secondary" className="mt-1">
                Roteiro criado
              </Badge>
            </Link>
          )}
        </td>
        {lista === "sugeridas" && (
          <>
            <td className="p-2">{h.modo ? MODO_ROTULO[h.modo] : "—"}</td>
            <td className="p-2">
              <MetricaPill viral={h.viral} />
            </td>
          </>
        )}
        <td className="p-2">
          <div className="flex flex-wrap justify-end gap-1">
            <Button size="sm" variant="outline" onClick={() => setRoteiroDe(h)}>
              <Sparkles className="mr-1 h-4 w-4" /> Criar roteiro
            </Button>
            <Button size="icon" variant="ghost" aria-label="Editar headline" onClick={() => setEditando(h)}>
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-pressed={h.favorita}
              aria-label={h.favorita ? "Desfavoritar headline" : "Favoritar headline"}
              disabled={favoritar.isPending}
              onClick={() => alternarFavorita(h)}
            >
              <Heart className={cn("h-4 w-4", h.favorita && "fill-current text-rose-600")} />
            </Button>
            {lista === "sugeridas" && h.viral?.permalink && (
              <Button size="icon" variant="ghost" asChild>
                <a href={h.viral.permalink} target="_blank" rel="noopener noreferrer" aria-label="Abrir link do viral">
                  <ExternalLink className="h-4 w-4" />
                </a>
              </Button>
            )}
            <Button size="icon" variant="ghost" aria-label="Excluir headline" onClick={() => setConfirmar([h.id])}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </td>
      </tr>
    );
  }

  const colunas = lista === "sugeridas" ? 6 : 4;

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{t.titulo}</h1>
          <p className="text-sm text-muted-foreground">{t.descricao}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          {lista === "sugeridas" && (
            <Button onClick={sugerirAgora} disabled={!marcaId || gerarAgora.isPending}>
              <RefreshCw className="mr-1 h-4 w-4" /> {gerarAgora.isPending ? "Gerando…" : "Gerar sugestões agora"}
            </Button>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Input
            aria-label="Pesquisar headlines"
            placeholder="Pesquisar..."
            className="w-64"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          {lista === "sugeridas" && (
            <select
              aria-label="Modo"
              value={modo}
              onChange={(e) => setModo(e.target.value as typeof modo)}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm shadow-sm"
            >
              <option value="">Todos os modos</option>
              <option value="automatico">Automático</option>
              <option value="manual">Manual</option>
            </select>
          )}
        </div>
        <Button variant="outline" disabled={sel.size === 0} onClick={() => setConfirmar([...sel])}>
          <Trash2 className="mr-1 h-4 w-4" /> Excluir Selecionados ({sel.size})
        </Button>
      </div>

      {dados.showSkeleton && (
        <div className="space-y-2" data-testid="headlines-skeleton">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      )}

      {dados.isError && !dados.data && (
        <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar as headlines.
          </span>
          <Button size="sm" variant="outline" onClick={() => dados.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {!!marcaId && dados.data && items.length === 0 && !avulsa.data && (
        <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
          {q.trim() || modo ? "Nenhuma headline encontrada para este filtro." : t.vazio}
        </p>
      )}

      {(items.length > 0 || avulsa.data) && (
        <div className={dados.isRefreshing ? "opacity-80 transition-opacity" : undefined} aria-busy={dados.isRefreshing}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="w-8 p-2">
                  <Checkbox
                    aria-label="Selecionar todas"
                    checked={todos}
                    onCheckedChange={(v) => setSel(v === true ? new Set(items.map((h) => h.id)) : new Set())}
                  />
                </th>
                <th className="p-2">Data</th>
                <th className="p-2">Headline</th>
                {lista === "sugeridas" && (
                  <>
                    <th className="p-2">Modo</th>
                    <th className="p-2">Métrica</th>
                  </>
                )}
                <th className="p-2" />
              </tr>
            </thead>
            <tbody>
              {avulsa.data && (
                <>
                  {linha(avulsa.data, true)}
                  {items.length > 0 && (
                    <tr>
                      <td colSpan={colunas} className="p-1" />
                    </tr>
                  )}
                </>
              )}
              {items.map((h) => linha(h, h.id === hid))}
            </tbody>
          </table>

          {total > HEADLINES_PAGE_SIZE && (
            <div className="flex items-center justify-between pt-3 text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + HEADLINES_PAGE_SIZE, total)} de {total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - HEADLINES_PAGE_SIZE))}>
                  Anterior
                </Button>
                <Button size="sm" variant="outline" disabled={offset + HEADLINES_PAGE_SIZE >= total} onClick={() => setOffset(offset + HEADLINES_PAGE_SIZE)}>
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <EditarHeadlineRoteiroModal open={!!editando} onOpenChange={(o) => !o && setEditando(null)} headline={editando} />
      <RoteiroAvancadoModal
        open={!!roteiroDe}
        onOpenChange={(o) => !o && setRoteiroDe(null)}
        marcaId={marcaId}
        headlineInicial={roteiroDe ? { id: roteiroDe.id, texto: roteiroDe.texto } : null}
      />

      <AlertDialog open={!!confirmar} onOpenChange={(o) => !o && !excluir.isPending && setConfirmar(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Você realmente deseja deletar as headlines selecionadas?</AlertDialogTitle>
            <AlertDialogDescription>Esta ação não pode ser desfeita.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={excluir.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={excluir.isPending}
              onClick={(e) => {
                e.preventDefault();
                void confirmarExclusao();
              }}
            >
              {excluir.isPending ? "Excluindo…" : "Excluir"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
