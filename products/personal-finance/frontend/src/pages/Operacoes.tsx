import { useState } from "react";
import { useOperacoes, useCreateOperacao, useDeleteOperacao } from "@/hooks/useOperacoes";
import { useCarteiras } from "@/hooks/useCarteira";
import { formatCurrency, formatDate } from "@/lib/utils";
import { TIPO_ATIVO_LABELS } from "@/lib/constants";
import type { Operacao } from "@/types";
import Modal from "@/components/Modal";
import { Plus, ArrowUpDown, Trash2, TrendingUp, TrendingDown, DollarSign } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const TIPO_OPERACAO_LABELS: Record<string, string> = {
  compra: "Compra",
  venda: "Venda",
  dividendo: "Dividendo",
  jcp: "JCP",
  rendimento: "Rendimento",
  split: "Split",
  bonificacao: "Bonificacao",
  amortizacao: "Amortizacao",
  transferencia: "Transferencia",
};

const TIPO_OPERACAO_COLORS: Record<string, string> = {
  compra: "text-blue-500 bg-blue-500/10",
  venda: "text-red-500 bg-red-500/10",
  dividendo: "text-emerald-500 bg-emerald-500/10",
  jcp: "text-emerald-500 bg-emerald-500/10",
  rendimento: "text-emerald-500 bg-emerald-500/10",
};

const EMPTY_FORM = {
  carteira_id: "",
  ticker: "",
  tipo: "compra",
  data: new Date().toISOString().slice(0, 10),
  quantidade: 0,
  preco_unitario: 0,
  taxas: 0,
  valor_total: 0,
  notas: "",
};

