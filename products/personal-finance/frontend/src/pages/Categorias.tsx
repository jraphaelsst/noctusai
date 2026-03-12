import { useState } from "react";
import {
  useCategorias, useCategoriasArvore,
  useCreateCategoria, useUpdateCategoria, useDeleteCategoria,
} from "@/hooks/useCategorias";
import type { Categoria } from "@/types";
import Modal from "@/components/Modal";
import ConfirmDialog from "@/components/ConfirmDialog";
import { Plus, Tags, ChevronDown, ChevronRight, Pencil, Trash2 } from "lucide-react";

const inputClass = "w-full px-3 py-2 rounded-md border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary";

const TIPO_LABELS: Record<string, string> = { receita: "Receita", despesa: "Despesa" };

const EMPTY_FORM = { nome: "", tipo: "despesa", icone: "", cor: "#6366f1", categoria_pai_id: "" };

function SubcategoriaRow({ cat, onEdit, onDelete }: { cat: Categoria; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="flex items-center justify-between py-2 pl-10 pr-4 hover:bg-accent/50 transition-colors">
      <div className="flex items-center gap-2 min-w-0">
        {cat.icone && <span className="text-sm">{cat.icone}</span>}
        <span className="text-sm">{cat.nome}</span>
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
          cat.tipo === "receita" ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"
        }`}>
          {TIPO_LABELS[cat.tipo] || cat.tipo}
        </span>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <button onClick={onEdit} className="p-1 rounded hover:bg-accent transition" title="Editar">
          <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
        </button>
        {!cat.is_sistema && (
          <button onClick={onDelete} className="p-1 rounded hover:bg-red-500/10 transition" title="Excluir">
            <Trash2 className="w-3.5 h-3.5 text-red-500" />
          </button>
        )}
      </div>
    </div>
  );
}

function CategoriaCard({
  cat,
  onEdit,
  onDelete,
  onEditSub,
  onDeleteSub,
}: {
  cat: Categoria;
  onEdit: () => void;
  onDelete: () => void;
  onEditSub: (sub: Categoria) => void;
  onDeleteSub: (sub: Categoria) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const subs = cat.subcategorias || [];
  const hasSubs = subs.length > 0;

  return (
    <div className="rounded-lg border bg-card overflow-hidden">
      <div className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          {hasSubs ? (
            <button onClick={() => setExpanded(!expanded)} className="p-0.5">
              {expanded ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
            </button>
          ) : (
            <div className="w-5" />
          )}
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-sm"
            style={{ backgroundColor: cat.cor ? `${cat.cor}20` : "hsl(var(--muted))" }}
          >
            {cat.icone || <Tags className="w-4 h-4" style={{ color: cat.cor || undefined }} />}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{cat.nome}</p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className={`px-1.5 py-0.5 rounded-full font-medium ${
                cat.tipo === "receita" ? "bg-emerald-500/10 text-emerald-500" : "bg-red-500/10 text-red-500"
              }`}>
                {TIPO_LABELS[cat.tipo] || cat.tipo}
              </span>
              {hasSubs && <span>{subs.length} subcategoria{subs.length !== 1 ? "s" : ""}</span>}
              {cat.is_sistema && <span className="px-1.5 py-0.5 rounded-full bg-muted font-medium">Sistema</span>}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button onClick={onEdit} className="p-1.5 rounded hover:bg-accent transition" title="Editar">
            <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
          {!cat.is_sistema && (
            <button onClick={onDelete} className="p-1.5 rounded hover:bg-red-500/10 transition" title="Excluir">
              <Trash2 className="w-3.5 h-3.5 text-red-500" />
            </button>
          )}
        </div>
      </div>
      {expanded && hasSubs && (
        <div className="border-t divide-y">
          {subs.map((sub) => (
            <SubcategoriaRow
              key={sub.id}
              cat={sub}
              onEdit={() => onEditSub(sub)}
              onDelete={() => onDeleteSub(sub)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Categorias() {
  const { data: categorias, isLoading: flatLoading } = useCategorias();
  const { data: arvore, isLoading: arvoreLoading } = useCategoriasArvore();
  const createMutation = useCreateCategoria();
  const updateMutation = useUpdateCategoria();
  const deleteMutation = useDeleteCategoria();

  const [filter, setFilter] = useState<"all" | "receita" | "despesa">("all");
  const [modal, setModal] = useState<"create" | "edit" | null>(null);
  const [editingCategoria, setEditingCategoria] = useState<Categoria | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<Categoria | null>(null);

  const isLoading = flatLoading || arvoreLoading;

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingCategoria(null);
    setModal("create");
  };

  const openEdit = (cat: Categoria) => {
    setForm({
      nome: cat.nome,
      tipo: cat.tipo,
      icone: cat.icone || "",
      cor: cat.cor || "#6366f1",
      categoria_pai_id: cat.categoria_pai_id || "",
    });
    setEditingCategoria(cat);
    setModal("edit");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: any = {
      nome: form.nome,
      tipo: form.tipo,
      icone: form.icone || undefined,
      cor: form.cor || undefined,
      categoria_pai_id: form.categoria_pai_id || undefined,
    };
    if (modal === "edit" && editingCategoria) {
      updateMutation.mutate({ id: editingCategoria.id, ...payload }, { onSuccess: () => setModal(null) });
    } else {
      createMutation.mutate(payload, { onSuccess: () => setModal(null) });
    }
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  const parentCategories = (categorias || []).filter((c) => !c.categoria_pai_id);

  const tree = (arvore || []).filter((cat) => {
    if (filter === "all") return true;
    return cat.tipo === filter;
  });

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Categorias</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition"
        >
          <Plus className="w-4 h-4" />
          Nova Categoria
        </button>
      </div>

      {/* Type Filter Tabs */}
      <div className="flex items-center gap-2">
        {([["all", "Todas"], ["receita", "Receitas"], ["despesa", "Despesas"]] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setFilter(key)}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition ${
              filter === key
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Category Tree */}
      {tree.length > 0 ? (
        <div className="space-y-2">
          {tree.map((cat) => (
            <CategoriaCard
              key={cat.id}
              cat={cat}
              onEdit={() => openEdit(cat)}
              onDelete={() => setDeleteTarget(cat)}
              onEditSub={(sub) => openEdit(sub)}
              onDeleteSub={(sub) => setDeleteTarget(sub)}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <Tags className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p className="text-lg font-medium">Nenhuma categoria</p>
          <p className="text-sm">Crie categorias para organizar suas transacoes.</p>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal open={modal !== null} onClose={() => setModal(null)} title={modal === "edit" ? "Editar Categoria" : "Nova Categoria"}>
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
              <label className="block text-sm font-medium mb-1">Categoria Pai</label>
              <select value={form.categoria_pai_id} onChange={(e) => setForm({ ...form, categoria_pai_id: e.target.value })} className={inputClass}>
                <option value="">Nenhuma (raiz)</option>
                {parentCategories.map((c) => (
                  <option key={c.id} value={c.id}>{c.icone ? `${c.icone} ` : ""}{c.nome}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Icone</label>
              <input type="text" value={form.icone} onChange={(e) => setForm({ ...form, icone: e.target.value })} className={inputClass} placeholder="Ex: 🏠" />
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
      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDelete}
        title="Excluir Categoria"
        message={`Tem certeza que deseja excluir "${deleteTarget?.nome}"? Transacoes vinculadas ficarao sem categoria.`}
        confirmLabel="Excluir"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
