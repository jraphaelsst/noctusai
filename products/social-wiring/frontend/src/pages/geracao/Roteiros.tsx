/**
 * Meus roteiros (P10, `/media-creation/roteiros`, `?open=<id>`) — contract §7.8.
 * Table ☐ · Data · Nome · H. Origem · Status · 👁 · 🗑, search, "Excluir
 * Selecionados", "Criar roteiro" (RoteiroAvancadoModal with an empty headline).
 * Real status from the 3 s poll (hook); loading = two signals off `data`.
 */
import { useEffect, useState } from "react";
import { AlertCircle, Eye, Plus, Trash2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { EditarRoteiroModal } from "@/components/geracao/roteiro/EditarRoteiroModal";
import { RoteiroAvancadoModal } from "@/components/geracao/roteiro/RoteiroAvancadoModal";
import { StatusBadge } from "@/components/geracao/StatusBadge";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ROTEIROS_PAGE_SIZE, useExcluirRoteiros, useRoteiros } from "@/hooks/geracao/useRoteiros";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";

const FAVORITAS = "/media-creation/headlines/favoritas";

function dataCurta(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
}

export default function Roteiros() {
  const [params, setParams] = useSearchParams();
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 300);
  const [offset, setOffset] = useState(0);
  const lista = useRoteiros(marcaId, q, offset);
  const items = lista.data?.items ?? [];
  const total = lista.data?.total ?? 0;

  const excluir = useExcluirRoteiros();
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [confirmarExcluir, setConfirmarExcluir] = useState<string[] | null>(null);
  const [criarAberto, setCriarAberto] = useState(false);
  const [abertoId, setAbertoId] = useState<string | null>(null);

  // Marca / search change: back to page 1, clear the selection.
  useEffect(() => {
    setOffset(0);
    setSelecionados(new Set());
  }, [marcaId, q]);

  // `?open=<id>` auto-opens that roteiro once, then is consumed.
  const openParam = params.get("open");
  useEffect(() => {
    if (!openParam) return;
    setAbertoId(openParam);
    const next = new URLSearchParams(params);
    next.delete("open");
    setParams(next, { replace: true });
  }, [openParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const todosMarcados = items.length > 0 && items.every((r) => selecionados.has(r.id));

  function alternar(id: string) {
    setSelecionados((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function confirmar() {
    const ids = confirmarExcluir;
    if (!ids?.length) return;
    try {
      const r = await excluir.mutateAsync(ids);
      toast.success(r.excluidos === 1 ? "1 roteiro excluído." : `${r.excluidos} roteiros excluídos.`);
      setSelecionados(new Set());
      setConfirmarExcluir(null);
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message.replace(/^\[\d+\]\s*/, "") : "Não foi possível excluir.");
    }
  }

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Meus roteiros</h1>
          <p className="text-sm text-muted-foreground">
            Edite suas headlines favoritas ou crie roteiros a partir delas.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button onClick={() => setCriarAberto(true)} disabled={!marcaId}>
            <Plus className="mr-1 h-4 w-4" /> Criar roteiro
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          aria-label="Pesquisar roteiros"
          placeholder="Pesquisar..."
          className="max-w-xs"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Button
          variant="outline"
          disabled={selecionados.size === 0}
          onClick={() => setConfirmarExcluir([...selecionados])}
        >
          <Trash2 className="mr-1 h-4 w-4" /> Excluir Selecionados
        </Button>
      </div>

      {lista.showSkeleton && (
        <div className="space-y-2" data-testid="roteiros-skeleton">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {lista.isError && !lista.data && (
        <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar seus roteiros.
          </span>
          <Button size="sm" variant="outline" onClick={() => lista.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {!!marcaId && lista.data && items.length === 0 && (
        <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
          {q.trim()
            ? "Nenhum roteiro encontrado para esta busca."
            : "Você ainda não tem roteiros. Clique em Criar roteiro para começar."}
        </p>
      )}

      {items.length > 0 && (
        <div className={lista.isRefreshing ? "opacity-80 transition-opacity" : undefined} aria-busy={lista.isRefreshing}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="w-8 p-2">
                  <Checkbox
                    aria-label="Selecionar todos"
                    checked={todosMarcados}
                    onCheckedChange={(v) => setSelecionados(v === true ? new Set(items.map((r) => r.id)) : new Set())}
                  />
                </th>
                <th className="p-2">Data</th>
                <th className="p-2">Nome</th>
                <th className="p-2">H. Origem</th>
                <th className="p-2">Status</th>
                <th className="w-24 p-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-b" data-testid={`roteiro-${r.id}`}>
                  <td className="p-2">
                    <Checkbox
                      aria-label={`Selecionar ${r.nome}`}
                      checked={selecionados.has(r.id)}
                      onCheckedChange={() => alternar(r.id)}
                    />
                  </td>
                  <td className="whitespace-nowrap p-2">{dataCurta(r.created_at)}</td>
                  <td className="max-w-xs truncate p-2 font-medium" title={r.nome}>
                    {r.nome}
                  </td>
                  <td className="max-w-xs truncate p-2" title={r.headline_texto}>
                    {r.headline_id ? (
                      <Link className="underline" to={`${FAVORITAS}?hid=${encodeURIComponent(r.headline_id)}`}>
                        {r.headline_texto}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">{r.headline_texto}</span>
                    )}
                  </td>
                  <td className="p-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="p-2">
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" aria-label={`Ver ${r.nome}`} onClick={() => setAbertoId(r.id)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        aria-label={`Excluir ${r.nome}`}
                        onClick={() => setConfirmarExcluir([r.id])}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {total > ROTEIROS_PAGE_SIZE && (
            <div className="flex items-center justify-between pt-3 text-sm text-muted-foreground">
              <span>
                {offset + 1}–{Math.min(offset + ROTEIROS_PAGE_SIZE, total)} de {total}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - ROTEIROS_PAGE_SIZE))}
                >
                  Anterior
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={offset + ROTEIROS_PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + ROTEIROS_PAGE_SIZE)}
                >
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <RoteiroAvancadoModal open={criarAberto} onOpenChange={setCriarAberto} marcaId={marcaId} headlineInicial={null} />
      <EditarRoteiroModal
        open={!!abertoId}
        onOpenChange={(o) => !o && setAbertoId(null)}
        roteiroId={abertoId}
        onReprocessado={(novo) => setAbertoId(novo.id)}
      />

      <AlertDialog open={!!confirmarExcluir} onOpenChange={(o) => !o && !excluir.isPending && setConfirmarExcluir(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Excluir roteiros</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmarExcluir?.length === 1
                ? "Excluir este roteiro? Esta ação não pode ser desfeita."
                : `Excluir ${confirmarExcluir?.length ?? 0} roteiros? Esta ação não pode ser desfeita.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={excluir.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              disabled={excluir.isPending}
              onClick={(e) => {
                e.preventDefault();
                void confirmar();
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
