/**
 * Configuracao — Leads "Configuração" subtab (§6 of leads-module-PROJECT.md).
 *
 * Sources CRUD (label/categoria/cor/ativo/ordem) · alias-map editor incl.
 * the unmapped queue · corretores CRUD + aliases. Two local sections
 * (toggle, not a nested shell tab) — Origens / Corretores — mirroring each
 * other's shape per §5.2 ("mirrors the source-alias endpoints").
 */
import { useState } from "react";
import { AlertTriangle, CheckCircle2, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Skeleton, TableSkeleton } from "@noctusai/lib/design-system";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useLeadSourceAliasMutations,
  useLeadSourceAliases,
  useLeadSourceMutations,
  useLeadSourceUnmapped,
  useLeadSources,
} from "@/hooks/useLeadsSources";
import OlxWebhookCard from "./components/OlxWebhookCard";
import ImovelWebWebhookCard from "./components/ImovelWebWebhookCard";
import ReceiverTokensCard from "./components/ReceiverTokensCard";
import {
  useLeadCorretorAliasMutations,
  useLeadCorretorAliases,
  useLeadCorretorMutations,
  useLeadCorretorUnmapped,
  useLeadCorretores,
} from "@/hooks/useLeadsCorretores";
import type {
  LeadCorretor,
  LeadCorretorInput,
  LeadSource,
  LeadSourceCategoria,
  LeadSourceInput,
} from "@/pages/leads/types";
import { describeError } from "./utils";

const CATEGORIA_OPTIONS: { value: LeadSourceCategoria; label: string }[] = [
  { value: "portal", label: "Portal" },
  { value: "social", label: "Social" },
  { value: "direto", label: "Direto" },
  { value: "parceria", label: "Parceria" },
  { value: "offline", label: "Offline" },
  { value: "outro", label: "Outro" },
];

// No `slug` field — the backend derives it from `label` server-side.
function emptySourceForm(): LeadSourceInput {
  return { label: "", categoria: "outro", cor: "#6366f1", ativo: true, ordem: 0 };
}

// ─── Sources ─────────────────────────────────────────────────────────────────

