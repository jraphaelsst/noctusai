import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useConta, useUpdateConta, useDeleteConta } from "@/hooks/useContas";
import { useTransacoes } from "@/hooks/useTransacoes";
import { formatCurrency, formatDate } from "@/lib/utils";
import { TIPO_CONTA_LABELS, TIPO_TRANSACAO_LABELS } from "@/lib/constants";
import type { Conta } from "@/types";
import Modal from "@/components/Modal";
import {
  ArrowLeft, Pencil, Trash2,
  Wallet, Building2, CreditCard, PiggyBank, Landmark, BanknoteIcon,
  ChevronLeft, ChevronRight,
} from "lucide-react";

const ICON_MAP: Record<string, React.ElementType> = {
  corrente: Building2,
  poupanca: PiggyBank,
  cartao_credito: CreditCard,
  investimento: Landmark,
  carteira: Wallet,
  emprestimo: BanknoteIcon,
};

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const EMPTY_FORM = { nome: "", tipo: "corrente", instituicao: "", saldo: 0, moeda: "BRL", cor: "#6366f1" };

export default function ContaDetalhes() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: conta, isLoading: contaLoading } = useConta(id);
  const updateMutation = useUpdateConta();
  const deleteMutation = useDeleteConta();

  const [page, setPage] = useState(1);
  const pageSize = 10;
  const { data: transacoesResult, isLoading: txLoading } = useTransacoes({ conta_id: id, page, page_size: pageSize });

  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const openEdit = (c: Conta) => {
    setForm({
      nome: c.nome,
      tipo: c.tipo,
      instituicao: c.instituicao || "",
      saldo: c.saldo,
      moeda: c.moeda || "BRL",
      cor: c.cor || "#6366f1",
    });
    setEditOpen(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!conta) return;
    updateMutation.mutate({ id: conta.id, ...form, saldo: Number(form.saldo) }, { onSuccess: () => setEditOpen(false) });
  };

  const handleDelete = () => {
    if (!conta) return;
    deleteMutation.mutate(conta.id, { onSuccess: () => navigate("/contas") });
  };

  if (contaLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!conta) {
    return (
      <div className="space-y-6">
        <button onClick={() => navigate("/contas")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">Conta nao encontrada</p>
        </div>
      </div>
    );
  }

  const Icon = ICON_MAP[conta.tipo] || Wallet;
  const isNegative = conta.saldo < 0;
  const transacoes = transacoesResult?.data || [];
  const totalTx = transacoesResult?.total || 0;
  const totalPages = Math.max(1, Math.ceil(totalTx / pageSize));

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <button onClick={() => navigate("/contas")} className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition">
        <ArrowLeft className="w-4 h-4" />
        Voltar para Contas
      </button>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center shrink-0"
            style={{ backgroundColor: conta.cor ? `${conta.cor}20` : "hsl(var(--muted))" }}
          >
            {conta.icone ? (
              <span className="text-2xl">{conta.icone}</span>
            ) : (
              <Icon className="w-7 h-7" style={{ color: conta.cor || "hsl(var(--primary))" }} />
            )}
          </div>
          <div>
            <h1 className="text-2xl font-bold">{conta.nome}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted font-medium">
                {TIPO_CONTA_LABELS[conta.tipo] || conta.tipo}
              </span>
              {conta.instituicao && (
                <span className="text-sm text-muted-foreground">{conta.instituicao}</span>
              )}
              {!conta.ativo && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-500 font-medium">Inativa</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => openEdit(conta)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border bg-background text-sm hover:bg-accent transition">
            <Pencil className="w-3.5 h-3.5" />
            Editar
          </button>
          <button onClick={() => setDeleteOpen(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-md border border-red-500/30 text-red-500 text-sm hover:bg-red-500/10 transition">
            <Trash2 className="w-3.5 h-3.5" />
            Excluir
          </button>
        </div>
      </div>

      {/* Balance Card */}
      <div className="rounded-lg border bg-card p-6" style={{ borderLeftWidth: 4, borderLeftColor: conta.cor || "hsl(var(--primary))" }}>
        <p className="text-sm text-muted-foreground">Saldo</p>
        <p className={`text-3xl font-bold ${isNegative ? "text-red-500" : "text-foreground"}`}>
          {formatCurrency(conta.saldo)}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{conta.moeda || "BRL"}</p>
      </div>

      {/* Recent Transactions */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Transacoes Recentes</h2>
        <div className="rounded-lg border bg-card overflow-auto">
          {txLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : transacoes.length > 0 ? (
            <>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Descricao</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Categoria</th>
                    <th className="text-left p-3 font-medium text-muted-foreground">Tipo</th>
                    <th className="text-right p-3 font-medium text-muted-foreground">Valor</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {transacoes.map((tx) => {
                    const isReceita = tx.tipo === "receita";
                    return (
                      <tr key={tx.id} className="hover:bg-accent/50 transition-colors">
                        <td className="p-3 text-muted-foreground">{formatDate(tx.data)}</td>
                        <td className="p-3 truncate max-w-[200px]">{tx.descricao || tx.comerciante || "-"}</td>
                        <td className="p-3 text-muted-foreground">{tx.categoria?.nome || "-"}</td>
                        <td className="p-3">
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${isReceita ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"}`}>
                            {TIPO_TRANSACAO_LABELS[tx.tipo] || tx.tipo}
                          </span>
                        </td>
                        <td className={`p-3 text-right font-medium ${isReceita ? "text-emerald-500" : "text-red-500"}`}>
                          {isReceita ? "+" : "-"}{formatCurrency(Math.abs(tx.valor))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t">
                  <p className="text-xs text-muted-foreground">{totalTx} transacao{totalTx !== 1 ? "es" : ""}</p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page <= 1}
                      className="p-1.5 rounded-md border hover:bg-accent transition disabled:opacity-30"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page >= totalPages}
                      className="p-1.5 rounded-md border hover:bg-accent transition disabled:opacity-30"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-sm">Nenhuma transacao nesta conta</p>
            </div>
          )}
        </div>
      </div>

      {/* Edit Modal */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Editar Conta">
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
            <label className="block text-sm font-medium mb-1">Saldo</label>
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
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Excluir Conta">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir esta conta? Esta acao nao pode ser desfeita.
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
