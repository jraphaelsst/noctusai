/**
 * CampanhaManagerDialog — the spend-entry surface for ONE portal (`origem`).
 * Owns full page-scoped CRUD over that origem's `lead_campanhas` rows
 * (PROJECT.md §3.3 / §3.5): a "list" view (every period recorded for this
 * origem, with edit/delete) and a "form" view (create or edit one period).
 *
 * There is no portal API — the operator reads these numbers off each
 * portal's own dashboard and types them in, which is why this dialog opens
 * from BOTH "registrar investimento" (a portal with leads and no spend —
 * 23 of 24 rows on day one) and "editar" (a portal that already has entries).
 *
 * 409 handling (duplicate `(origem_id, periodo_inicio, periodo_fim)`):
 * resolved client-side against the campanha list this dialog already holds
 * for the origem (see `findConflictingCampanha` in `usePortalRoi.ts`) —
 * both as a pre-submit guard and as the true-409 fallback — rather than by
 * parsing an unpinned error-body shape. Either path lands on the same
 * "atualizar o lançamento existente?" prompt so the operator is never
 * dead-ended (contract requirement).
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";

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
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import {
  findConflictingCampanha,
  formatDateBR,
  formatMoneyOrNaoInformado,
  isConflictError,
  usePortalRoiCampanhaMutations,
  usePortalRoiCampanhas,
  type CampanhaRow,
  type CampanhaWritableFields,
} from "@/hooks/usePortalRoi";

function describeMutationError(err: unknown, fallback: string): string {
  const message = err instanceof Error ? err.message : "";
  const decoded = message.replace(/^\[\d+\]\s*/, "").trim();
  return decoded ? `${fallback} ${decoded}` : fallback;
}

interface FormValues {
  periodo_inicio: string;
  periodo_fim: string;
  investimento: string;
  impressoes: string;
  cliques: string;
  leads: string;
  visitas_perfil: string;
  engajamento: string;
  observacoes: string;
}

function emptyForm(): FormValues {
  return {
    periodo_inicio: "",
    periodo_fim: "",
    investimento: "",
    impressoes: "",
    cliques: "",
    leads: "",
    visitas_perfil: "",
    engajamento: "",
    observacoes: "",
  };
}

function fromCampanha(c: CampanhaRow): FormValues {
  return {
    periodo_inicio: c.periodo_inicio,
    periodo_fim: c.periodo_fim,
    investimento: String(c.investimento),
    impressoes: c.impressoes === null ? "" : String(c.impressoes),
    cliques: c.cliques === null ? "" : String(c.cliques),
    leads: c.leads === null ? "" : String(c.leads),
    visitas_perfil: c.visitas_perfil === null ? "" : String(c.visitas_perfil),
    engajamento: c.engajamento === null ? "" : String(c.engajamento),
    observacoes: c.observacoes ?? "",
  };
}

function toNullableInt(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function toPayload(origemId: string, form: FormValues): CampanhaWritableFields {
  return {
    origem_id: origemId,
    periodo_inicio: form.periodo_inicio,
    periodo_fim: form.periodo_fim,
    investimento: Number(form.investimento) || 0,
    impressoes: toNullableInt(form.impressoes),
    cliques: toNullableInt(form.cliques),
    leads: toNullableInt(form.leads),
    visitas_perfil: toNullableInt(form.visitas_perfil),
    engajamento: toNullableInt(form.engajamento),
    observacoes: form.observacoes.trim() === "" ? null : form.observacoes,
  };
}

/** Client-side mirror of the two 422 rules the contract names (§3.3) —
 * catches the common typo before a round trip, not a replacement for the
 * backend's own validation. */
function validate(form: FormValues): string | null {
  if (!form.periodo_inicio || !form.periodo_fim) return "Informe o período (início e fim).";
  if (form.periodo_fim < form.periodo_inicio) return "O fim do período não pode ser anterior ao início.";
  const investimento = Number(form.investimento);
  if (form.investimento.trim() === "" || Number.isNaN(investimento)) return "Informe o investimento.";
  if (investimento < 0) return "O investimento não pode ser negativo.";
  return null;
}

export interface CampanhaManagerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  origemId: string;
  origemLabel: string;
}

