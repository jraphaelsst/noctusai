import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMetas, useCreateMeta, useUpdateMeta, useDeleteMeta, useAddContribuicao } from "@/hooks/useMetas";
import { formatCurrency, formatDate } from "@/lib/utils";
import { PRIORIDADE_LABELS } from "@/lib/constants";
import type { Meta } from "@/types";
import Modal from "@/components/Modal";
import { Plus, Target, DollarSign, Pencil, Trash2 } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  ativa: { label: "Ativa", className: "bg-emerald-500/10 text-emerald-500" },
  concluida: { label: "Concluida", className: "bg-blue-500/10 text-blue-500" },
  pausada: { label: "Pausada", className: "bg-amber-500/10 text-amber-500" },
  cancelada: { label: "Cancelada", className: "bg-red-500/10 text-red-500" },
};

const PRIORIDADE_CONFIG: Record<string, { className: string }> = {
  alta: { className: "bg-red-500/10 text-red-500" },
  media: { className: "bg-amber-500/10 text-amber-500" },
  baixa: { className: "bg-blue-500/10 text-blue-500" },
};

const TIPO_META_OPTIONS = ["poupanca", "quitar_divida", "investimento", "fundo_emergencia", "personalizado"];

function MetaCard({ meta, onEdit, onDelete, onContribuir, onClick }: { meta: Meta; onEdit: () => void; onDelete: () => void; onContribuir: () => void; onClick: () => void }) {
  const pct = meta.valor_alvo > 0 ? (meta.valor_atual / meta.valor_alvo) * 100 : 0;
  const statusCfg = STATUS_CONFIG[meta.status] || { label: meta.status, className: "bg-muted text-muted-foreground" };
  const prioridadeCfg = PRIORIDADE_CONFIG[meta.prioridade] || { className: "bg-muted text-muted-foreground" };

  const getBarColor = () => {
    if (meta.status === "concluida") return "bg-blue-500";
    if (pct >= 100) return "bg-emerald-500";
    if (pct >= 60) return "bg-primary";
    return "bg-amber-500";
  };

  return (
    <div
      className="rounded-lg border bg-card p-5 space-y-4 transition-shadow hover:shadow-md cursor-pointer"
      style={{ borderLeftWidth: 4, borderLeftColor: meta.cor || "hsl(var(--primary))" }}
      onClick={onClick}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-lg"
            style={{ backgroundColor: meta.cor ? `${meta.cor}20` : "hsl(var(--muted))" }}
          >
            {meta.icone || <Target className="w-5 h-5" style={{ color: meta.cor || "hsl(var(--primary))" }} />}
          </div>
          <div className="min-w-0">
            <p className="font-semibold truncate">{meta.nome}</p>
            <p className="text-xs text-muted-foreground">{meta.tipo}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 ml-2" onClick={(e) => e.stopPropagation()}>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${prioridadeCfg.className}`}>
            {PRIORIDADE_LABELS[meta.prioridade] || meta.prioridade}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusCfg.className}`}>
            {statusCfg.label}
          </span>
          <button onClick={onEdit} className="p-1 rounded-md hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          <button onClick={onDelete} className="p-1 rounded-md hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        </div>
      </div>

      {/* Progress */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{formatCurrency(meta.valor_atual)}</span>
          <span className="font-medium">{formatCurrency(meta.valor_alvo)}</span>
        </div>
        <div className="w-full bg-muted rounded-full h-2.5">
          <div
            className={`h-2.5 rounded-full transition-all ${getBarColor()}`}
            style={{ width: `${Math.min(pct, 100)}%` }}
          />
        </div>
        <p className="text-xs text-muted-foreground text-right">{pct.toFixed(1)}% concluido</p>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-1" onClick={(e) => e.stopPropagation()}>
        <div className="text-xs text-muted-foreground">
          {meta.data_alvo ? (
            <span>Meta para: {formatDate(meta.data_alvo)}</span>
          ) : (
            <span>Sem data alvo</span>
          )}
        </div>
        {meta.status === "ativa" && (
          <button
            onClick={onContribuir}
            className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 font-medium transition"
          >
            <DollarSign className="w-3 h-3" />
            Contribuir
          </button>
        )}
      </div>
    </div>
  );
}

const EMPTY_FORM = { nome: "", tipo: "poupanca", valor_alvo: 0, data_alvo: "", prioridade: "media", status: "ativa", icone: "", cor: "#10b981" };
const EMPTY_CONTRIBUICAO = { valor: 0, descricao: "" };

export default function Metas() {
  const navigate = useNavigate();
  const { data: metas, isPending } = useMetas();
  const createMutation = useCreateMeta();
  const updateMutation = useUpdateMeta();
  const deleteMutation = useDeleteMeta();
  const contribuicaoMutation = useAddContribuicao();

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingMeta, setEditingMeta] = useState<Meta | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [contribuirMeta, setContribuirMeta] = useState<Meta | null>(null);
  const [contribForm, setContribForm] = useState(EMPTY_CONTRIBUICAO);

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingMeta(null);
    setModal("create");
  };

  const openEdit = (m: Meta) => {
    setForm({
      nome: m.nome,
      tipo: m.tipo,
      valor_alvo: m.valor_alvo,
      data_alvo: m.data_alvo || "",
      prioridade: m.prioridade,
      status: m.status,
      icone: m.icone || "",
      cor: m.cor || "#10b981",
    });
    setEditingMeta(m);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = {
      nome: form.nome,
      tipo: form.tipo,
      valor_alvo: Number(form.valor_alvo),
      prioridade: form.prioridade,
      status: form.status,
      cor: form.cor || undefined,
      icone: form.icone || undefined,
      data_alvo: form.data_alvo || undefined,
    };
    if (modal === "edit" && editingMeta) {
      updateMutation.mutate({ id: editingMeta.id, ...payload }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(payload, { onSuccess: () => setModal(null) });
    }
  };

  const handleDelete = () => {
    if (!deleteConfirmId) return;
    deleteMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  const handleContribuir = (e: React.FormEvent) => {
    e.preventDefault();
    if (!contribuirMeta) return;
    contribuicaoMutation.mutate(
      { id: contribuirMeta.id, valor: Number(contribForm.valor), descricao: contribForm.descricao || undefined },
      { onSuccess: () => { setContribuirMeta(null); setContribForm(EMPTY_CONTRIBUICAO); } },
    );
  };

  if (isPending && !metas) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const lista = metas || [];
  const ativas = lista.filter((m) => m.status === "ativa");
  const concluidas = lista.filter((m) => m.status === "concluida");
  const outras = lista.filter((m) => m.status !== "ativa" && m.status !== "concluida");
  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Metas Financeiras</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Meta
        </button>
      </div>

      {lista.length > 0 ? (
        <div className="space-y-6">
          {/* Active Goals */}
          {ativas.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold text-muted-foreground">Ativas ({ativas.length})</h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {ativas.map((meta) => (
                  <MetaCard
                    key={meta.id}
                    meta={meta}
                    onEdit={() => openEdit(meta)}
                    onDelete={() => setDeleteConfirmId(meta.id)}
                    onContribuir={() => { setContribuirMeta(meta); setContribForm(EMPTY_CONTRIBUICAO); }}
                    onClick={() => navigate(`/metas/${meta.id}`)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Completed Goals */}
          {concluidas.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold text-muted-foreground">Concluidas ({concluidas.length})</h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {concluidas.map((meta) => (
                  <MetaCard
                    key={meta.id}
                    meta={meta}
                    onEdit={() => openEdit(meta)}
                    onDelete={() => setDeleteConfirmId(meta.id)}
                    onContribuir={() => {}}
                    onClick={() => navigate(`/metas/${meta.id}`)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Other Goals */}
          {outras.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold text-muted-foreground">Outras ({outras.length})</h2>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {outras.map((meta) => (
                  <MetaCard
                    key={meta.id}
                    meta={meta}
                    onEdit={() => openEdit(meta)}
                    onDelete={() => setDeleteConfirmId(meta.id)}
                    onContribuir={() => {}}
                    onClick={() => navigate(`/metas/${meta.id}`)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Target className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma meta cadastrada</p>
          <p className="text-sm">Defina metas financeiras para acompanhar seu progresso.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Meta" : "Nova Meta"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Nome *</label>
            <input type="text" required value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Tipo *</label>
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
                {TIPO_META_OPTIONS.map((v) => (
                  <option key={v} value={v}>{v.charAt(0).toUpperCase() + v.slice(1).replace("_", " ")}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Valor Alvo *</label>
              <input type="number" required step="0.01" min="0.01" value={form.valor_alvo} onChange={(e) => setForm({ ...form, valor_alvo: Number(e.target.value) })} className={inputClass} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Data Alvo</label>
              <input type="date" value={form.data_alvo} onChange={(e) => setForm({ ...form, data_alvo: e.target.value })} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Prioridade</label>
              <select value={form.prioridade} onChange={(e) => setForm({ ...form, prioridade: e.target.value })} className={inputClass}>
                {Object.entries(PRIORIDADE_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
          </div>
          {modal === "edit" && (
            <div>
              <label className="block text-sm font-medium mb-1">Status</label>
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className={inputClass}>
                {Object.entries(STATUS_CONFIG).map(([v, c]) => (
                  <option key={v} value={v}>{c.label}</option>
                ))}
              </select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Icone</label>
              <input type="text" value={form.icone} onChange={(e) => setForm({ ...form, icone: e.target.value })} className={inputClass} placeholder="🎯" />
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

      {/* Contribute Modal */}
      <Modal open={contribuirMeta !== null} onClose={() => setContribuirMeta(null)} title={`Contribuir — ${contribuirMeta?.nome || ""}`}>
        <form onSubmit={handleContribuir} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Valor *</label>
            <input type="number" required step="0.01" min="0.01" value={contribForm.valor} onChange={(e) => setContribForm({ ...contribForm, valor: Number(e.target.value) })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Descricao</label>
            <input type="text" value={contribForm.descricao} onChange={(e) => setContribForm({ ...contribForm, descricao: e.target.value })} className={inputClass} placeholder="Aporte mensal" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setContribuirMeta(null)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={contribuicaoMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {contribuicaoMutation.isPending ? "Salvando..." : "Contribuir"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Meta">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta meta e todas as suas contribuicoes?
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
