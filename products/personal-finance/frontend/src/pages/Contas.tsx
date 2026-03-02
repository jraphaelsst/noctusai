import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useContas, useCreateConta, useUpdateConta, useDeleteConta } from "@/hooks/useContas";
import { formatCurrency } from "@/lib/utils";
import { TIPO_CONTA_LABELS } from "@/lib/constants";
import type { Conta } from "@/types";
import Modal from "@/components/Modal";
import { Plus, Wallet, Building2, CreditCard, PiggyBank, Landmark, BanknoteIcon, Pencil, Trash2 } from "lucide-react";

const ICON_MAP: Record<string, React.ElementType> = {
  corrente: Building2,
  poupanca: PiggyBank,
  cartao_credito: CreditCard,
  investimento: Landmark,
  carteira: Wallet,
  emprestimo: BanknoteIcon,
};

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function ContaCard({ conta, onEdit, onDelete, onClick }: { conta: Conta; onEdit: () => void; onDelete: () => void; onClick: () => void }) {
  const Icon = ICON_MAP[conta.tipo] || Wallet;
  const isNegative = conta.saldo < 0;

  return (
    <div
      className="rounded-lg border bg-card p-4 space-y-3 transition-shadow hover:shadow-md cursor-pointer"
      style={{ borderLeftWidth: 4, borderLeftColor: conta.cor || "hsl(var(--primary))" }}
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
          style={{ backgroundColor: conta.cor ? `${conta.cor}20` : "hsl(var(--muted))" }}
        >
          {conta.icone ? (
            <span className="text-lg">{conta.icone}</span>
          ) : (
            <Icon className="w-5 h-5" style={{ color: conta.cor || "hsl(var(--primary))" }} />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold truncate">{conta.nome}</p>
          <p className="text-xs text-muted-foreground">
            {TIPO_CONTA_LABELS[conta.tipo] || conta.tipo}
            {conta.instituicao ? ` - ${conta.instituicao}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
          <button onClick={onEdit} className="p-1.5 rounded-md hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        </div>
      </div>
      <div>
        <p className="text-xs text-muted-foreground">Saldo</p>
        <p className={`text-xl font-bold ${isNegative ? "text-red-500" : "text-foreground"}`}>
          {formatCurrency(conta.saldo)}
        </p>
      </div>
      {!conta.ativo && (
        <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          Inativa
        </span>
      )}
    </div>
  );
}

const EMPTY_FORM = { nome: "", tipo: "corrente", instituicao: "", saldo: 0, moeda: "BRL", cor: "#6366f1" };

export default function Contas() {
  const navigate = useNavigate();
  const { data: contas, isLoading } = useContas();
  const createMutation = useCreateConta();
  const updateMutation = useUpdateConta();
  const deleteMutation = useDeleteConta();

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingConta, setEditingConta] = useState<Conta | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingConta(null);
    setModal("create");
  };

  const openEdit = (conta: Conta) => {
    setForm({
      nome: conta.nome,
      tipo: conta.tipo,
      instituicao: conta.instituicao || "",
      saldo: conta.saldo,
      moeda: conta.moeda || "BRL",
      cor: conta.cor || "#6366f1",
    });
    setEditingConta(conta);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = { ...form, saldo: Number(form.saldo) };
    if (modal === "edit" && editingConta) {
      updateMutation.mutate({ id: editingConta.id, ...payload }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(payload, { onSuccess: () => setModal(null) });
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

  const lista = contas || [];
  const totalSaldo = lista.reduce((acc, c) => acc + c.saldo, 0);
  const isNegativeTotal = totalSaldo < 0;
  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Contas</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Conta
        </button>
      </div>

      {/* Total Balance */}
      <div className="rounded-lg border bg-card p-6">
        <p className="text-sm text-muted-foreground">Saldo Total</p>
        <p className={`text-3xl font-bold ${isNegativeTotal ? "text-red-500" : "text-foreground"}`}>
          {formatCurrency(totalSaldo)}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          {lista.length} conta{lista.length !== 1 ? "s" : ""} cadastrada{lista.length !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Account Cards */}
      {lista.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {lista.map((conta) => (
            <ContaCard
              key={conta.id}
              conta={conta}
              onEdit={() => openEdit(conta)}
              onDelete={() => setDeleteConfirmId(conta.id)}
              onClick={() => navigate(`/contas/${conta.id}`)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Wallet className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma conta cadastrada</p>
          <p className="text-sm">Adicione sua primeira conta para comecar a controlar suas financas.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Conta" : "Nova Conta"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Tipo *</label>
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
              {Object.entries(TIPO_CONTA_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Instituicao</label>
            <input type="text" value={form.instituicao} onChange={(e) => setForm({ ...form, instituicao: e.target.value })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Saldo Inicial</label>
            <input type="number" step="0.01" value={form.saldo} onChange={(e) => setForm({ ...form, saldo: Number(e.target.value) })} className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Moeda</label>
              <select value={form.moeda} onChange={(e) => setForm({ ...form, moeda: e.target.value })} className={inputClass}>
                <option value="BRL">BRL</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Cor</label>
              <input type="color" value={form.cor} onChange={(e) => setForm({ ...form, cor: e.target.value })} className="w-full h-[38px] rounded-md border bg-background cursor-pointer" />
            </div>
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
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Conta">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta conta? Esta acao nao pode ser desfeita.
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
