import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useOrcamentos, useOrcamentoProgresso, useCreateOrcamento, useUpdateOrcamento, useDeleteOrcamento } from "@/hooks/useOrcamentos";
import { formatCurrency, getCurrentMonth, getMonthLabel } from "@/lib/utils";
import { METODO_ORCAMENTO_LABELS } from "@/lib/constants";
import type { Orcamento, OrcamentoItem } from "@/types";
import Modal from "@/components/Modal";
import { Plus, PiggyBank, Pencil, Trash2 } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function OrcamentoProgressoCard({ orcamento, periodoMes, onEdit, onDelete, onClick }: { orcamento: Orcamento; periodoMes: string; onEdit: () => void; onDelete: () => void; onClick: () => void }) {
  const { data: progresso } = useOrcamentoProgresso(orcamento.id, periodoMes);

  const itens: OrcamentoItem[] = progresso?.itens || [];
  const totalPlanejado = itens.reduce((acc: number, item: OrcamentoItem) => acc + item.valor_planejado, 0);
  const totalGasto = itens.reduce((acc: number, item: OrcamentoItem) => acc + item.valor_gasto, 0);
  const pctTotal = totalPlanejado > 0 ? (totalGasto / totalPlanejado) * 100 : 0;

  const getBarColor = (pct: number) => {
    if (pct >= 100) return "bg-red-500";
    if (pct >= 80) return "bg-amber-500";
    return "bg-emerald-500";
  };

  return (
    <div className="rounded-lg border bg-card p-5 space-y-4 cursor-pointer hover:shadow-md transition-shadow" onClick={onClick}>
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-lg">{orcamento.nome}</h3>
          <p className="text-xs text-muted-foreground">
            {METODO_ORCAMENTO_LABELS[orcamento.metodo] || orcamento.metodo}
            {!orcamento.ativo && " - Inativo"}
          </p>
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          <div className="text-right mr-2">
            <p className="text-sm font-medium">{formatCurrency(totalGasto)}</p>
            <p className="text-xs text-muted-foreground">de {formatCurrency(totalPlanejado)}</p>
          </div>
          <button onClick={onEdit} className="p-1.5 rounded-md hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        </div>
      </div>

      {/* Overall gauge */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Total</span>
          <span>{pctTotal.toFixed(0)}%</span>
        </div>
        <div className="w-full bg-muted rounded-full h-3">
          <div
            className={`h-3 rounded-full transition-all ${getBarColor(pctTotal)}`}
            style={{ width: `${Math.min(pctTotal, 100)}%` }}
          />
        </div>
      </div>

      {/* Category progress bars */}
      {itens.length > 0 && (
        <div className="space-y-3 pt-2">
          {itens.map((item: OrcamentoItem) => {
            const pct = item.valor_planejado > 0 ? (item.valor_gasto / item.valor_planejado) * 100 : 0;
            return (
              <div key={item.id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium truncate">{item.categoria?.nome || "Categoria"}</span>
                  <span className="text-muted-foreground ml-2 shrink-0">
                    {formatCurrency(item.valor_gasto)} / {formatCurrency(item.valor_planejado)}
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${getBarColor(pct)}`}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {itens.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-2">Nenhuma categoria configurada</p>
      )}
    </div>
  );
}

const EMPTY_FORM = { nome: "", metodo: "zero_based", periodo: "mensal", ativo: true };

export default function Orcamentos() {
  const navigate = useNavigate();
  const { data: orcamentos, isLoading } = useOrcamentos();
  const createMutation = useCreateOrcamento();
  const updateMutation = useUpdateOrcamento();
  const deleteMutation = useDeleteOrcamento();

  const [periodoMes, setPeriodoMes] = useState(getCurrentMonth());
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingOrcamento, setEditingOrcamento] = useState<Orcamento | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingOrcamento(null);
    setModal("create");
  };

  const openEdit = (o: Orcamento) => {
    setForm({ nome: o.nome, metodo: o.metodo, periodo: o.periodo, ativo: o.ativo });
    setEditingOrcamento(o);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (modal === "edit" && editingOrcamento) {
      updateMutation.mutate({ id: editingOrcamento.id, ...form }, { onSuccess: () => setModal(null) });
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

  const lista = orcamentos || [];
  const isSaving = createMutation.isPending || updateMutation.isPending;

  // Build month selector options (current + last 11 months)
  const meses: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    meses.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Orcamentos</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Novo Orcamento
        </button>
      </div>

      {/* Period selector */}
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

      {/* Budget Cards */}
      {lista.length > 0 ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {lista.map((orcamento) => (
            <OrcamentoProgressoCard
              key={orcamento.id}
              orcamento={orcamento}
              periodoMes={periodoMes}
              onEdit={() => openEdit(orcamento)}
              onDelete={() => setDeleteConfirmId(orcamento.id)}
              onClick={() => navigate(`/orcamentos/${orcamento.id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <PiggyBank className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhum orcamento cadastrado</p>
          <p className="text-sm">Crie um orcamento para controlar seus gastos por categoria.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Orcamento" : "Novo Orcamento"}>
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
            <input type="checkbox" id="orcamento-ativo" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} className="rounded" />
            <label htmlFor="orcamento-ativo" className="text-sm font-medium">Ativo</label>
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
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Orcamento">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir este orcamento?
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
