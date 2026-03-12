import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useWatchlist, useDeleteWatchlist, useAddWatchlistItem, useRemoveWatchlistItem } from "@/hooks/useWatchlist";
import type { WatchlistItem } from "@/types";
import Modal from "@/components/Modal";
import Breadcrumbs from "@/components/Breadcrumbs";
import { ArrowLeft, Plus, Trash2, Eye, Tag, Bell, X } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const EMPTY_ITEM_FORM = { ticker: "", nome: "", alerta_preco_acima: "", alerta_preco_abaixo: "" };

export default function WatchlistDetalhes() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: watchlist, isLoading } = useWatchlist(id);
  const deleteWlMutation = useDeleteWatchlist();
  const addItemMutation = useAddWatchlistItem();
  const removeItemMutation = useRemoveWatchlistItem();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [itemForm, setItemForm] = useState(EMPTY_ITEM_FORM);

  const handleDeleteWl = () => {
    if (!watchlist) return;
    deleteWlMutation.mutate(watchlist.id, { onSuccess: () => navigate("/watchlist") });
  };

  const handleAddItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!watchlist) return;
    const payload: any = {
      id: watchlist.id,
      ticker: itemForm.ticker,
      nome: itemForm.nome || undefined,
    };
    if (itemForm.alerta_preco_acima) payload.alerta_preco_acima = Number(itemForm.alerta_preco_acima);
    if (itemForm.alerta_preco_abaixo) payload.alerta_preco_abaixo = Number(itemForm.alerta_preco_abaixo);
    addItemMutation.mutate(payload, { onSuccess: () => { setAddItemOpen(false); setItemForm(EMPTY_ITEM_FORM); } });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!watchlist) {
    return (
      <div className="space-y-6">
        <button onClick={() => navigate("/watchlist")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">Watchlist nao encontrada</p>
        </div>
      </div>
    );
  }

  const itens: WatchlistItem[] = watchlist.itens || [];

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[
        { label: "Dashboard", href: "/" },
        { label: "Watchlist", href: "/watchlist" },
        { label: watchlist.nome },
      ]} />

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Eye className="w-7 h-7 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{watchlist.nome}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {itens.length} ativo{itens.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setItemForm(EMPTY_ITEM_FORM); setAddItemOpen(true); }}
            className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Adicionar Ativo
          </button>
          <button onClick={() => setDeleteOpen(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-500/30 text-red-500 text-sm hover:bg-red-500/10 transition">
            <Trash2 className="w-3.5 h-3.5" />
            Excluir Watchlist
          </button>
        </div>
      </div>

      {/* Items Table */}
      <div className="rounded-lg border bg-card overflow-auto">
        {itens.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium text-muted-foreground">Ticker</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Nome</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Alertas</th>
                <th className="p-3 w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {itens.map((item) => (
                <tr key={item.id} className="hover:bg-accent/50 transition-colors">
                  <td className="p-3">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <Tag className="w-4 h-4 text-primary" />
                      </div>
                      <span className="font-semibold">{item.ticker}</span>
                    </div>
                  </td>
                  <td className="p-3 text-muted-foreground">{item.nome || "-"}</td>
                  <td className="p-3">
                    {(item.alerta_preco_acima || item.alerta_preco_abaixo) ? (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <Bell className="w-3 h-3" />
                        {item.alerta_preco_abaixo && <span>{"<"} R$ {item.alerta_preco_abaixo}</span>}
                        {item.alerta_preco_acima && <span>{">"} R$ {item.alerta_preco_acima}</span>}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="p-3">
                    <button
                      onClick={() => removeItemMutation.mutate(item.id)}
                      className="p-1.5 rounded-md hover:bg-red-500/10 transition"
                      title="Remover"
                    >
                      <X className="w-4 h-4 text-red-500" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-center py-12 text-muted-foreground">
            <Tag className="w-10 h-10 mx-auto mb-3 opacity-50" />
            <p className="text-sm">Nenhum ativo nesta watchlist</p>
            <p className="text-xs mt-1">Adicione ativos para acompanhar precos e alertas.</p>
          </div>
        )}
      </div>

      {/* Add Item Modal */}
      <Modal open={addItemOpen} onClose={() => setAddItemOpen(false)} title="Adicionar Ativo">
        <form onSubmit={handleAddItem} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Ticker *</label>
            <input type="text" required value={itemForm.ticker} onChange={(e) => setItemForm({ ...itemForm, ticker: e.target.value.toUpperCase() })} className={inputClass} placeholder="PETR4" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Nome</label>
            <input type="text" value={itemForm.nome} onChange={(e) => setItemForm({ ...itemForm, nome: e.target.value })} className={inputClass} placeholder="Petrobras PN" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Alerta Acima</label>
              <input type="number" step="0.01" value={itemForm.alerta_preco_acima} onChange={(e) => setItemForm({ ...itemForm, alerta_preco_acima: e.target.value })} className={inputClass} placeholder="R$" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Alerta Abaixo</label>
              <input type="number" step="0.01" value={itemForm.alerta_preco_abaixo} onChange={(e) => setItemForm({ ...itemForm, alerta_preco_abaixo: e.target.value })} className={inputClass} placeholder="R$" />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setAddItemOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={addItemMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {addItemMutation.isPending ? "Adicionando..." : "Adicionar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Watchlist Confirmation */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Excluir Watchlist">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta watchlist e todos os seus itens?
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            Cancelar
          </button>
          <button onClick={handleDeleteWl} disabled={deleteWlMutation.isPending} className="px-4 py-2 rounded-md bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition disabled:opacity-50">
            {deleteWlMutation.isPending ? "Excluindo..." : "Excluir"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
