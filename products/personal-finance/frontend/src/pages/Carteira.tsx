import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCarteiras, useCreateCarteira, useUpdateCarteira, useDeleteCarteira } from "@/hooks/useCarteira";
import { formatCurrency, formatPercent } from "@/lib/utils";
import type { Carteira } from "@/types";
import Modal from "@/components/Modal";
import { Plus, TrendingUp, TrendingDown, Briefcase, ChevronRight, Pencil, Trash2 } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function CarteiraCard({ carteira, onClick, onEdit, onDelete }: { carteira: Carteira; onClick: () => void; onEdit: () => void; onDelete: () => void }) {
  const valorTotal = carteira.valor_total || 0;
  const ganhoPerdaTotal = carteira.ganho_perda_total || 0;
  const isPositive = ganhoPerdaTotal >= 0;

  return (
    <div className="w-full rounded-lg border bg-card p-5 space-y-3 text-left transition-shadow hover:shadow-md hover:border-primary/30">
      <div className="flex items-center justify-between">
        <button onClick={onClick} className="flex items-center gap-3 min-w-0 flex-1">
          <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <Briefcase className="w-5 h-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="font-semibold truncate">{carteira.nome}</p>
            <p className="text-xs text-muted-foreground">
              {carteira.tipo}
              {carteira.corretora ? ` - ${carteira.corretora}` : ""}
            </p>
          </div>
        </button>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          <button onClick={onEdit} className="p-1.5 rounded-md hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
          <button onClick={onClick} className="p-1.5">
            <ChevronRight className="w-5 h-5 text-muted-foreground" />
          </button>
        </div>
      </div>

      <button onClick={onClick} className="w-full text-left">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-xs text-muted-foreground">Valor Total</p>
            <p className="text-xl font-bold">{formatCurrency(valorTotal)}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Ganho/Perda</p>
            <div className={`flex items-center gap-1 text-sm font-semibold ${isPositive ? "text-emerald-500" : "text-red-500"}`}>
              {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              <span>{formatCurrency(Math.abs(ganhoPerdaTotal))}</span>
            </div>
          </div>
        </div>

        {carteira.total_ativos !== undefined && (
          <p className="text-xs text-muted-foreground mt-3">
            {carteira.total_ativos} ativo{carteira.total_ativos !== 1 ? "s" : ""}
          </p>
        )}
      </button>

      {!carteira.ativo && (
        <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          Inativa
        </span>
      )}
    </div>
  );
}

const TIPO_CARTEIRA_OPTIONS = ["geral", "acoes", "renda_fixa", "fundos", "crypto", "previdencia", "outro"];
const EMPTY_FORM = { nome: "", tipo: "geral", corretora: "" };

export default function CarteiraPag() {
  const navigate = useNavigate();
  const { data: carteiras, isLoading } = useCarteiras();
  const createMutation = useCreateCarteira();
  const updateMutation = useUpdateCarteira();
  const deleteMutation = useDeleteCarteira();

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingCarteira, setEditingCarteira] = useState<Carteira | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingCarteira(null);
    setModal("create");
  };

  const openEdit = (c: Carteira) => {
    setForm({ nome: c.nome, tipo: c.tipo || "geral", corretora: c.corretora || "" });
    setEditingCarteira(c);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (modal === "edit" && editingCarteira) {
      updateMutation.mutate({ id: editingCarteira.id, ...form }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(form, { onSuccess: () => setModal(null) });
    }
  };

  const handleDelete = () => {
    if (!deleteConfirmId) return;
    deleteMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const lista = carteiras || [];
  const totalValor = lista.reduce((acc, c) => acc + (c.valor_total || 0), 0);
  const totalGanhoPerda = lista.reduce((acc, c) => acc + (c.ganho_perda_total || 0), 0);
  const isPositiveTotal = totalGanhoPerda >= 0;
  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Investimentos</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Carteira
        </button>
      </div>

      {/* Summary */}
      {lista.length > 0 && (
        <div className="rounded-lg border bg-card p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Valor Total Investido</p>
              <p className="text-3xl font-bold">{formatCurrency(totalValor)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Ganho/Perda Total</p>
              <div className={`flex items-center gap-2 ${isPositiveTotal ? "text-emerald-500" : "text-red-500"}`}>
                {isPositiveTotal ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
                <p className="text-3xl font-bold">{formatCurrency(Math.abs(totalGanhoPerda))}</p>
              </div>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            {lista.length} carteira{lista.length !== 1 ? "s" : ""}
          </p>
        </div>
      )}

      {/* Portfolio Cards */}
      {lista.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {lista.map((carteira) => (
            <CarteiraCard
              key={carteira.id}
              carteira={carteira}
              onClick={() => navigate(`/carteira/${carteira.id}`)}
              onEdit={() => openEdit(carteira)}
              onDelete={() => setDeleteConfirmId(carteira.id)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Briefcase className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma carteira cadastrada</p>
          <p className="text-sm">Crie uma carteira para acompanhar seus investimentos.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Carteira" : "Nova Carteira"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tipo</label>
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
              {TIPO_CARTEIRA_OPTIONS.map((v) => (
                <option key={v} value={v}>{v.charAt(0).toUpperCase() + v.slice(1).replace("_", " ")}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Corretora</label>
            <input type="text" value={form.corretora} onChange={(e) => setForm({ ...form, corretora: e.target.value })} className={inputClass} />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setModal(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={isSaving} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {isSaving ? "Salvando..." : "Salvar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Carteira">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta carteira? Todos os ativos associados serao removidos.
        </p>
        <div className="flex justify-end gap-3">
          <button onClick={() => setDeleteConfirmId(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            Cancelar
          </button>
          <button onClick={handleDelete} disabled={deleteMutation.isPending} className="px-4 py-2 rounded-md bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition disabled:opacity-50">
            {deleteMutation.isPending ? "Excluindo..." : "Excluir"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
