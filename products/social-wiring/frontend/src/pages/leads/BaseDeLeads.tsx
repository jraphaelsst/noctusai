/**
 * BaseDeLeads — "Base de Leads" subtab (§6 of leads-module-PROJECT.md).
 *
 * Paginated sortable table + row-click detail drawer + page-scoped
 * create/edit/delete + a "Revisar" quick-filter toggle for `needs_review`.
 * The sticky filter bar itself is `LeadsFilterBar`, mounted once in
 * `Leads.tsx` above every subtab — this page only reads the shared
 * `useLeadsFilters()` state + adds the needs_review quick-toggle button.
 */
import { useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TableSkeleton } from "@noctusai/lib/design-system";
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
import { leadsFiltersQueryKey, useLeadsFilters } from "@/hooks/useLeadsFilters";
import { useLeadMutations, useLeadsList, type LeadsOrder, type LeadsSort } from "@/hooks/useLeads";
import type { Lead } from "@/pages/leads/types";
import { LeadFormDialog, type LeadFormValues } from "./components/LeadFormDialog";
import { LeadDetailDrawer } from "./components/LeadDetailDrawer";
import { describeError } from "./utils";

const PAGE_SIZE = 25;

const TIPO_VARIANT: Record<Lead["tipo_lead"], "default" | "secondary" | "outline"> = {
  novo: "default",
  retorno: "secondary",
  desconhecido: "outline",
};
const TIPO_LABEL: Record<Lead["tipo_lead"], string> = {
  novo: "Novo",
  retorno: "Retorno",
  desconhecido: "Desconhecido",
};

interface SortHeaderProps {
  label: string;
  field: LeadsSort;
  sort: LeadsSort;
  order: LeadsOrder;
  onSort: (field: LeadsSort) => void;
}

function SortHeader({ label, field, sort, order, onSort }: SortHeaderProps) {
  const active = sort === field;
  const Icon = active ? (order === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className="inline-flex items-center gap-1 font-medium hover:text-foreground"
      data-testid={`leads-sort-${field}`}
    >
      {label}
      <Icon className={`h-3 w-3 ${active ? "" : "opacity-40"}`} />
    </button>
  );
}

