import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  useOrcamento, useOrcamentoProgresso, useUpdateOrcamento, useDeleteOrcamento,
  useCreateOrcamentoItem, useUpdateOrcamentoItem, useDeleteOrcamentoItem,
} from "@/hooks/useOrcamentos";
import { useCategorias } from "@/hooks/useCategorias";
import { formatCurrency, getCurrentMonth, getMonthLabel } from "@/lib/utils";
import { METODO_ORCAMENTO_LABELS } from "@/lib/constants";
import type { OrcamentoItem } from "@/types";
import Modal from "@/components/Modal";
import Breadcrumbs from "@/components/Breadcrumbs";
import { ArrowLeft, Pencil, Trash2, Plus } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const EMPTY_FORM = { nome: "", metodo: "zero_based", periodo: "mensal", ativo: true };
const EMPTY_ITEM_FORM = { categoria_id: "", valor_planejado: 0 };

export default function OrcamentoDetalhes() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: orcamento, isLoading } = useOrcamento(id);
  const { data: categorias } = useCategorias();
  const updateMutation = useUpdateOrcamento();
  const deleteMutation = useDeleteOrcamento();
  const createItemMutation = useCreateOrcamentoItem();
  const updateItemMutation = useUpdateOrcamentoItem();
  const deleteItemMutation = useDeleteOrcamentoItem();

  const [periodoMes, setPeriodoMes] = useState(getCurrentMonth());
  const { data: progresso } = useOrcamentoProgresso(id, periodoMes);

  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Item CRUD state
  const [addItemOpen, setAddItemOpen] = useState(false);
  const [itemForm, setItemForm] = useState(EMPTY_ITEM_FORM);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [editItemValue, setEditItemValue] = useState(0);
  const [deleteItemId, setDeleteItemId] = useState<string | null>(null);

  const openEdit = () => {
    if (!orcamento) return;
    setForm({ nome: orcamento.nome, metodo: orcamento.metodo, periodo: orcamento.periodo, ativo: orcamento.ativo });
    setEditOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!orcamento) return;
    updateMutation.mutate({ id: orcamento.id, ...form }, { onSuccess: () => setEditOpen(false) });
  };

  const handleDelete = () => {
    if (!orcamento) return;
    deleteMutation.mutate(orcamento.id, { onSuccess: () => navigate("/orcamentos") });
  };

  const handleAddItem = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    createItemMutation.mutate(
      { orcamentoId: id, categoria_id: itemForm.categoria_id, valor_planejado: Number(itemForm.valor_planejado), periodo_mes: periodoMes },
      { onSuccess: () => { setAddItemOpen(false); setItemForm(EMPTY_ITEM_FORM); } },
    );
  };

  const handleUpdateItem = (itemId: string) => {
    updateItemMutation.mutate(
      { itemId, valor_planejado: editItemValue },
      { onSuccess: () => setEditingItemId(null) },
    );
  };

  const handleDeleteItem = () => {
    if (!deleteItemId) return;
    deleteItemMutation.mutate(deleteItemId, { onSuccess: () => setDeleteItemId(null) });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!orcamento) {
    return (
      <div className="space-y-6">
        <button onClick={() => navigate("/orcamentos")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">Orcamento nao encontrado</p>
        </div>
      </div>
    );
  }

  const itens: OrcamentoItem[] = progresso?.itens || [];
  const totalPlanejado = itens.reduce((acc: number, item: OrcamentoItem) => acc + item.valor_planejado, 0);
  const totalGasto = itens.reduce((acc: number, item: OrcamentoItem) => acc + item.valor_gasto, 0);
  const pctTotal = totalPlanejado > 0 ? (totalGasto / totalPlanejado) * 100 : 0;

  const getBarColor = (pct: number) => {
    if (pct >= 100) return "bg-red-500";
    if (pct >= 80) return "bg-amber-500";
    return "bg-emerald-500";
  };

  // Categories not yet in this budget for this period
  const usedCategoryIds = new Set(itens.map((i) => i.categoria_id));
  const availableCategories = (categorias || []).filter((c) => !usedCategoryIds.has(c.id));

  // Build month selector options
  const meses: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    meses.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[
        { label: "Dashboard", href: "/" },
        { label: "Orcamentos", href: "/orcamentos" },
        { label: orcamento.nome },
      ]} />

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{orcamento.nome}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-medium">
              {METODO_ORCAMENTO_LABELS[orcamento.metodo] || orcamento.metodo}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-medium capitalize">
              {orcamento.periodo}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${orcamento.ativo ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500"}`}>
              {orcamento.ativo ? "Ativo" : "Inativo"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={openEdit} className="flex items-center gap-1.5 px-3 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            <Pencil className="w-3.5 h-3.5" />
            Editar
          </button>
          <button onClick={() => setDeleteOpen(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-500/30 text-red-500 text-sm hover:bg-red-500/10 transition">
            <Trash2 className="w-3.5 h-3.5" />
            Excluir
          </button>
        </div>
      </div>

      {/* Period Selector */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-muted-foreground">Periodo:</label>
        <select
          value={periodoMes}
          onChange={(e) => setPeriodoMes(e.target.value)}
          className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {meses.map((m) => (
            <option key={m} value={m}>{getMonthLabel(m)}</option>
          ))}
        </select>
      </div>

      {/* Overall Progress */}
      <div className="rounded-lg border bg-card p-6 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Progresso Total</h2>
          <div className="text-right">
            <p className="text-xl font-bold">{formatCurrency(totalGasto)}</p>
            <p className="text-sm text-muted-foreground">de {formatCurrency(totalPlanejado)}</p>
          </div>
        </div>
        <div className="space-y-1">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>Utilizado</span>
            <span className="font-medium">{pctTotal.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-muted rounded-full h-4">
            <div
              className={`h-4 rounded-full transition-all ${getBarColor(pctTotal)}`}
              style={{ width: `${Math.min(pctTotal, 100)}%` }}
            />
          </div>
        </div>
        {totalPlanejado > totalGasto && (
          <p className="text-sm text-muted-foreground">
            Restante: {formatCurrency(totalPlanejado - totalGasto)}
          </p>
        )}
        {totalGasto > totalPlanejado && totalPlanejado > 0 && (
          <p className="text-sm text-red-500">
            Excedido em: {formatCurrency(totalGasto - totalPlanejado)}
          </p>
        )}
      </div>

      {/* Category Breakdown */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Categorias</h2>
          <button
            onClick={() => { setItemForm(EMPTY_ITEM_FORM); setAddItemOpen(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            Adicionar Categoria
          </button>
        </div>
        {itens.length > 0 ? (
          <div className="space-y-3">
            {itens.map((item: OrcamentoItem) => {
              const pct = item.valor_planejado > 0 ? (item.valor_gasto / item.valor_planejado) * 100 : 0;
              const isEditing = editingItemId === item.id;
              return (
                <div key={item.id} className="rounded-lg border bg-card p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {item.categoria?.icone && <span className="text-sm">{item.categoria.icone}</span>}
                      <span className="font-medium">{item.categoria?.nome || "Categoria"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {isEditing ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={editItemValue}
                            onChange={(e) => setEditItemValue(Number(e.target.value))}
                            className="w-28 px-2 py-1 rounded border bg-background text-sm"
                          />
                          <button
                            onClick={() => handleUpdateItem(item.id)}
                            disabled={updateItemMutation.isPending}
                            className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50"
                          >
                            Salvar
                          </button>
                          <button onClick={() => setEditingItemId(null)} className="text-xs px-2 py-1 rounded border hover:bg-accent">
                            Cancelar
                          </button>
                        </div>
                      ) : (
                        <>
                          <div className="text-right">
                            <span className="text-sm font-medium">{formatCurrency(item.valor_gasto)}</span>
                            <span className="text-sm text-muted-foreground"> / {formatCurrency(item.valor_planejado)}</span>
                          </div>
                          <button
                            onClick={() => { setEditingItemId(item.id); setEditItemValue(item.valor_planejado); }}
                            className="p-1 rounded hover:bg-accent transition"
                            title="Editar valor"
                          >
                            <Pencil className="w-3 h-3 text-muted-foreground" />
                          </button>
                          <button
                            onClick={() => setDeleteItemId(item.id)}
                            className="p-1 rounded hover:bg-red-500/10 transition"
                            title="Remover"
                          >
                            <Trash2 className="w-3 h-3 text-red-500" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="w-full bg-muted rounded-full h-2.5">
                      <div
                        className={`h-2.5 rounded-full transition-all ${getBarColor(pct)}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{pct.toFixed(0)}%</span>
                      {item.valor_planejado > item.valor_gasto && (
                        <span>Restante: {formatCurrency(item.valor_planejado - item.valor_gasto)}</span>
                      )}
                      {item.valor_gasto > item.valor_planejado && (
                        <span className="text-red-500">Excedido: {formatCurrency(item.valor_gasto - item.valor_planejado)}</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-lg border bg-card text-center py-12 text-muted-foreground">
            <p className="text-sm">Nenhuma categoria configurada para este periodo</p>
            <p className="text-xs mt-1">Clique em "Adicionar Categoria" para definir limites de gastos.</p>
          </div>
        )}
      </div>

      {/* Add Item Modal */}
      <Modal open={addItemOpen} onClose={() => setAddItemOpen(false)} title="Adicionar Categoria ao Orcamento">
        <form onSubmit={handleAddItem} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Categoria *</label>
            <select value={itemForm.categoria_id} onChange={(e) => setItemForm({ ...itemForm, categoria_id: e.target.value })} className={inputClass} required>
              <option value="">Selecionar</option>
              {availableCategories.map((c) => (
                <option key={c.id} value={c.id}>{c.icone ? `${c.icone} ` : ""}{c.nome}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Valor Planejado *</label>
            <input type="number" required step="0.01" min="0.01" value={itemForm.valor_planejado || ""} onChange={(e) => setItemForm({ ...itemForm, valor_planejado: Number(e.target.value) })} className={inputClass} />
          </div>
          <p className="text-xs text-muted-foreground">Periodo: {getMonthLabel(periodoMes)}</p>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setAddItemOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={createItemMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {createItemMutation.isPending ? "Adicionando..." : "Adicionar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Editar Orcamento">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Metodo</label>
            <select value={form.metodo} onChange={(e) => setForm({ ...form, metodo: e.target.value })} className={inputClass}>
              {Object.entries(METODO_ORCAMENTO_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Periodo</label>
            <select value={form.periodo} onChange={(e) => setForm({ ...form, periodo: e.target.value })} className={inputClass}>
              <option value="mensal">Mensal</option>
              <option value="quinzenal">Quinzenal</option>
              <option value="semanal">Semanal</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="orcamento-ativo-edit" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} className="rounded" />
            <label htmlFor="orcamento-ativo-edit" className="text-sm font-medium">Ativo</label>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setEditOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={updateMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {updateMutation.isPending ? "Salvando..." : "Salvar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Orcamento Confirmation */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Excluir Orcamento">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir este orcamento?
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            Cancelar
          </button>
          <button onClick={handleDelete} disabled={deleteMutation.isPending} className="px-4 py-2 rounded-md bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition disabled:opacity-50">
            {deleteMutation.isPending ? "Excluindo..." : "Excluir"}
          </button>
        </div>
      </Modal>

      {/* Delete Item Confirmation */}
      <Modal open={deleteItemId !== null} onClose={() => setDeleteItemId(null)} title="Remover Categoria">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja remover esta categoria do orcamento?
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteItemId(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            Cancelar
          </button>
          <button onClick={handleDeleteItem} disabled={deleteItemMutation.isPending} className="px-4 py-2 rounded-md bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition disabled:opacity-50">
            {deleteItemMutation.isPending ? "Removendo..." : "Remover"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
