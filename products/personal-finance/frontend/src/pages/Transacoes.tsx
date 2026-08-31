import { useState } from "react";
import { useTransacoes, useCreateTransacao, useUpdateTransacao, useDeleteTransacao } from "@/hooks/useTransacoes";
import { useContas } from "@/hooks/useContas";
import { useCategorias } from "@/hooks/useCategorias";
import { formatCurrency, formatDate } from "@/lib/utils";
import { TIPO_TRANSACAO_LABELS } from "@/lib/constants";
import type { Transacao } from "@/types";
import Modal from "@/components/Modal";
import { Plus, Search, ArrowLeftRight, ChevronLeft, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { AIIndicator } from "@noctusai/lib/design-system";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const EMPTY_FORM = {
  tipo: "despesa",
  conta_id: "",
  categoria_id: "",
  valor: 0,
  data: new Date().toISOString().slice(0, 10),
  descricao: "",
  comerciante: "",
  conta_destino_id: "",
};

export default function Transacoes() {
  const [page, setPage] = useState(1);
  const [busca, setBusca] = useState("");
  const [contaId, setContaId] = useState<string | undefined>();
  const [categoriaId, setCategoriaId] = useState<string | undefined>();
  const [tipo, setTipo] = useState<string | undefined>();
  const [dataInicio, setDataInicio] = useState<string | undefined>();
  const [dataFim, setDataFim] = useState<string | undefined>();
  const pageSize = 20;

  const { data: result, isPending } = useTransacoes({
    page,
    page_size: pageSize,
    busca: busca || undefined,
    conta_id: contaId,
    categoria_id: categoriaId,
    tipo,
    data_inicio: dataInicio,
    data_fim: dataFim,
  });

  const { data: contas } = useContas();
  const { data: categorias } = useCategorias();

  const createMutation = useCreateTransacao();
  const updateMutation = useUpdateTransacao();
  const deleteMutation = useDeleteTransacao();

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingTransacao, setEditingTransacao] = useState<Transacao | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const transacoes: Transacao[] = result?.data || [];
  const total = result?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, conta_id: contas?.[0]?.id || "" });
    setEditingTransacao(null);
    setModal("create");
  };

  const openEdit = (t: Transacao) => {
    setForm({
      tipo: t.tipo,
      conta_id: t.conta_id,
      categoria_id: t.categoria_id || "",
      valor: Math.abs(t.valor),
      data: t.data,
      descricao: t.descricao || "",
      comerciante: t.comerciante || "",
      conta_destino_id: t.conta_destino_id || "",
    });
    setEditingTransacao(t);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = {
      tipo: form.tipo,
      conta_id: form.conta_id,
      valor: Number(form.valor),
      data: form.data,
      descricao: form.descricao || undefined,
      comerciante: form.comerciante || undefined,
      categoria_id: form.categoria_id || undefined,
    };
    if (form.tipo === "transferencia" && form.conta_destino_id) {
      payload.conta_destino_id = form.conta_destino_id;
    }
    if (modal === "edit" && editingTransacao) {
      updateMutation.mutate({ id: editingTransacao.id, ...payload }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(payload, { onSuccess: () => setModal(null) });
    }
  };

  const handleDelete = () => {
    if (!deleteConfirmId) return;
    deleteMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  if (isPending && !result) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Transacoes</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Transacao
        </button>
      </div>

      {/* Filters */}
      <div className="rounded-lg border bg-card p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
          {/* Search */}
          <div className="relative lg:col-span-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Buscar descricao, comerciante..."
              value={busca}
              onChange={(e) => { setBusca(e.target.value); setPage(1); }}
              className="w-full pl-9 pr-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Account filter */}
          <select
            value={contaId || ""}
            onChange={(e) => { setContaId(e.target.value || undefined); setPage(1); }}
            className={inputClass}
          >
            <option value="">Todas as contas</option>
            {(contas || []).map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>

          {/* Category filter */}
          <select
            value={categoriaId || ""}
            onChange={(e) => { setCategoriaId(e.target.value || undefined); setPage(1); }}
            className={inputClass}
          >
            <option value="">Todas as categorias</option>
            {(categorias || []).map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>

          {/* Type filter */}
          <select
            value={tipo || ""}
            onChange={(e) => { setTipo(e.target.value || undefined); setPage(1); }}
            className={inputClass}
          >
            <option value="">Todos os tipos</option>
            {Object.entries(TIPO_TRANSACAO_LABELS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>

          {/* Date range */}
          <div className="flex gap-2">
            <input
              type="date"
              value={dataInicio || ""}
              onChange={(e) => { setDataInicio(e.target.value || undefined); setPage(1); }}
              className="w-full px-2 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="De"
            />
            <input
              type="date"
              value={dataFim || ""}
              onChange={(e) => { setDataFim(e.target.value || undefined); setPage(1); }}
              className="w-full px-2 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Ate"
            />
          </div>
        </div>
      </div>

      {/* Transaction List */}
      {transacoes.length > 0 ? (
        <div className="rounded-lg border bg-card divide-y">
          {transacoes.map((t) => {
            const isReceita = t.tipo === "receita";
            const isTransferencia = t.tipo === "transferencia";
            return (
              <div key={t.id} className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="w-9 h-9 rounded-full flex items-center justify-center text-sm shrink-0"
                    style={{ backgroundColor: t.categoria?.cor ? `${t.categoria.cor}20` : "hsl(var(--muted))" }}
                  >
                    {t.categoria?.icone || (isReceita ? "+" : isTransferencia ? "~" : "-")}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate flex items-center gap-2">
                      <span className="truncate">{t.descricao || t.comerciante || "Transacao"}</span>
                      <AIIndicator refType="transacao" refId={t.id} hideIcon />
                    </p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{formatDate(t.data)}</span>
                      {t.categoria?.nome && (
                        <>
                          <span className="text-muted-foreground/40">|</span>
                          <span>{t.categoria.nome}</span>
                        </>
                      )}
                      {t.conta?.nome && (
                        <>
                          <span className="text-muted-foreground/40">|</span>
                          <span>{t.conta.nome}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-4">
                  <div className="text-right">
                    <span className={`text-sm font-semibold ${isReceita ? "text-emerald-500" : isTransferencia ? "text-blue-500" : "text-red-500"}`}>
                      {isReceita ? "+" : isTransferencia ? "" : "-"}{formatCurrency(Math.abs(t.valor))}
                    </span>
                    <p className="text-xs text-muted-foreground">
                      {TIPO_TRANSACAO_LABELS[t.tipo] || t.tipo}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <button onClick={() => openEdit(t)} className="p-1.5 rounded-md hover:bg-accent transition" title="Editar">
                      <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                    <button onClick={() => setDeleteConfirmId(t.id)} className="p-1.5 rounded-md hover:bg-red-500/10 transition" title="Excluir">
                      <Trash2 className="w-3.5 h-3.5 text-red-500" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <ArrowLeftRight className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma transacao encontrada</p>
          <p className="text-sm">Ajuste os filtros ou adicione uma nova transacao.</p>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {((page - 1) * pageSize) + 1}-{Math.min(page * pageSize, total)} de {total}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="p-2 rounded-md border hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm px-3">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="p-2 rounded-md border hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Transacao" : "Nova Transacao"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Tipo *</label>
            <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
              {Object.entries(TIPO_TRANSACAO_LABELS).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Conta *</label>
              <select required value={form.conta_id} onChange={(e) => setForm({ ...form, conta_id: e.target.value })} className={inputClass}>
                <option value="">Selecione...</option>
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
          {form.tipo === "transferencia" && (
            <div>
              <label className="block text-sm font-medium mb-1">Conta Destino *</label>
              <select required value={form.conta_destino_id} onChange={(e) => setForm({ ...form, conta_destino_id: e.target.value })} className={inputClass}>
                <option value="">Selecione...</option>
                {(contas || []).filter((c) => c.id !== form.conta_id).map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}</option>
                ))}
              </select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Valor *</label>
              <input type="number" required step="0.01" min="0.01" value={form.valor} onChange={(e) => setForm({ ...form, valor: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Data *</label>
              <input type="date" required value={form.data} onChange={(e) => setForm({ ...form, data: e.target.value })} className={inputClass} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Descricao</label>
            <input type="text" value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Comerciante</label>
            <input type="text" value={form.comerciante} onChange={(e) => setForm({ ...form, comerciante: e.target.value })} className={inputClass} />
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
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Transacao">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta transacao?
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