export default function BaseDeLeads() {
  const { filters, setNeedsReview } = useLeadsFilters();
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<LeadsSort>("data_entrada");
  const [order, setOrder] = useState<LeadsOrder>("desc");
  const [formOpen, setFormOpen] = useState(false);
  const [editingLead, setEditingLead] = useState<Lead | null>(null);
  const [detailLead, setDetailLead] = useState<Lead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Lead | null>(null);

  // A filter change (drill-in click, search, date range, ...) invalidates
  // whatever page number was in scroll — without this, staying on e.g. page
  // 40 of a narrower result set renders the empty-state "Nenhum lead
  // encontrado" even though the filtered leads DO exist, just on an earlier
  // page (leads-p0-frontend-ux finding #5).
  const filtersKey = leadsFiltersQueryKey(filters);
  useEffect(() => {
    setPage(1);
  }, [filtersKey]);

  const { data, isPending, isFetching, isError, error } = useLeadsList(filters, {
    page,
    pageSize: PAGE_SIZE,
    sort,
    order,
  });
  const { create, update, remove } = useLeadMutations();

  const leads = data?.data ?? [];
  const total = data?.pagination?.total ?? 0;
  const totalPages = data?.pagination?.total_pages ?? 1;

  function handleSort(field: LeadsSort) {
    if (field === sort) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(field);
      setOrder("desc");
    }
    setPage(1);
  }

  function openCreate() {
    setEditingLead(null);
    setFormOpen(true);
  }

  function openEditFromDrawer(lead: Lead) {
    setDetailLead(null);
    setEditingLead(lead);
    setFormOpen(true);
  }

  function handleSubmit(values: LeadFormValues) {
    if (editingLead) {
      update.mutate(
        { id: editingLead.id, body: values },
        {
          onSuccess: () => {
            toast.success("Lead atualizado.");
            setFormOpen(false);
          },
          onError: (err) => toast.error(describeError(err, "Erro ao atualizar lead.")),
        },
      );
    } else {
      create.mutate(values, {
        onSuccess: () => {
          toast.success("Lead criado.");
          setFormOpen(false);
        },
        onError: (err) => toast.error(describeError(err, "Erro ao criar lead.")),
      });
    }
  }

  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Lead removido.");
        setDeleteTarget(null);
        setDetailLead(null);
      },
      onError: (err) => toast.error(describeError(err, "Erro ao remover lead.")),
    });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          variant={filters.needs_review === true ? "default" : "outline"}
          size="sm"
          onClick={() => setNeedsReview(filters.needs_review === true ? null : true)}
          data-testid="leads-revisar-toggle"
        >
          <AlertCircle className="mr-2 h-4 w-4" />
          Revisar
        </Button>
        <Button onClick={openCreate} className="gap-2" data-testid="leads-btn-novo">
          <Plus className="h-4 w-4" />
          Novo lead
        </Button>
      </div>

      {isPending && (
        <Card data-testid="leads-table-loading">
          <CardContent className="p-0">
            <TableSkeleton rows={8} columns={6} />
          </CardContent>
        </Card>
      )}

      {isError && (
        <Card className="border-destructive" data-testid="leads-table-error">
          <CardContent className="flex items-center gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <p className="text-sm text-destructive">
              Erro ao carregar leads:{" "}
              {((error as Error)?.message ?? "").replace(/^\[\d+\]\s*/, "") || "Tente novamente."}
            </p>
          </CardContent>
        </Card>
      )}

      {!isPending && !isFetching && !isError && leads.length === 0 && (
        <Card data-testid="leads-table-empty">
          <CardHeader>
            <CardTitle className="text-base">Nenhum lead encontrado</CardTitle>
            <CardDescription>
              {filters.needs_review || filters.q
                ? "Nenhum lead com esses filtros. Tente outros critérios."
                : "Nenhum lead importado ainda — use a aba Importação ou crie um manualmente."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {!isPending && !isError && leads.length > 0 && (
        <Card data-testid="leads-table">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-left text-muted-foreground">
                    <th className="px-4 py-3">
                      <SortHeader label="Data" field="data_entrada" sort={sort} order={order} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3">
                      <SortHeader label="Cliente" field="cliente_nome" sort={sort} order={order} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3">
                      <SortHeader label="Origem" field="origem" sort={sort} order={order} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3">
                      <SortHeader label="Corretor" field="corretor" sort={sort} order={order} onSort={handleSort} />
                    </th>
                    <th className="px-4 py-3">Tipo</th>
                    <th className="px-4 py-3">Revisar</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr
                      key={lead.id}
                      className="cursor-pointer border-b last:border-0 hover:bg-muted/30"
                      onClick={() => setDetailLead(lead)}
                      data-testid={`lead-row-${lead.id}`}
                    >
                      <td className="px-4 py-3 whitespace-nowrap">{lead.data_entrada}</td>
                      <td className="px-4 py-3">
                        <span className="font-medium">
                          {lead.cliente_nome || <span className="text-muted-foreground">—</span>}
                        </span>
                        <p className="text-xs text-muted-foreground">{lead.contato ?? "—"}</p>
                      </td>
                      <td className="px-4 py-3">
                        {lead.origem ? (
                          <span className="inline-flex items-center gap-1.5">
                            {lead.origem.cor && (
                              <span
                                className="h-2.5 w-2.5 rounded-full"
                                style={{ backgroundColor: lead.origem.cor }}
                              />
                            )}
                            {lead.origem.label}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">{lead.origem_raw ?? "—"}</span>
                        )}
                      </td>
                      <td className="px-4 py-3">{lead.corretor?.nome ?? lead.corretor_raw ?? "—"}</td>
                      <td className="px-4 py-3">
                        <Badge variant={TIPO_VARIANT[lead.tipo_lead]}>{TIPO_LABEL[lead.tipo_lead]}</Badge>
                      </td>
                      <td className="px-4 py-3">
                        {lead.needs_review && <Badge variant="destructive">Revisar</Badge>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {total > PAGE_SIZE && (
              <div className="flex items-center justify-between border-t px-4 py-3" data-testid="leads-pagination">
                <p className="text-sm text-muted-foreground">
                  Página {page} de {totalPages} ({total} leads)
                </p>
                <div className="flex gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page === 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <LeadDetailDrawer
        lead={detailLead}
        onOpenChange={(open) => !open && setDetailLead(null)}
        onEdit={openEditFromDrawer}
        onDelete={(lead) => setDeleteTarget(lead)}
      />

      <LeadFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        lead={editingLead}
        onSubmit={handleSubmit}
        isPending={create.isPending || update.isPending}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover lead?</AlertDialogTitle>
            <AlertDialogDescription>
              O lead de <strong>{deleteTarget?.cliente_nome || deleteTarget?.contato || deleteTarget?.id}</strong>{" "}
              será removido permanentemente.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="lead-confirm-delete"
            >
              {remove.isPending ? "Removendo..." : "Remover"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
