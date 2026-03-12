import { useState } from "react";
import { useRecorrentes, useCreateRecorrente, useUpdateRecorrente, useDeleteRecorrente, useExecutarPendentes, useExecutarUnico } from "@/hooks/useRecorrentes";
import { useContas } from "@/hooks/useContas";
import { useCategorias } from "@/hooks/useCategorias";
import { formatCurrency, formatDate } from "@/lib/utils";
import { FREQUENCIA_LABELS } from "@/lib/constants";
import type { Recorrente } from "@/types";
import Modal from "@/components/Modal";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Plus, CalendarClock, AlertTriangle, Pencil, Trash2, Play, Zap } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

function isProxima(dataStr?: string): boolean {
  if (!dataStr) return false;
  const date = new Date(dataStr + "T00:00:00");
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  const dias = diff / (1000 * 60 * 60 * 24);
  return dias >= 0 && dias <= 7;
}

function RecorrenteRow({ item, onEdit, onDelete, onExecute }: { item: Recorrente; onEdit: () => void; onDelete: () => void; onExecute: () => void }) {
  const isReceita = item.tipo === "receita";
  const proxima = isProxima(item.proxima_data);

  return (
    <div className={`flex items-center justify-between p-4 hover:bg-accent/50 transition-colors ${proxima ? "border-l-4 border-l-amber-500" : ""}`}>
      <div className="flex items-center gap-3 min-w-0">
        <div
          className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
            isReceita ? "bg-emerald-500/10" : "bg-red-500/10"
          }`}
        >
          {item.categoria?.icone || (
            <CalendarClock className={`w-4 h-4 ${isReceita ? "text-emerald-500" : "text-red-500"}`} />
          )}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium truncate">{item.nome}</p>
            {proxima && <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{FREQUENCIA_LABELS[item.frequencia] || item.frequencia}</span>
            {item.categoria?.nome && (
              <>
                <span className="text-muted-foreground/40">|</span>
                <span>{item.categoria.nome}</span>
              </>
            )}
            {item.conta?.nome && (
              <>
                <span className="text-muted-foreground/40">|</span>
                <span>{item.conta.nome}</span>
              </>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <div className="text-right">
          <span className={`text-sm font-semibold ${isReceita ? "text-emerald-500" : "text-red-500"}`}>
            {isReceita ? "+" : "-"}{formatCurrency(Math.abs(item.valor))}
          </span>
          <p className="text-xs text-muted-foreground">
            {item.proxima_data ? formatDate(item.proxima_data) : "Sem data"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={onExecute} className="p-1.5 rounded-md hover:bg-emerald-500/10 transition" title="Executar agora">
            <Play className="w-3.5 h-3.5 text-emerald-500" />
          </button>
          <button onClick={onEdit} className="p-1.5 rounded-md hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button onClick={onDelete} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        </div>
      </div>
    </div>
  );
}

const EMPTY_FORM = {
  nome: "", tipo: "despesa", valor: 0, frequencia: "mensal",
  dia_vencimento: "", conta_id: "", categoria_id: "",
  is_automatico: false, comerciante: "",
};

export default function Recorrentes() {
  const { data: recorrentes, isLoading } = useRecorrentes();
  const { data: contas } = useContas();
  const { data: categorias } = useCategorias();
  const createMutation = useCreateRecorrente();
  const updateMutation = useUpdateRecorrente();
  const deleteMutation = useDeleteRecorrente();
  const executarPendentesMutation = useExecutarPendentes();
  const executarUnicoMutation = useExecutarUnico();

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingRecorrente, setEditingRecorrente] = useState<Recorrente | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [confirmExecOpen, setConfirmExecOpen] = useState(false);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingRecorrente(null);
    setModal("create");
  };

  const openEdit = (r: Recorrente) => {
    setForm({
      nome: r.nome,
      tipo: r.tipo,
      valor: Math.abs(r.valor),
      frequencia: r.frequencia,
      dia_vencimento: r.dia_vencimento ? String(r.dia_vencimento) : "",
      conta_id: r.conta_id || "",
      categoria_id: r.categoria_id || "",
      is_automatico: r.is_automatico,
      comerciante: r.comerciante || "",
    });
    setEditingRecorrente(r);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = {
      nome: form.nome,
      tipo: form.tipo,
      valor: Number(form.valor),
      frequencia: form.frequencia,
      is_automatico: form.is_automatico,
      comerciante: form.comerciante || undefined,
      conta_id: form.conta_id || undefined,
      categoria_id: form.categoria_id || undefined,
      dia_vencimento: form.dia_vencimento ? Number(form.dia_vencimento) : undefined,
    };
    if (modal === "edit" && editingRecorrente) {
      updateMutation.mutate({ id: editingRecorrente.id, ...payload }, { onSuccess: () => setModal(null) });
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

  const lista = recorrentes || [];
  const isSaving = createMutation.isPending || updateMutation.isPending;

  // Separate and sort: upcoming first, then by next date
  const sorted = [...lista].sort((a, b) => {
    const aProx = isProxima(a.proxima_data);
    const bProx = isProxima(b.proxima_data);
    if (aProx && !bProx) return -1;
    if (!aProx && bProx) return 1;
    const aDate = a.proxima_data || "9999-12-31";
    const bDate = b.proxima_data || "9999-12-31";
    return aDate.localeCompare(bDate);
  });

  const receitas = sorted.filter((r) => r.tipo === "receita");
  const despesas = sorted.filter((r) => r.tipo === "despesa");
  const totalReceitas = receitas.reduce((acc, r) => acc + r.valor, 0);
  const totalDespesas = despesas.reduce((acc, r) => acc + r.valor, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Transacoes Recorrentes</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setConfirmExecOpen(true)}
            disabled={executarPendentesMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-md border bg-background text-sm font-medium hover:bg-accent transition disabled:opacity-50"
          >
            <Zap className="w-4 h-4" />
            {executarPendentesMutation.isPending ? "Executando..." : "Executar Pendentes"}
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
          >
            <Plus className="w-4 h-4" />
            Nova Recorrente
          </button>
        </div>
      </div>

      {/* Summary */}
      {lista.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Receitas Recorrentes</p>
            <p className="text-xl font-bold text-emerald-500">{formatCurrency(totalReceitas)}</p>
            <p className="text-xs text-muted-foreground">{receitas.length} item(ns)</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Despesas Recorrentes</p>
            <p className="text-xl font-bold text-red-500">{formatCurrency(totalDespesas)}</p>
            <p className="text-xs text-muted-foreground">{despesas.length} item(ns)</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Fluxo Recorrente</p>
            <p className={`text-xl font-bold ${totalReceitas - totalDespesas >= 0 ? "text-emerald-500" : "text-red-500"}`}>
              {formatCurrency(totalReceitas - totalDespesas)}
            </p>
            <p className="text-xs text-muted-foreground">{lista.length} total</p>
          </div>
        </div>
      )}

      {/* List */}
      {sorted.length > 0 ? (
        <div className="rounded-lg border bg-card divide-y">
          {sorted.map((item) => (
            <RecorrenteRow
              key={item.id}
              item={item}
              onEdit={() => openEdit(item)}
              onDelete={() => setDeleteConfirmId(item.id)}
              onExecute={() => executarUnicoMutation.mutate(item.id)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <CalendarClock className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma transacao recorrente</p>
          <p className="text-sm">Cadastre pagamentos e recebimentos recorrentes para acompanhar automaticamente.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Recorrente" : "Nova Recorrente"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Tipo *</label>
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
                <option value="receita">Receita</option>
                <option value="despesa">Despesa</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Valor *</label>
              <input type="number" required step="0.01" min="0.01" value={form.valor} onChange={(e) => setForm({ ...form, valor: Number(e.target.value) })} className={inputClass} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Frequencia *</label>
              <select value={form.frequencia} onChange={(e) => setForm({ ...form, frequencia: e.target.value })} className={inputClass}>
                {Object.entries(FREQUENCIA_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Dia Vencimento</label>
              <input type="number" min="1" max="31" value={form.dia_vencimento} onChange={(e) => setForm({ ...form, dia_vencimento: e.target.value })} className={inputClass} placeholder="1-31" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Conta</label>
              <select value={form.conta_id} onChange={(e) => setForm({ ...form, conta_id: e.target.value })} className={inputClass}>
                <option value="">Nenhuma</option>
                {(contas || []).map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Categoria</label>
              <select value={form.categoria_id} onChange={(e) => setForm({ ...form, categoria_id: e.target.value })} className={inputClass}>
                <option value="">Nenhuma</option>
                {(categorias || []).map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Comerciante</label>
            <input type="text" value={form.comerciante} onChange={(e) => setForm({ ...form, comerciante: e.target.value })} className={inputClass} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="rec-automatico" checked={form.is_automatico} onChange={(e) => setForm({ ...form, is_automatico: e.target.checked })} className="rounded" />
            <label htmlFor="rec-automatico" className="text-sm font-medium">Debito automatico</label>
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
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Recorrente">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta transacao recorrente?
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

      {/* Executar Pendentes Confirmation */}
      <ConfirmDialog
        open={confirmExecOpen}
        onClose={() => setConfirmExecOpen(false)}
        onConfirm={() => {
          executarPendentesMutation.mutate(undefined, { onSuccess: () => setConfirmExecOpen(false) });
        }}
        title="Executar Pendentes"
        message="Isso vai criar transacoes para todas as recorrencias vencidas. Deseja continuar?"
        confirmLabel="Executar"
        loading={executarPendentesMutation.isPending}
      />
    </div>
  );
}
