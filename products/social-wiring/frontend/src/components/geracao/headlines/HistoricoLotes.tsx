/**
 * History of headline batches (`#myHeadlines`): search, "Excluir Selecionados (N)",
 * ☐ · Data · Tipo · Status · 👁 (enabled on completo/falha) · 🗑 (contract §7.7).
 * Status is the real polled status (the hook polls while any row is moving).
 */
import { useEffect, useState } from "react";
import { AlertCircle, Eye, Trash2 } from "lucide-react";
import { toast } from "sonner";

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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { HEADLINES_PAGE_SIZE, useExcluirLotes, useLotes } from "@/hooks/geracao/useHeadlines";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import type { HeadlineLote } from "@/types/geracao";
import { ORIGEM_ROTULO } from "../labels";
import { StatusBadge } from "../StatusBadge";
import { mensagemErro } from "./lote";

interface Props {
  marcaId: string | null;
  onVer: (lote: HeadlineLote) => void;
}

export function HistoricoLotes({ marcaId, onVer }: Props) {
  const [busca, setBusca] = useState("");
  const q = useDebouncedValue(busca, 300);
  const [offset, setOffset] = useState(0);
  const lista = useLotes(marcaId, q, offset);
  const items = lista.data?.items ?? [];
  const total = lista.data?.total ?? 0;
  const excluir = useExcluirLotes();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [confirmar, setConfirmar] = useState<string[] | null>(null);

  useEffect(() => {
    setOffset(0);
    setSel(new Set());
  }, [marcaId, q]);

  const todos = items.length > 0 && items.every((l) => sel.has(l.id));

  async function confirmarExclusao() {
    const ids = confirmar;
    if (!ids?.length) return;
    try {
      const r = await excluir.mutateAsync(ids);
      toast.success(r.excluidos === 1 ? "1 lote excluído." : `${r.excluidos} lotes excluídos.`);
      setSel(new Set());
      setConfirmar(null);
    } catch (e) {
      toast.error(mensagemErro(e, "Não foi possível excluir."));
    }
  }

  return (
    <section id="myHeadlines" className="space-y-3">
      <h2 className="text-lg font-semibold">Minhas headlines</h2>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          aria-label="Pesquisar lotes"
          placeholder="Pesquisar..."
          className="max-w-xs"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <Button variant="outline" disabled={sel.size === 0} onClick={() => setConfirmar([...sel])}>
          <Trash2 className="mr-1 h-4 w-4" /> Excluir Selecionados ({sel.size})
        </Button>
      </div>

      {lista.showSkeleton && (
        <div className="space-y-2" data-testid="lotes-skeleton">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}

      {lista.isError && !lista.data && (
        <div role="alert" className="flex items-center justify-between rounded-md border p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-destructive" /> Não foi possível carregar o histórico.
          </span>
          <Button size="sm" variant="outline" onClick={() => lista.refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {!!marcaId && lista.data && items.length === 0 && (
        <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
          {q.trim() ? "Nenhum lote encontrado para esta busca." : "Você ainda não gerou headlines."}
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
                    checked={todos}
                    onCheckedChange={(v) => setSel(v === true ? new Set(items.map((l) => l.id)) : new Set())}
                  />
                </th>
                <th className="p-2">Data</th>
                <th className="p-2">Tipo</th>
                <th className="p-2">Status</th>
                <th className="w-24 p-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((l) => {
                const terminal = l.status === "completo" || l.status === "falha";
                return (
                  <tr key={l.id} className="border-b" data-testid={`lote-${l.id}`}>
                    <td className="p-2">
                      <Checkbox
                        aria-label={`Selecionar lote de ${dataPtBr(l.created_at)}`}
                        checked={sel.has(l.id)}
                        onCheckedChange={() =>
                          setSel((s) => {
                            const n = new Set(s);
                            if (n.has(l.id)) n.delete(l.id);
                            else n.add(l.id);
                            return n;
                          })
                        }
                      />
                    </td>
                    <td className="whitespace-nowrap p-2">{dataPtBr(l.created_at)}</td>
                    <td className="max-w-xs p-2">
                      <span className="font-medium">{ORIGEM_ROTULO[l.origem]}</span>
                      {l.resumo && <span className="block truncate text-xs text-muted-foreground" title={l.resumo}>{l.resumo}</span>}
                    </td>
                    <td className="p-2">
                      <StatusBadge status={l.status} />
                    </td>
                    <td className="p-2">
                      <div className="flex justify-end gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Ver lote de ${dataPtBr(l.created_at)}`}
                          disabled={!terminal}
                          onClick={() => onVer(l)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Excluir lote de ${dataPtBr(l.created_at)}`}
                          onClick={() => setConfirmar([l.id])}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
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

      <AlertDialog open={!!confirmar} onOpenChange={(o) => !o && !excluir.isPending && setConfirmar(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Você realmente deseja deletar estas Headlines?</AlertDialogTitle>
            <AlertDialogDescription>
              Os lotes selecionados serão excluídos com todas as headlines geradas — inclusive as favoritas. Esta ação não pode ser desfeita.
            </AlertDialogDescription>
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
    </section>
  );
}
