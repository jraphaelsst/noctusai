import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useCarteira, useCarteiraResumo } from "@/hooks/useCarteira";
import { useAtivos, useCreateAtivo, useUpdateAtivo, useDeleteAtivo } from "@/hooks/useAtivos";
import { useAtualizarPrecos } from "@/hooks/useCotacoes";
import { DonutChartCard } from "@/components/charts/DonutChartCard";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { TIPO_ATIVO_LABELS, CHART_COLORS } from "@/lib/constants";
import type { Ativo } from "@/types";
import Modal from "@/components/Modal";
import Breadcrumbs from "@/components/Breadcrumbs";
import {
  ArrowLeft, Plus, TrendingUp, TrendingDown,
  ArrowUpDown, ArrowUp, ArrowDown, Pencil, Trash2, RefreshCw,
} from "lucide-react";

type SortKey = "ticker" | "nome" | "quantidade" | "preco_medio" | "preco_atual" | "ganho_perda_pct" | "valor_atual";
type SortDir = "asc" | "desc";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const EMPTY_FORM = { ticker: "", nome: "", tipo: "acao", quantidade: 0, preco_medio: 0, preco_atual: 0, setor: "" };

export default function CarteiraDetalhes() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: carteira, isPending: carteiraPending } = useCarteira(id);
  const { data: ativos, isPending: ativosPending } = useAtivos(id);
  const { data: resumo } = useCarteiraResumo(id);

  const createMutation = useCreateAtivo();
  const updateMutation = useUpdateAtivo();
  const deleteMutation = useDeleteAtivo();
  const atualizarPrecosMutation = useAtualizarPrecos();

  const [sortKey, setSortKey] = useState<SortKey>("valor_atual");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingAtivo, setEditingAtivo] = useState<Ativo | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  const showSkeleton = (carteiraPending && !carteira) || (ativosPending && !ativos);

  const sortedAtivos = useMemo(() => {
    const lista = [...(ativos || [])];
    lista.sort((a, b) => {
      let va: any = a[sortKey];
      let vb: any = b[sortKey];
      if (typeof va === "string") {
        va = va.toLowerCase();
        vb = (vb || "").toLowerCase();
      }
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return lista;
  }, [ativos, sortKey, sortDir]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ArrowUpDown className="w-3 h-3 opacity-40" />;
    return sortDir === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />;
  };

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingAtivo(null);
    setModal("create");
  };

  const openEdit = (a: Ativo) => {
    setForm({
      ticker: a.ticker,
      nome: a.nome || "",
      tipo: a.tipo,
      quantidade: a.quantidade,
      preco_medio: a.preco_medio,
      preco_atual: a.preco_atual,
      setor: a.setor || "",
    });
    setEditingAtivo(a);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      ...form,
      carteira_id: id!,
      quantidade: Number(form.quantidade),
      preco_medio: Number(form.preco_medio),
      preco_atual: Number(form.preco_atual),
    };
    if (modal === "edit" && editingAtivo) {
      updateMutation.mutate({ id: editingAtivo.id, ...payload }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(payload, { onSuccess: () => setModal(null) });
    }
  };

  const handleDelete = () => {
    if (!deleteConfirmId) return;
    deleteMutation.mutate(deleteConfirmId, { onSuccess: () => setDeleteConfirmId(null) });
  };

  if (showSkeleton) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!carteira) {
    return (
      <div className="space-y-6">
        <button
          onClick={() => navigate("/carteira")}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium">Carteira nao encontrada</p>
        </div>
      </div>
    );
  }

  const valorTotal = carteira.valor_total || 0;
  const ganhoPerdaTotal = carteira.ganho_perda_total || 0;
  const isPositive = ganhoPerdaTotal >= 0;
  const lista = sortedAtivos;
  const isSaving = createMutation.isPending || updateMutation.isPending;

  // Allocation chart data by tipo
  const allocByType = lista.reduce<Record<string, number>>((acc, a) => {
    const tipo = TIPO_ATIVO_LABELS[a.tipo] || a.tipo;
    acc[tipo] = (acc[tipo] || 0) + a.valor_atual;
    return acc;
  }, {});

  const allocationData = Object.entries(allocByType).map(([nome, total], idx) => ({
    nome,
    total,
    cor: CHART_COLORS[idx % CHART_COLORS.length],
  }));

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[
        { label: "Dashboard", href: "/" },
        { label: "Investimentos", href: "/carteira" },
        { label: carteira.nome },
      ]} />

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">{carteira.nome}</h1>
          <p className="text-sm text-muted-foreground">
            {carteira.tipo}
            {carteira.corretora ? ` - ${carteira.corretora}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => atualizarPrecosMutation.mutate()}
            disabled={atualizarPrecosMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 rounded-md border bg-background text-sm font-medium hover:bg-accent transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${atualizarPrecosMutation.isPending ? "animate-spin" : ""}`} />
            {atualizarPrecosMutation.isPending ? "Atualizando..." : "Atualizar Precos"}
          </button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
          >
            <Plus className="w-4 h-4" />
            Adicionar Ativo
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Valor Total</p>
          <p className="text-2xl font-bold">{formatCurrency(valorTotal)}</p>
          {resumo?.custo_total > 0 && (
            <p className="text-xs text-muted-foreground">Custo: {formatCurrency(resumo.custo_total)}</p>
          )}
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Ganho/Perda</p>
          <div className={`flex items-center gap-2 ${isPositive ? "text-emerald-500" : "text-red-500"}`}>
            {isPositive ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
            <p className="text-2xl font-bold">{formatCurrency(Math.abs(ganhoPerdaTotal))}</p>
          </div>
          {resumo?.ganho_perda_pct !== undefined && (
            <p className={`text-xs font-medium ${isPositive ? "text-emerald-500" : "text-red-500"}`}>
              {resumo.ganho_perda_pct >= 0 ? "+" : ""}{resumo.ganho_perda_pct.toFixed(2)}%
            </p>
          )}
        </div>
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Total Ativos</p>
          <p className="text-2xl font-bold">{lista.length}</p>
        </div>
        {resumo?.alocacao_alvo && resumo.alocacao_alvo.length > 0 && (
          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">Metas de Alocacao</p>
            <div className="mt-1 space-y-1">
              {resumo.alocacao_alvo.map((alvo: any) => {
                const atual = resumo.alocacao_atual?.find((a: any) => a.tipo === alvo.classe_ativo);
                const pctAtual = atual?.percentual || 0;
                return (
                  <div key={alvo.classe_ativo} className="flex items-center justify-between text-xs">
                    <span>{TIPO_ATIVO_LABELS[alvo.classe_ativo] || alvo.classe_ativo}</span>
                    <span className={Math.abs(pctAtual - alvo.percentual) > 5 ? "text-amber-500" : "text-muted-foreground"}>
                      {pctAtual.toFixed(0)}% / {alvo.percentual}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Content: Table + Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Holdings Table */}
        <div className="lg:col-span-2 rounded-lg border bg-card overflow-auto">
          {lista.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  {([
                    ["ticker", "Ticker"],
                    ["nome", "Nome"],
                    ["quantidade", "Qtd"],
                    ["preco_medio", "PM"],
                    ["preco_atual", "Atual"],
                    ["ganho_perda_pct", "G/P %"],
                    ["valor_atual", "Valor"],
                  ] as [SortKey, string][]).map(([key, label]) => (
                    <th key={key} className="text-left p-3 font-medium text-muted-foreground">
                      <button
                        onClick={() => handleSort(key)}
                        className="flex items-center gap-1 hover:text-foreground transition"
                      >
                        {label}
                        <SortIcon col={key} />
                      </button>
                    </th>
                  ))}
                  <th className="p-3 w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {lista.map((a) => {
                  const isPos = a.ganho_perda >= 0;
                  return (
                    <tr key={a.id} className="hover:bg-accent/50 transition-colors">
                      <td className="p-3 font-semibold">{a.ticker}</td>
                      <td className="p-3 text-muted-foreground truncate max-w-[140px]">{a.nome || "-"}</td>
                      <td className="p-3">{a.quantidade}</td>
                      <td className="p-3">{formatCurrency(a.preco_medio)}</td>
                      <td className="p-3">{formatCurrency(a.preco_atual)}</td>
                      <td className={`p-3 font-medium ${isPos ? "text-emerald-500" : "text-red-500"}`}>
                        {formatPercent(a.ganho_perda_pct)}
                      </td>
                      <td className="p-3 font-medium">{formatCurrency(a.valor_atual)}</td>
                      <td className="p-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => openEdit(a)} className="p-1 rounded hover:bg-accent transition" title="Editar">
                            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
                          </button>
                          <button onClick={() => setDeleteConfirmId(a.id)} className="p-1 rounded hover:bg-red-500/10 transition" title="Excluir">
                            <Trash2 className="w-3.5 h-3.5 text-red-500" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <p className="text-sm">Nenhum ativo nesta carteira</p>
            </div>
          )}
        </div>

        {/* Allocation Chart */}
        <div>
          {allocationData.length > 0 ? (
            <DonutChartCard title="Alocacao por Tipo" data={allocationData} />
          ) : (
            <div className="rounded-lg border bg-card p-4 text-center text-muted-foreground">
              <p className="text-sm">Sem dados para exibir</p>
            </div>
          )}
        </div>
      </div>

      {/* Create/Edit Ativo Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Ativo" : "Adicionar Ativo"}>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Ticker *</label>
              <input type="text" required value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })} className={inputClass} placeholder="PETR4" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Tipo *</label>
              <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className={inputClass}>
                {Object.entries(TIPO_ATIVO_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Nome</label>
            <input type="text" value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} className={inputClass} placeholder="Petrobras PN" />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Quantidade *</label>
              <input type="number" required step="0.00000001" min="0" value={form.quantidade} onChange={(e) => setForm({ ...form, quantidade: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Preco Medio *</label>
              <input type="number" required step="0.0001" min="0" value={form.preco_medio} onChange={(e) => setForm({ ...form, preco_medio: Number(e.target.value) })} className={inputClass} />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Preco Atual *</label>
              <input type="number" required step="0.0001" min="0" value={form.preco_atual} onChange={(e) => setForm({ ...form, preco_atual: Number(e.target.value) })} className={inputClass} />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Setor</label>
            <input type="text" value={form.setor} onChange={(e) => setForm({ ...form, setor: e.target.value })} className={inputClass} placeholder="Energia" />
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
      <Modal open={deleteConfirmId !== null} onClose={() => setDeleteConfirmId(null)} title="Excluir Ativo">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir este ativo da carteira?
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
