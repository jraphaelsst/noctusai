import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useWatchlists, useCreateWatchlist, useDeleteWatchlist, useAddWatchlistItem, useRemoveWatchlistItem } from "@/hooks/useWatchlist";
import type { Watchlist as WatchlistType, WatchlistItem } from "@/types";
import Modal from "@/components/Modal";
import { Plus, Eye, Tag, Bell, Trash2, X } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function WatchlistItemRow({ item, onRemove }: { item: WatchlistItem; onRemove: () => void }) {
  return (
    <div className="flex items-center justify-between py-2 border-b last:border-b-0">
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
          <Tag className="w-4 h-4 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">{item.ticker}</p>
          {item.nome && <p className="text-xs text-muted-foreground truncate">{item.nome}</p>}
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0 ml-2">
        {(item.alerta_preco_acima || item.alerta_preco_abaixo) && (
          <div className="flex items-center gap-1">
            <Bell className="w-3 h-3" />
            {item.alerta_preco_abaixo && <span>{"<"}{item.alerta_preco_abaixo}</span>}
            {item.alerta_preco_acima && <span>{">"}{item.alerta_preco_acima}</span>}
          </div>
        )}
        <button onClick={onRemove} className="p-1 rounded hover:bg-red-500/10 transition" title="Remover">
          <X className="w-3.5 h-3.5 text-red-500" />
        </button>
      </div>
    </div>
  );
}

function WatchlistCard({ watchlist, onDelete, onAddItem, onRemoveItem, onClick }: {
  watchlist: WatchlistType;
  onDelete: () => void;
  onAddItem: () => void;
  onRemoveItem: (itemId: string) => void;
  onClick: () => void;
}) {
  const itens = watchlist.itens || [];

  return (
    <div className="rounded-lg border bg-card p-5 space-y-3 cursor-pointer hover:shadow-md transition-shadow" onClick={onClick}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Eye className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold">{watchlist.nome}</h3>
            <p className="text-xs text-muted-foreground">
              {itens.length} ativo{itens.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={onAddItem}
            className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 font-medium transition"
          >
            <Plus className="w-3 h-3" />
            Adicionar
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir watchlist">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        </div>
      </div>

      {itens.length > 0 ? (
        <div className="pt-1">
          {itens.map((item) => (
            <WatchlistItemRow key={item.id} item={item} onRemove={() => onRemoveItem(item.id)} />
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-3">Nenhum ativo adicionado</p>
      )}
    </div>
  );
}

const EMPTY_WL_FORM = { nome: "" };
const EMPTY_ITEM_FORM = { ticker: "", nome: "", alerta_preco_acima: "", alerta_preco_abaixo: "" };

export default function Watchlist() {
  const navigate = useNavigate();
  const { data: watchlists, isLoading } = useWatchlists();
  const createWlMutation = useCreateWatchlist();
  const deleteWlMutation = useDeleteWatchlist();
  const addItemMutation = useAddWatchlistItem();
  const removeItemMutation = useRemoveWatchlistItem();

  const [createWlOpen, setCreateWlOpen] = useState(false);
  const [wlForm, setWlForm] = useState(EMPTY_WL_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [addItemWlId, setAddItemWlId] = useState<string | null>(null);
  const [itemForm, setItemForm] = useState(EMPTY_ITEM_FORM);

  const handleCreateWl = (e: React.FormEvent) => {
    e.preventDefault();
    createWlMutation.mutate({ nome: wlForm.nome }, { onSuccess: () => { setCreateWlOpen(false); setWlForm(EMPTY_WL_FORM); } });
  };

  const handleDeleteWl = () => {
    if (!deleteConfirmId) return;
    deleteWlMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  const handleAddItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!addItemWlId) return;
    const payload: any = {
      id: addItemWlId,
      ticker: itemForm.ticker,
      nome: itemForm.nome || undefined,
    };
    if (itemForm.alerta_preco_acima) payload.alerta_preco_acima = Number(itemForm.alerta_preco_acima);
    if (itemForm.alerta_preco_abaixo) payload.alerta_preco_abaixo = Number(itemForm.alerta_preco_abaixo);
    addItemMutation.mutate(payload, { onSuccess: () => { setAddItemWlId(null); setItemForm(EMPTY_ITEM_FORM); } });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const lista = watchlists || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Watchlists</h1>
        <button
          onClick={() => { setWlForm(EMPTY_WL_FORM); setCreateWlOpen(true); }}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Watchlist
        </button>
      </div>

      {lista.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {lista.map((wl) => (
            <WatchlistCard
              key={wl.id}
              watchlist={wl}
              onDelete={() => setDeleteConfirmId(wl.id)}
              onAddItem={() => { setAddItemWlId(wl.id); setItemForm(EMPTY_ITEM_FORM); }}
              onRemoveItem={(itemId) => removeItemMutation.mutate(itemId)}
              onClick={() => navigate(`/watchlist/${wl.id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Eye className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma watchlist cadastrada</p>
          <p className="text-sm">Crie uma watchlist para acompanhar ativos do seu interesse.</p>
        </div>
      )}

      {/* Create Watchlist Modal */}
      <Modal open={createWlOpen} onClose={() => setCreateWlOpen(false)} title="Nova Watchlist">
        <form onSubmit={handleCreateWl} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={wlForm.nome} onChange={(e) => setWlForm({ nome: e.target.value })} className={inputClass} placeholder="Acoes Brasileiras" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setCreateWlOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={createWlMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {createWlMutation.isPending ? "Criando..." : "Criar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Add Item Modal */}
      <Modal open={addItemWlId !== null} onClose={() => setAddItemWlId(null)} title="Adicionar Ativo">
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
            <button type="button" onClick={() => setAddItemWlId(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={addItemMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {addItemMutation.isPending ? "Adicionando..." : "Adicionar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Watchlist Confirmation */}
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Watchlist">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta watchlist e todos os seus itens?
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteConfirmId(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
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