export default function Operacoes() {
  const [filtroCarteira, setFiltroCarteira] = useState<string>("");
  const { data: operacoes, isLoading } = useOperacoes(filtroCarteira ? { carteira_id: filtroCarteira } : undefined);
  const { data: carteiras } = useCarteiras();
  const createMutation = useCreateOperacao();
  const deleteMutation = useDeleteOperacao();

  const [modal, setModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, carteira_id: filtroCarteira || (carteiras?.[0]?.id || "") });
    setModal(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = {
      carteira_id: form.carteira_id,
      ticker: form.ticker.toUpperCase(),
      tipo: form.tipo,
      data: form.data,
      valor_total: Number(form.valor_total),
      taxas: Number(form.taxas) || 0,
      notas: form.notas || undefined,
    };
    if (form.quantidade) payload.quantidade = Number(form.quantidade);
    if (form.preco_unitario) payload.preco_unitario = Number(form.preco_unitario);
    createMutation.mutate(payload, { onSuccess: () => setModal(false) });
  };

  const handleDelete = () => {
    if (!deleteConfirmId) return;
    deleteMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  // Auto-calculate valor_total from quantidade * preco_unitario
  const updateCalc = (field: string, value: number) => {
    const newForm = { ...form, [field]: value };
    if (field === "quantidade" || field === "preco_unitario") {
      const qty = field === "quantidade" ? value : form.quantidade;
      const price = field === "preco_unitario" ? value : form.preco_unitario;
      if (qty && price) {
        newForm.valor_total = Number((qty * price).toFixed(2));
      }
    }
    setForm(newForm);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const lista = operacoes || [];

  // Summary KPIs
  const totalCompras = lista.filter((o) => o.tipo === "compra").reduce((a, o) => a + o.valor_total, 0);
  const totalVendas = lista.filter((o) => o.tipo === "venda").reduce((a, o) => a + o.valor_total, 0);
  const totalProventos = lista
    .filter((o) => ["dividendo", "jcp", "rendimento"].includes(o.tipo))
    .reduce((a, o) => a + o.valor_total, 0);

  const getOperacaoIcon = (tipo: string) => {
    if (tipo === "compra") return <TrendingUp className="w-4 h-4" />;
    if (tipo === "venda") return <TrendingDown className="w-4 h-4" />;
    return <DollarSign className="w-4 h-4" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Operacoes</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Operacao
        </button>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <label className="text-sm font-medium text-muted-foreground">Carteira:</label>
        <select
          value={filtroCarteira}
          onChange={(e) => setFiltroCarteira(e.target.value)}
          className="px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="">Todas</option>
          {(carteiras || []).map((c) => (
            <option key={c.id} value={c.id}>{c.nome}</option>
          ))}
        </select>
      </div>

      {/* Summary Cards */}
      {lista.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Total Compras</p>
            <p className="text-xl font-bold text-blue-500">{formatCurrency(totalCompras)}</p>
            <p className="text-xs text-muted-foreground">{lista.filter((o) => o.tipo === "compra").length} operacao(es)</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Total Vendas</p>
            <p className="text-xl font-bold text-red-500">{formatCurrency(totalVendas)}</p>
            <p className="text-xs text-muted-foreground">{lista.filter((o) => o.tipo === "venda").length} operacao(es)</p>
          </div>
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Proventos</p>
            <p className="text-xl font-bold text-emerald-500">{formatCurrency(totalProventos)}</p>
            <p className="text-xs text-muted-foreground">
              {lista.filter((o) => ["dividendo", "jcp", "rendimento"].includes(o.tipo)).length} operacao(es)
            </p>
          </div>
        </div>
      )}

      {/* Operations List */}
      {lista.length > 0 ? (
        <div className="rounded-lg border bg-card divide-y">
          {lista.map((op) => {
            const colorClass = TIPO_OPERACAO_COLORS[op.tipo] || "text-muted-foreground bg-muted";
            return (
              <div key={op.id} className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${colorClass}`}>
                    {getOperacaoIcon(op.tipo)}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold">{op.ticker}</p>
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${colorClass}`}>
                        {TIPO_OPERACAO_LABELS[op.tipo] || op.tipo}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{formatDate(op.data)}</span>
                      {op.quantidade && (
                        <>
                          <span className="text-muted-foreground/40">|</span>
                          <span>{op.quantidade} un</span>
                        </>
                      )}
                      {op.preco_unitario && (
                        <>
                          <span className="text-muted-foreground/40">|</span>
                          <span>@ {formatCurrency(op.preco_unitario)}</span>
                        </>
                      )}
                      {op.notas && (
                        <>
                          <span className="text-muted-foreground/40">|</span>
                          <span className="truncate max-w-[150px]">{op.notas}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0 ml-4">
                  <div className="text-right">
                    <span className="text-sm font-semibold">{formatCurrency(op.valor_total)}</span>
                    {op.taxas > 0 && (
                      <p className="text-xs text-muted-foreground">Taxas: {formatCurrency(op.taxas)}</p>
                    )}
                  </div>
                  <button
                    onClick={() => setDeleteConfirmId(op.id)}
                    className="p-1.5 rounded-md hover:bg-red-500/10 transition"
                    title="Excluir"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-red-500" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <ArrowUpDown className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma operacao registrada</p>
          <p className="text-sm">Registre compras, vendas e proventos dos seus investimentos.</p>
        </div>
      )}

      {/* Create Modal */}
      <Modal open={modal} onClose={() => setModal(false)} title="Nova Operacao">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Carteira *</label>
              <select value={form.carteira_id} onChange={(e) => setForm({ ...form, carteira_id: e.target.value })} className={inputClass} required>
                <option value="">Selecionar</option>
                {(carteiras || []).map((c) => (
                  <option key={c.id} value={c.id}>{c.nome}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Ticker *</label>
              <input type="text" required value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} className={inputClass} placeholder="PETR4" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Tipo *</label>
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
                {Object.entries(TIPO_OPERACAO_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Data *</label>
              <input type="date" required value={form.data} onChange={(e) => setForm({ ...form, data: e.target.value })} className={inputClass} />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Quantidade</label>
              <input type="number" step="0.00000001" min="0" value={form.quantidade || ""} onChange={(e) => updateCalc("quantidade", Number(e.target.value))} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Preco Unitario</label>
              <input type="number" step="0.0001" min="0" value={form.preco_unitario || ""} onChange={(e) => updateCalc("preco_unitario", Number(e.target.value))} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Taxas</label>
              <input type="number" step="0.01" min="0" value={form.taxas || ""} onChange={(e) => setForm({ ...form, taxas: Number(e.target.value) })} className={inputClass} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Valor Total *</label>
            <input type="number" required step="0.01" min="0.01" value={form.valor_total} onChange={(e) => setForm({ ...form, valor_total: Number(e.target.value) })} className={inputClass} />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Notas</label>
            <input type="text" value={form.notas} onChange={(e) => setForm({ ...form, notas: e.target.value })} className={inputClass} placeholder="Observacoes sobre a operacao" />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={() => setModal(false)} className="px-4 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
              Cancelar
            </button>
            <button type="submit" disabled={createMutation.isPending} className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition disabled:opacity-50">
              {createMutation.isPending ? "Registrando..." : "Registrar"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Operacao">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta operacao? O ativo sera recalculado automaticamente.
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