function OrigensConfig() {
  const sourcesQ = useLeadSources();
  const aliasesQ = useLeadSourceAliases();
  const unmappedQ = useLeadSourceUnmapped();
  const sources = sourcesQ.data ?? [];
  const aliases = aliasesQ.data ?? [];
  const unmapped = unmappedQ.data ?? [];
  const { create, update, remove } = useLeadSourceMutations();
  const { upsert, remove: removeAlias } = useLeadSourceAliasMutations();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LeadSource | null>(null);
  const [form, setForm] = useState<LeadSourceInput>(emptySourceForm());
  const [deleteTarget, setDeleteTarget] = useState<LeadSource | null>(null);
  const [reassignTo, setReassignTo] = useState<string>("");
  const [newAlias, setNewAlias] = useState("");
  const [newAliasSource, setNewAliasSource] = useState<string>("");
  const [mapTarget, setMapTarget] = useState<Record<string, string>>({});

  function openCreate() {
    setEditing(null);
    setForm(emptySourceForm());
    setFormOpen(true);
  }
  function openEdit(source: LeadSource) {
    setEditing(source);
    // `slug` is server-derived from `label` (never client-supplied) —
    // `LeadSourceUpdate` is `extra="forbid"`, so sending it back 422s every
    // edit (leads-p0-frontend-ux finding #4).
    setForm({
      label: source.label,
      categoria: source.categoria,
      cor: source.cor,
      ativo: source.ativo,
      ordem: source.ordem,
    });
    setFormOpen(true);
  }
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) {
      update.mutate(
        { id: editing.id, body: form },
        {
          onSuccess: () => {
            toast.success("Origem atualizada.");
            setFormOpen(false);
          },
          onError: (err) => toast.error(describeError(err, "Erro ao atualizar origem.")),
        },
      );
    } else {
      create.mutate(form, {
        onSuccess: () => {
          toast.success("Origem criada.");
          setFormOpen(false);
        },
        onError: (err) => toast.error(describeError(err, "Erro ao criar origem.")),
      });
    }
  }
  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(
      { id: deleteTarget.id, reassignTo: reassignTo || undefined },
      {
        onSuccess: () => {
          toast.success("Origem removida.");
          setDeleteTarget(null);
          setReassignTo("");
        },
        onError: (err) =>
          toast.error(
            (err as Error)?.message?.includes("409")
              ? "Ainda há leads nesta origem — escolha uma origem para reatribuir."
              : "Erro ao remover origem.",
          ),
      },
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Origens canônicas</h3>
        <Button size="sm" onClick={openCreate} data-testid="source-btn-novo">
          <Plus className="mr-2 h-4 w-4" />
          Nova origem
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        {sourcesQ.isPending && (
          <div className="p-4" data-testid="sources-loading">
            <TableSkeleton rows={5} columns={5} />
          </div>
        )}
        {sourcesQ.isError && (
          <div
            className="flex flex-wrap items-center gap-2 p-4 text-sm text-destructive"
            data-testid="sources-error"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Erro ao carregar origens.
            <Button size="sm" variant="outline" onClick={() => sourcesQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        )}
        {!sourcesQ.isPending && !sourcesQ.isFetching && !sourcesQ.isError && sources.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-foreground" data-testid="sources-empty">
            Nenhuma origem cadastrada ainda. Clique em "Nova origem" para começar.
          </div>
        )}
        {!sourcesQ.isPending && !sourcesQ.isError && sources.length > 0 && (
          <table className="w-full text-sm" data-testid="sources-table">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                <th className="px-3 py-2">Label</th>
                <th className="px-3 py-2">Categoria</th>
                <th className="px-3 py-2">Ordem</th>
                <th className="px-3 py-2">Ativo</th>
                <th className="px-3 py-2 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} className="border-b last:border-0" data-testid={`source-row-${s.id}`}>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      {s.cor && <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.cor }} />}
                      {s.label}
                    </span>
                  </td>
                  <td className="px-3 py-2">{s.categoria}</td>
                  <td className="px-3 py-2">{s.ordem}</td>
                  <td className="px-3 py-2">
                    <Badge variant={s.ativo ? "default" : "outline"}>{s.ativo ? "Ativo" : "Inativo"}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(s)} data-testid={`source-edit-${s.id}`}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(s)}
                      data-testid={`source-delete-${s.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-lg border border-border p-4">
        <h4 className="mb-2 text-sm font-semibold">Mapa de aliases</h4>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input
            placeholder="Alias (ex: VIVAVREAL)"
            value={newAlias}
            onChange={(e) => setNewAlias(e.target.value)}
            className="h-8 w-56 text-sm"
            data-testid="alias-new-input"
          />
          <Select value={newAliasSource} onValueChange={setNewAliasSource}>
            <SelectTrigger className="h-8 w-48 text-sm" data-testid="alias-new-source-select">
              <SelectValue placeholder="Origem canônica" />
            </SelectTrigger>
            <SelectContent>
              {(sources ?? []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            disabled={!newAlias || !newAliasSource}
            onClick={() =>
              upsert.mutate(
                { alias: newAlias, source_id: newAliasSource },
                {
                  onSuccess: () => {
                    toast.success("Alias mapeado.");
                    setNewAlias("");
                    setNewAliasSource("");
                  },
                  onError: (err) => toast.error(describeError(err, "Erro ao mapear alias.")),
                },
              )
            }
            data-testid="alias-new-submit"
          >
            Adicionar
          </Button>
        </div>

        {aliasesQ.isPending && (
          <div className="flex flex-wrap gap-1.5" data-testid="aliases-loading">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={22} width={104} rounded="full" announce={i === 0} />
            ))}
          </div>
        )}
        {aliasesQ.isError && (
          <p className="flex items-center gap-1.5 text-xs text-destructive" data-testid="aliases-error">
            <AlertTriangle className="h-3.5 w-3.5" />
            Erro ao carregar aliases.
            <button
              type="button"
              onClick={() => aliasesQ.refetch()}
              className="underline underline-offset-2 hover:text-destructive/80"
            >
              Tentar novamente
            </button>
          </p>
        )}
        {!aliasesQ.isPending && !aliasesQ.isFetching && !aliasesQ.isError && aliases.length === 0 && (
          <p className="text-xs text-muted-foreground" data-testid="aliases-empty">
            Nenhum alias mapeado ainda.
          </p>
        )}
        {!aliasesQ.isPending && !aliasesQ.isError && aliases.length > 0 && (
          <div className="flex flex-wrap gap-1.5" data-testid="aliases-list">
            {aliases.map((a) => (
              <span
                key={a.id}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-xs"
              >
                {a.alias} → {sources.find((s) => s.id === a.source_id)?.label ?? a.source_id}
                <button
                  type="button"
                  onClick={() => removeAlias.mutate(a.id)}
                  aria-label={`Remover alias ${a.alias}`}
                  className="ml-0.5 rounded-full hover:text-destructive"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="mt-3 border-t border-dashed border-border pt-3">
          {unmappedQ.isPending && (
            <div data-testid="sources-unmapped-loading">
              <Skeleton height={12} width={140} className="mb-2" />
              <div className="space-y-1.5">
                <Skeleton height={32} announce={false} />
                <Skeleton height={32} announce={false} />
              </div>
            </div>
          )}
          {unmappedQ.isError && (
            <div
              className="flex flex-wrap items-center gap-2 text-xs text-destructive"
              data-testid="sources-unmapped-error"
            >
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Erro ao carregar a fila de não mapeados.
              <Button size="sm" variant="outline" onClick={() => unmappedQ.refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}
          {!unmappedQ.isPending && !unmappedQ.isFetching && !unmappedQ.isError && unmapped.length === 0 && (
            <p
              className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400"
              data-testid="sources-unmapped-empty"
            >
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              Tudo mapeado — nenhuma origem pendente.
            </p>
          )}
          {!unmappedQ.isPending && !unmappedQ.isError && unmapped.length > 0 && (
            <div data-testid="sources-unmapped-queue">
              <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                Não mapeados ({unmapped.length})
              </p>
              <div className="space-y-1.5">
                {unmapped.map((u) => (
                  <div key={u.alias} className="flex items-center gap-2 text-sm">
                    <span className="w-48 truncate" title={u.alias}>
                      {u.alias}
                    </span>
                    <span className="text-xs text-muted-foreground">({u.count})</span>
                    <Select
                      value={mapTarget[u.alias] ?? ""}
                      onValueChange={(v) => setMapTarget({ ...mapTarget, [u.alias]: v })}
                    >
                      <SelectTrigger className="h-8 w-44 text-xs">
                        <SelectValue placeholder="Mapear para..." />
                      </SelectTrigger>
                      <SelectContent>
                        {sources.map((s) => (
                          <SelectItem key={s.id} value={s.id}>
                            {s.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!mapTarget[u.alias]}
                      onClick={() =>
                        upsert.mutate(
                          { alias: u.alias, source_id: mapTarget[u.alias] },
                          { onSuccess: () => toast.success("Alias mapeado.") },
                        )
                      }
                    >
                      Mapear
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent data-testid="source-form-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? "Editar origem" : "Nova origem"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label>Label</Label>
              <Input
                required
                value={form.label}
                onChange={(e) => setForm({ ...form, label: e.target.value })}
                data-testid="source-form-label"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Categoria</Label>
                <Select
                  value={form.categoria}
                  onValueChange={(v) => setForm({ ...form, categoria: v as LeadSourceCategoria })}
                >
                  <SelectTrigger data-testid="source-form-categoria">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIA_OPTIONS.map((c) => (
                      <SelectItem key={c.value} value={c.value}>
                        {c.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Cor</Label>
                <Input
                  type="color"
                  value={form.cor ?? "#6366f1"}
                  onChange={(e) => setForm({ ...form, cor: e.target.value })}
                  className="h-10 p-1"
                  data-testid="source-form-cor"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Ordem</Label>
                <Input
                  type="number"
                  value={form.ordem ?? 0}
                  onChange={(e) => setForm({ ...form, ordem: Number(e.target.value) })}
                  data-testid="source-form-ordem"
                />
              </div>
              <div className="flex items-center justify-between rounded-md border border-input px-3">
                <Label htmlFor="source-ativo">Ativo</Label>
                <Switch
                  id="source-ativo"
                  checked={form.ativo ?? true}
                  onCheckedChange={(v) => setForm({ ...form, ativo: v })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setFormOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" disabled={create.isPending || update.isPending} data-testid="source-form-submit">
                Salvar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover origem?</AlertDialogTitle>
            <AlertDialogDescription>
              Se ainda houver leads em <strong>{deleteTarget?.label}</strong>, escolha uma origem para
              reatribuí-los (opcional).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Select value={reassignTo} onValueChange={setReassignTo}>
            <SelectTrigger>
              <SelectValue placeholder="Reatribuir para (opcional)" />
            </SelectTrigger>
            <SelectContent>
              {(sources ?? [])
                .filter((s) => s.id !== deleteTarget?.id)
                .map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.label}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Remover</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ─── Corretores ──────────────────────────────────────────────────────────────

function emptyCorretorForm(): LeadCorretorInput {
  return { nome: "", cor: "#6366f1", ativo: true };
}

function CorretoresConfig() {
  const corretoresQ = useLeadCorretores();
  const aliasesQ = useLeadCorretorAliases();
  const unmappedQ = useLeadCorretorUnmapped();
  const corretores = corretoresQ.data ?? [];
  const aliases = aliasesQ.data ?? [];
  const unmapped = unmappedQ.data ?? [];
  const { create, update, remove } = useLeadCorretorMutations();
  const { upsert, remove: removeAlias } = useLeadCorretorAliasMutations();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LeadCorretor | null>(null);
  const [form, setForm] = useState<LeadCorretorInput>(emptyCorretorForm());
  const [deleteTarget, setDeleteTarget] = useState<LeadCorretor | null>(null);
  const [reassignTo, setReassignTo] = useState<string>("");
  const [newAlias, setNewAlias] = useState("");
  const [newAliasCorretor, setNewAliasCorretor] = useState<string>("");
  const [mapTarget, setMapTarget] = useState<Record<string, string>>({});

  function openCreate() {
    setEditing(null);
    setForm(emptyCorretorForm());
    setFormOpen(true);
  }
  function openEdit(corretor: LeadCorretor) {
    setEditing(corretor);
    setForm({ nome: corretor.nome, cor: corretor.cor, ativo: corretor.ativo });
    setFormOpen(true);
  }
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (editing) {
      update.mutate(
        { id: editing.id, body: form },
        {
          onSuccess: () => {
            toast.success("Corretor atualizado.");
            setFormOpen(false);
          },
          onError: (err) => toast.error(describeError(err, "Erro ao atualizar corretor.")),
        },
      );
    } else {
      create.mutate(form, {
        onSuccess: () => {
          toast.success("Corretor criado.");
          setFormOpen(false);
        },
        onError: (err) => toast.error(describeError(err, "Erro ao criar corretor.")),
      });
    }
  }
  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(
      { id: deleteTarget.id, reassignTo: reassignTo || undefined },
      {
        onSuccess: () => {
          toast.success("Corretor removido.");
          setDeleteTarget(null);
          setReassignTo("");
        },
        onError: (err) =>
          toast.error(
            (err as Error)?.message?.includes("409")
              ? "Ainda há leads deste corretor — escolha um corretor para reatribuir."
              : "Erro ao remover corretor.",
          ),
      },
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Corretores</h3>
        <Button size="sm" onClick={openCreate} data-testid="corretor-btn-novo">
          <Plus className="mr-2 h-4 w-4" />
          Novo corretor
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        {corretoresQ.isPending && (
          <div className="p-4" data-testid="corretores-loading">
            <TableSkeleton rows={5} columns={4} />
          </div>
        )}
        {corretoresQ.isError && (
          <div
            className="flex flex-wrap items-center gap-2 p-4 text-sm text-destructive"
            data-testid="corretores-error"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" />
            Erro ao carregar corretores.
            <Button size="sm" variant="outline" onClick={() => corretoresQ.refetch()}>
              Tentar novamente
            </Button>
          </div>
        )}
        {!corretoresQ.isPending && !corretoresQ.isFetching && !corretoresQ.isError && corretores.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-foreground" data-testid="corretores-empty">
            Nenhum corretor cadastrado ainda. Clique em "Novo corretor" para começar.
          </div>
        )}
        {!corretoresQ.isPending && !corretoresQ.isError && corretores.length > 0 && (
          <table className="w-full text-sm" data-testid="corretores-table">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                <th className="px-3 py-2">Nome</th>
                <th className="px-3 py-2 text-right">Leads</th>
                <th className="px-3 py-2">Ativo</th>
                <th className="px-3 py-2 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {corretores.map((c) => (
                <tr key={c.id} className="border-b last:border-0" data-testid={`corretor-row-${c.id}`}>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      {c.cor && <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.cor }} />}
                      {c.nome}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{c.lead_count}</td>
                  <td className="px-3 py-2">
                    <Badge variant={c.ativo ? "default" : "outline"}>{c.ativo ? "Ativo" : "Inativo"}</Badge>
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(c)} data-testid={`corretor-edit-${c.id}`}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleteTarget(c)}
                      data-testid={`corretor-delete-${c.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="rounded-lg border border-border p-4">
        <h4 className="mb-2 text-sm font-semibold">Mapa de aliases</h4>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Input
            placeholder="Alias (ex: ALE)"
            value={newAlias}
            onChange={(e) => setNewAlias(e.target.value)}
            className="h-8 w-56 text-sm"
            data-testid="corretor-alias-new-input"
          />
          <Select value={newAliasCorretor} onValueChange={setNewAliasCorretor}>
            <SelectTrigger className="h-8 w-48 text-sm">
              <SelectValue placeholder="Corretor" />
            </SelectTrigger>
            <SelectContent>
              {(corretores ?? []).map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.nome}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            disabled={!newAlias || !newAliasCorretor}
            onClick={() =>
              upsert.mutate(
                { alias: newAlias, corretor_id: newAliasCorretor },
                {
                  onSuccess: () => {
                    toast.success("Alias mapeado.");
                    setNewAlias("");
                    setNewAliasCorretor("");
                  },
                  onError: (err) => toast.error(describeError(err, "Erro ao mapear alias.")),
                },
              )
            }
          >
            Adicionar
          </Button>
        </div>

        {aliasesQ.isPending && (
          <div className="flex flex-wrap gap-1.5" data-testid="corretor-aliases-loading">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} height={22} width={104} rounded="full" announce={i === 0} />
            ))}
          </div>
        )}
        {aliasesQ.isError && (
          <p className="flex items-center gap-1.5 text-xs text-destructive" data-testid="corretor-aliases-error">
            <AlertTriangle className="h-3.5 w-3.5" />
            Erro ao carregar aliases.
            <button
              type="button"
              onClick={() => aliasesQ.refetch()}
              className="underline underline-offset-2 hover:text-destructive/80"
            >
              Tentar novamente
            </button>
          </p>
        )}
        {!aliasesQ.isPending && !aliasesQ.isFetching && !aliasesQ.isError && aliases.length === 0 && (
          <p className="text-xs text-muted-foreground" data-testid="corretor-aliases-empty">
            Nenhum alias mapeado ainda.
          </p>
        )}
        {!aliasesQ.isPending && !aliasesQ.isError && aliases.length > 0 && (
          <div className="flex flex-wrap gap-1.5" data-testid="corretor-aliases-list">
            {aliases.map((a) => (
              <span
                key={a.id}
                className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-0.5 text-xs"
              >
                {a.alias} → {corretores.find((c) => c.id === a.corretor_id)?.nome ?? a.corretor_id}
                <button
                  type="button"
                  onClick={() => removeAlias.mutate(a.id)}
                  aria-label={`Remover alias ${a.alias}`}
                  className="ml-0.5 rounded-full hover:text-destructive"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        <div className="mt-3 border-t border-dashed border-border pt-3">
          {unmappedQ.isPending && (
            <div data-testid="corretores-unmapped-loading">
              <Skeleton height={12} width={140} className="mb-2" />
              <div className="space-y-1.5">
                <Skeleton height={32} announce={false} />
                <Skeleton height={32} announce={false} />
              </div>
            </div>
          )}
          {unmappedQ.isError && (
            <div
              className="flex flex-wrap items-center gap-2 text-xs text-destructive"
              data-testid="corretores-unmapped-error"
            >
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              Erro ao carregar a fila de não mapeados.
              <Button size="sm" variant="outline" onClick={() => unmappedQ.refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}
          {!unmappedQ.isPending && !unmappedQ.isFetching && !unmappedQ.isError && unmapped.length === 0 && (
            <p
              className="flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400"
              data-testid="corretores-unmapped-empty"
            >
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
              Tudo mapeado — nenhum corretor pendente.
            </p>
          )}
          {!unmappedQ.isPending && !unmappedQ.isError && unmapped.length > 0 && (
            <div data-testid="corretores-unmapped-queue">
              <p className="mb-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                Não mapeados ({unmapped.length})
              </p>
              <div className="space-y-1.5">
                {unmapped.map((u) => (
                  <div key={u.alias} className="flex items-center gap-2 text-sm">
                    <span className="w-48 truncate" title={u.alias}>
                      {u.alias}
                    </span>
                    <span className="text-xs text-muted-foreground">({u.count})</span>
                    <Select
                      value={mapTarget[u.alias] ?? ""}
                      onValueChange={(v) => setMapTarget({ ...mapTarget, [u.alias]: v })}
                    >
                      <SelectTrigger className="h-8 w-44 text-xs">
                        <SelectValue placeholder="Mapear para..." />
                      </SelectTrigger>
                      <SelectContent>
                        {corretores.map((c) => (
                          <SelectItem key={c.id} value={c.id}>
                            {c.nome}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!mapTarget[u.alias]}
                      onClick={() =>
                        upsert.mutate(
                          { alias: u.alias, corretor_id: mapTarget[u.alias] },
                          { onSuccess: () => toast.success("Alias mapeado.") },
                        )
                      }
                    >
                      Mapear
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent data-testid="corretor-form-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? "Editar corretor" : "Novo corretor"}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <Label>Nome</Label>
              <Input
                required
                value={form.nome}
                onChange={(e) => setForm({ ...form, nome: e.target.value })}
                data-testid="corretor-form-nome"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Cor</Label>
                <Input
                  type="color"
                  value={form.cor ?? "#6366f1"}
                  onChange={(e) => setForm({ ...form, cor: e.target.value })}
                  className="h-10 p-1"
                  data-testid="corretor-form-cor"
                />
              </div>
              <div className="flex items-center justify-between rounded-md border border-input px-3">
                <Label htmlFor="corretor-ativo">Ativo</Label>
                <Switch
                  id="corretor-ativo"
                  checked={form.ativo ?? true}
                  onCheckedChange={(v) => setForm({ ...form, ativo: v })}
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setFormOpen(false)}>
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={create.isPending || update.isPending}
                data-testid="corretor-form-submit"
              >
                Salvar
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover corretor?</AlertDialogTitle>
            <AlertDialogDescription>
              Se ainda houver leads de <strong>{deleteTarget?.nome}</strong>, escolha um corretor para
              reatribuí-los (opcional).
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Select value={reassignTo} onValueChange={setReassignTo}>
            <SelectTrigger>
              <SelectValue placeholder="Reatribuir para (opcional)" />
            </SelectTrigger>
            <SelectContent>
              {(corretores ?? [])
                .filter((c) => c.id !== deleteTarget?.id)
                .map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.nome}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>Remover</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Configuracao() {
  const [section, setSection] = useState<"origens" | "corretores" | "portais">(
    "origens",
  );

  return (
    <div className="space-y-4" data-testid="leads-config-success">
      <div className="inline-flex rounded-md border border-border bg-muted/30 p-1" role="group">
        <Button
          variant={section === "origens" ? "default" : "ghost"}
          size="sm"
          onClick={() => setSection("origens")}
          data-testid="config-section-origens"
        >
          Origens
        </Button>
        <Button
          variant={section === "corretores" ? "default" : "ghost"}
          size="sm"
          onClick={() => setSection("corretores")}
          data-testid="config-section-corretores"
        >
          Corretores
        </Button>
        <Button
          variant={section === "portais" ? "default" : "ghost"}
          size="sm"
          onClick={() => setSection("portais")}
          data-testid="config-section-portais"
        >
          Portais
        </Button>
      </div>

      {section === "origens" ? (
        <OrigensConfig />
      ) : section === "corretores" ? (
        <CorretoresConfig />
      ) : (
        <div className="space-y-4" data-testid="portais-config">
          <ReceiverTokensCard />
          <OlxWebhookCard />
          {/* A separate card, not a section of the OLX one: different
              vendor, different credentials, different failure modes — and
              an advertiser can be live on both at once. */}
          <ImovelWebWebhookCard />
        </div>
      )}
    </div>
  );
}