export function CampanhaManagerDialog({
  open,
  onOpenChange,
  origemId,
  origemLabel,
}: CampanhaManagerDialogProps) {
  const [view, setView] = useState<"list" | "form">("list");
  const [editing, setEditing] = useState<CampanhaRow | null>(null);
  const [conflict, setConflict] = useState<CampanhaRow | null>(null);
  const [form, setForm] = useState<FormValues>(emptyForm());
  const [deleteTarget, setDeleteTarget] = useState<CampanhaRow | null>(null);

  const campanhas = usePortalRoiCampanhas({ origem_id: origemId }, { enabled: open });
  const { create, update, remove } = usePortalRoiCampanhaMutations();

  useEffect(() => {
    if (open) {
      setView("list");
      setEditing(null);
      setConflict(null);
      setForm(emptyForm());
    }
  }, [open]);

  const rows = campanhas.data ?? [];
  const isPending = create.isPending || update.isPending;

  function openCreate() {
    setEditing(null);
    setConflict(null);
    setForm(emptyForm());
    setView("form");
  }

  function openEdit(row: CampanhaRow) {
    setEditing(row);
    setConflict(null);
    setForm(fromCampanha(row));
    setView("form");
  }

  function useConflictAsEditTarget() {
    if (!conflict) return;
    setEditing(conflict);
    setForm((f) => ({ ...f, periodo_inicio: conflict.periodo_inicio, periodo_fim: conflict.periodo_fim }));
    setConflict(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const validationError = validate(form);
    if (validationError) {
      toast.error(validationError);
      return;
    }

    const existing = findConflictingCampanha(rows, form, editing?.id);
    if (existing) {
      // Never dead-end: offer to update the row that already covers this
      // period instead of firing a request we already know will 409.
      setConflict(existing);
      return;
    }

    const payload = toPayload(origemId, form);
    if (editing) {
      update.mutate(
        { id: editing.id, body: payload },
        {
          onSuccess: () => {
            toast.success("Lançamento atualizado.");
            setView("list");
          },
          onError: (err) => {
            if (isConflictError(err)) {
              campanhas.refetch().then((r) => {
                const found = findConflictingCampanha(r.data ?? [], form, editing.id);
                if (found) setConflict(found);
                else toast.error(describeMutationError(err, "Erro ao atualizar lançamento."));
              });
              return;
            }
            toast.error(describeMutationError(err, "Erro ao atualizar lançamento."));
          },
        },
      );
    } else {
      create.mutate(payload, {
        onSuccess: () => {
          toast.success("Investimento registrado.");
          setView("list");
        },
        onError: (err) => {
          if (isConflictError(err)) {
            // A write raced in between our pre-submit check and this
            // request — refetch and resolve the same way.
            campanhas.refetch().then((r) => {
              const found = findConflictingCampanha(r.data ?? [], form);
              if (found) setConflict(found);
              else toast.error(describeMutationError(err, "Erro ao registrar investimento."));
            });
            return;
          }
          toast.error(describeMutationError(err, "Erro ao registrar investimento."));
        },
      });
    }
  }

  function handleDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success("Lançamento removido.");
        setDeleteTarget(null);
      },
      onError: (err) => {
        toast.error(describeMutationError(err, "Erro ao remover lançamento."));
        setDeleteTarget(null);
      },
    });
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className="max-h-[85vh] max-w-2xl overflow-y-auto"
          data-testid="campanha-manager-dialog"
        >
          <DialogHeader>
            <DialogTitle>
              {view === "list"
                ? `Lançamentos — ${origemLabel}`
                : editing
                  ? `Editar lançamento — ${origemLabel}`
                  : `Registrar investimento — ${origemLabel}`}
            </DialogTitle>
          </DialogHeader>

          {view === "list" ? (
            <div className="space-y-4 pt-2">
              {/* First-load only. Every save/delete in this dialog
                  invalidates `campanhas`, and `rows` always defaults to `[]`
                  via `?? []` — gate on the RAW `campanhas.data` (undefined
                  until the first successful fetch) so the table stays
                  mounted through every background refetch instead of
                  vanishing back to "Carregando…" after each save.
                  (KB § PATTERNS/frontend/lying-loading-state.md) */}
              {campanhas.isPending && !campanhas.data ? (
                <p className="py-8 text-center text-sm text-muted-foreground">Carregando…</p>
              ) : rows.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Nenhum lançamento registrado para este portal ainda.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-md border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
                        <th className="px-3 py-2 font-medium">Período</th>
                        <th className="px-3 py-2 font-medium">Investimento</th>
                        <th className="px-3 py-2 font-medium">CPL</th>
                        <th className="px-3 py-2 font-medium" />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((c) => (
                        <tr key={c.id} className="border-b last:border-0" data-testid="campanha-row">
                          <td className="px-3 py-2">
                            {formatDateBR(c.periodo_inicio)} – {formatDateBR(c.periodo_fim)}
                          </td>
                          <td className="px-3 py-2">{formatMoneyOrNaoInformado(c.investimento)}</td>
                          <td className="px-3 py-2">{formatMoneyOrNaoInformado(c.cpl)}</td>
                          <td className="px-3 py-2 text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEdit(c)}
                              data-testid="campanha-edit-btn"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setDeleteTarget(c)}
                              data-testid="campanha-delete-btn"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <DialogFooter className="sm:justify-between">
                <Button variant="outline" onClick={openCreate} data-testid="campanha-new-period-btn">
                  <Plus className="mr-2 h-4 w-4" />
                  Novo período
                </Button>
                <Button variant="ghost" onClick={() => onOpenChange(false)}>
                  Fechar
                </Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4 pt-2">
              {conflict && (
                <div
                  className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm"
                  data-testid="campanha-conflict-banner"
                >
                  <p>
                    Já existe um lançamento para{" "}
                    <strong>
                      {formatDateBR(conflict.periodo_inicio)} – {formatDateBR(conflict.periodo_fim)}
                    </strong>{" "}
                    ({formatMoneyOrNaoInformado(conflict.investimento)}). Um mesmo período não pode
                    ser lançado duas vezes.
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    className="mt-2"
                    onClick={useConflictAsEditTarget}
                    data-testid="campanha-use-conflict-btn"
                  >
                    Atualizar o lançamento existente
                  </Button>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-inicio">Início do período</Label>
                  <Input
                    id="campanha-inicio"
                    type="date"
                    required
                    value={form.periodo_inicio}
                    onChange={(e) => setForm({ ...form, periodo_inicio: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-periodo-inicio"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-fim">Fim do período</Label>
                  <Input
                    id="campanha-fim"
                    type="date"
                    required
                    value={form.periodo_fim}
                    onChange={(e) => setForm({ ...form, periodo_fim: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-periodo-fim"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="campanha-investimento">Investimento (R$)</Label>
                <Input
                  id="campanha-investimento"
                  type="number"
                  min={0}
                  step="0.01"
                  required
                  value={form.investimento}
                  onChange={(e) => setForm({ ...form, investimento: e.target.value })}
                  disabled={isPending}
                  data-testid="campanha-form-investimento"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-impressoes">Impressões</Label>
                  <Input
                    id="campanha-impressoes"
                    type="number"
                    min={0}
                    value={form.impressoes}
                    onChange={(e) => setForm({ ...form, impressoes: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-impressoes"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-cliques">Cliques</Label>
                  <Input
                    id="campanha-cliques"
                    type="number"
                    min={0}
                    value={form.cliques}
                    onChange={(e) => setForm({ ...form, cliques: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-cliques"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-leads">Leads</Label>
                  <Input
                    id="campanha-leads"
                    type="number"
                    min={0}
                    value={form.leads}
                    onChange={(e) => setForm({ ...form, leads: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-leads"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-visitas">Visitas ao perfil</Label>
                  <Input
                    id="campanha-visitas"
                    type="number"
                    min={0}
                    value={form.visitas_perfil}
                    onChange={(e) => setForm({ ...form, visitas_perfil: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-visitas"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="campanha-engajamento">Engajamento</Label>
                  <Input
                    id="campanha-engajamento"
                    type="number"
                    min={0}
                    value={form.engajamento}
                    onChange={(e) => setForm({ ...form, engajamento: e.target.value })}
                    disabled={isPending}
                    data-testid="campanha-form-engajamento"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="campanha-observacoes">Observações</Label>
                <Textarea
                  id="campanha-observacoes"
                  value={form.observacoes}
                  onChange={(e) => setForm({ ...form, observacoes: e.target.value })}
                  disabled={isPending}
                  data-testid="campanha-form-observacoes"
                />
              </div>

              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => (rows.length > 0 ? setView("list") : onOpenChange(false))}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={isPending} data-testid="campanha-form-submit">
                  {isPending ? "Salvando…" : "Salvar"}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover lançamento?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget &&
                `O período ${formatDateBR(deleteTarget.periodo_inicio)} – ${formatDateBR(deleteTarget.periodo_fim)} (${formatMoneyOrNaoInformado(deleteTarget.investimento)}) será removido. Essa ação não pode ser desfeita.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} data-testid="campanha-confirm-delete-btn">
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
