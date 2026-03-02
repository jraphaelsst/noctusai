import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMeta, useMetaProgresso, useUpdateMeta, useDeleteMeta, useAddContribuicao } from "@/hooks/useMetas";
import { formatCurrency, formatDate } from "@/lib/utils";
import { PRIORIDADE_LABELS } from "@/lib/constants";
import type { Meta } from "@/types";
import Modal from "@/components/Modal";
import { ArrowLeft, Pencil, Trash2, DollarSign, Target } from "lucide-react";

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

const EMPTY_FORM = { nome: "", tipo: "poupanca", valor_alvo: 0, data_alvo: "", prioridade: "media", status: "ativa", icone: "", cor: "#10b981" };
const EMPTY_CONTRIBUICAO = { valor: 0, descricao: "" };

export default function MetaDetalhes() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: meta, isLoading } = useMeta(id);
  const { data: _progresso } = useMetaProgresso(id);
  const updateMutation = useUpdateMeta();
  const deleteMutation = useDeleteMeta();
  const contribuicaoMutation = useAddContribuicao();

  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [contribuirOpen, setContribuirOpen] = useState(false);
  const [contribForm, setContribForm] = useState(EMPTY_CONTRIBUICAO);

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
    setEditOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!meta) return;
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
    updateMutation.mutate({ id: meta.id, ...payload }, { onSuccess: () => setEditOpen(false) });
  };

  const handleDelete = () => {
    if (!meta) return;
    deleteMutation.mutate(meta.id, { onSuccess: () => navigate("/metas") });
  };

  const handleContribuir = (e: React.FormEvent) => {
    e.preventDefault();
    if (!meta) return;
    contribuicaoMutation.mutate(
      { id: meta.id, valor: Number(contribForm.valor), descricao: contribForm.descricao || undefined },
      { onSuccess: () => { setContribuirOpen(false); setContribForm(EMPTY_CONTRIBUICAO); } },
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="space-y-6">
        <button onClick={() => navigate("/metas")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">Meta nao encontrada</p>
        </div>
      </div>
    );
  }

  const pct = meta.valor_alvo > 0 ? (meta.valor_atual / meta.valor_alvo) * 100 : 0;
  const remaining = Math.max(0, meta.valor_alvo - meta.valor_atual);
  const statusCfg = STATUS_CONFIG[meta.status] || { label: meta.status, className: "bg-muted text-muted-foreground" };
  const prioridadeCfg = PRIORIDADE_CONFIG[meta.prioridade] || { className: "bg-muted text-muted-foreground" };

  const getBarColor = () => {
    if (meta.status === "concluida") return "bg-blue-500";
    if (pct >= 100) return "bg-emerald-500";
    if (pct >= 60) return "bg-primary";
    return "bg-amber-500";
  };

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <button onClick={() => navigate("/metas")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
        <ArrowLeft className="w-4 h-4" />
        Voltar para Metas
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center shrink-0 text-2xl"
            style={{ backgroundColor: meta.cor ? `${meta.cor}20` : "hsl(var(--muted))" }}
          >
            {meta.icone || <Target className="w-7 h-7" style={{ color: meta.cor || "hsl(var(--primary))" }} />}
          </div>
          <div>
            <h1 className="text-2xl font-bold">{meta.nome}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-medium capitalize">{meta.tipo.replace("_", " ")}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${prioridadeCfg.className}`}>
                {PRIORIDADE_LABELS[meta.prioridade] || meta.prioridade}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusCfg.className}`}>
                {statusCfg.label}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {meta.status === "ativa" && (
            <button
              onClick={() => { setContribForm(EMPTY_CONTRIBUICAO); setContribuirOpen(true); }}
              className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition"
            >
              <DollarSign className="w-3.5 h-3.5" />
              Contribuir
            </button>
          )}
          <button onClick={() => openEdit(meta)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            <Pencil className="w-3.5 h-3.5" />
            Editar
          </button>
          <button onClick={() => setDeleteOpen(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-500/30 text-red-500 text-sm hover:bg-red-500/10 transition">
            <Trash2 className="w-3.5 h-3.5" />
            Excluir
          </button>
        </div>
      </div>

      {/* Progress Section */}
      <div className="rounded-lg border bg-card p-6 space-y-4" style={{ borderLeftWidth: 4, borderLeftColor: meta.cor || "hsl(var(--primary))" }}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-muted-foreground">Valor Atual</p>
            <p className="text-2xl font-bold">{formatCurrency(meta.valor_atual)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Valor Alvo</p>
            <p className="text-2xl font-bold">{formatCurrency(meta.valor_alvo)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Restante</p>
            <p className="text-2xl font-bold">{formatCurrency(remaining)}</p>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Progresso</span>
            <span className="font-semibold text-lg">{pct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-muted rounded-full h-5">
            <div
              className={`h-5 rounded-full transition-all ${getBarColor()}`}
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
        </div>

        {meta.data_alvo && (
          <div className="pt-2">
            <p className="text-sm text-muted-foreground">
              Data alvo: <span className="font-medium text-foreground">{formatDate(meta.data_alvo)}</span>
            </p>
          </div>
        )}
      </div>

      {/* Contribute Modal */}
      <Modal open={contribuirOpen} onClose={() => setContribuirOpen(false)} title={`Contribuir — ${meta.nome}`}>
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
            <button type="button" onClick={() => setContribuirOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={contribuicaoMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {contribuicaoMutation.isPending ? "Salvando..." : "Contribuir"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Editar Meta">
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
          <div>
            <label className="block text-sm font-medium mb-1">Status</label>
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className={inputClass}>
              {Object.entries(STATUS_CONFIG).map(([v, c]) => (
                <option key={v} value={v}>{c.label}</option>
              ))}
            </select>
          </div>
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
            <button type="button" onClick={() => setEditOpen(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={updateMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {updateMutation.isPending ? "Salvando..." : "Salvar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Excluir Meta">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta meta e todas as suas contribuicoes?
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
    </div>
  );
}
