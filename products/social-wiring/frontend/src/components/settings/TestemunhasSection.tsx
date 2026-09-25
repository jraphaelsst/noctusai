/**
 * `<TestemunhasSection/>` — the imobiliária's REGISTRY of signature
 * witnesses (migration 168 opened up migration 108's fixed pair). A
 * contract selects a subset of this registry per card — see
 * `hooks/useContratoTestemunhas.ts`.
 *
 * A sibling Card to `DadosImobiliariaTab` on the Settings "Imobiliária" tab,
 * not a merge into it: a different resource, a different hook, a different
 * lifecycle (add/edit/delete rows vs. one form with a single Save). Also
 * mounted standalone on `pages/Testemunhas.tsx` — this component owns all
 * the CRUD logic either way, never duplicated.
 *
 * [Owner decision, migration 168] CPF is now REQUIRED — the contract prints
 * CPF instead of RG, so RG is no longer collected here at all. The 2 rows
 * migration 108 shipped (RG + e-mail, no CPF) are KEPT and listed, flagged
 * "CPF pendente" — not selectable for a contract until an operator adds one
 * via Editar.
 */
import { useState } from "react";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { formatarDocumento } from "@/lib/utils";
import {
  useCreateTestemunha,
  useDeleteTestemunha,
  useTestemunhas,
  useUpdateTestemunha,
  type Testemunha,
  type TestemunhaCreate,
} from "@/hooks/useTestemunhas";

interface Draft {
  nome: string;
  cpf: string;
  celular: string;
  email: string;
}

const EMPTY_DRAFT: Draft = { nome: "", cpf: "", celular: "", email: "" };

function errorMessage(err: unknown, fallback: string): string {
  return (err as { message?: string } | null)?.message ?? fallback;
}

export function TestemunhasSection() {
  const query = useTestemunhas();
  const criar = useCreateTestemunha();
  const atualizar = useUpdateTestemunha();
  const excluir = useDeleteTestemunha();

  const [open, setOpen] = useState(false);
  const [editando, setEditando] = useState<Testemunha | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [removendo, setRemovendo] = useState<Testemunha | null>(null);

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const items = query.data?.items ?? [];

  function abrirNova() {
    setEditando(null);
    setDraft(EMPTY_DRAFT);
    setOpen(true);
  }

  function abrirEdicao(t: Testemunha) {
    setEditando(t);
    setDraft({
      nome: t.nome,
      cpf: t.cpf ?? "",
      celular: t.celular ?? "",
      email: t.email ?? "",
    });
    setOpen(true);
  }

  function submit() {
    const onSuccess = () => {
      setOpen(false);
      toast.success(
        editando ? "Testemunha atualizada." : "Testemunha adicionada.",
      );
    };
    const onError = (err: unknown) =>
      toast.error(errorMessage(err, "Não foi possível salvar a testemunha."));

    if (editando) {
      // PATCH: cpf stays whatever was typed — allows a legacy "CPF
      // pendente" row to finally get one without resending every field.
      atualizar.mutate(
        {
          id: editando.id,
          patch: {
            nome: draft.nome.trim(),
            cpf: draft.cpf.trim() || null,
            celular: draft.celular.trim() || null,
            email: draft.email.trim() || null,
          },
        },
        { onSuccess, onError },
      );
    } else {
      // CREATE: cpf is required (migration 168) — the Salvar button is
      // disabled until it is non-empty, and the server re-validates mod-11.
      const payload: TestemunhaCreate = {
        nome: draft.nome.trim(),
        cpf: draft.cpf.trim(),
        celular: draft.celular.trim() || null,
        email: draft.email.trim() || null,
      };
      criar.mutate(payload, { onSuccess, onError });
    }
  }

  function remover(t: Testemunha) {
    excluir.mutate(t.id, {
      onSuccess: () => setRemovendo(null),
      onError: (err) =>
        toast.error(errorMessage(err, "Não foi possível remover a testemunha.")),
    });
  }

  const salvando = criar.isPending || atualizar.isPending;
  // CREATE always needs a CPF; EDIT may be clearing/keeping one field at a
  // time (e.g. adding a CPF to a legacy row) so only nome is required there.
  const podeSalvar = editando
    ? !!draft.nome.trim()
    : !!draft.nome.trim() && !!draft.cpf.trim();

  return (
    <Card data-testid="testemunhas-section">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Testemunhas</CardTitle>
          <CardDescription>
            Testemunhas cadastradas pela imobiliária. Cada contrato escolhe
            quais delas assinam, na aba Contratos do card.
          </CardDescription>
        </div>
        <Button size="sm" onClick={abrirNova} data-testid="testemunha-nova">
          <Plus className="mr-1 h-4 w-4" />
          Nova testemunha
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {isRefreshing && (
          <p
            className="text-xs text-muted-foreground"
            data-testid="testemunhas-refreshing"
          >
            Atualizando…
          </p>
        )}
        {showSkeleton ? (
          <p className="text-sm text-muted-foreground">Carregando…</p>
        ) : query.isError ? (
          <p className="text-sm text-destructive">
            Não foi possível carregar as testemunhas.
          </p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhuma testemunha cadastrada.
          </p>
        ) : (
          <div className="space-y-2">
            {items.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-md border p-3"
                data-testid={`testemunha-${t.id}`}
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-medium">{t.nome}</p>
                    {t.cpf_pendente && (
                      <Badge variant="outline" className="text-[10px] text-amber-700" data-testid={`testemunha-cpf-pendente-${t.id}`}>
                        CPF pendente
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {[t.cpf ? formatarDocumento(t.cpf) : null, t.celular, t.email]
                      .filter(Boolean)
                      .join(" · ") || "—"}
                  </p>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => abrirEdicao(t)}
                    aria-label={`Editar ${t.nome}`}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setRemovendo(t)}
                    aria-label={`Remover ${t.nome}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editando ? "Editar testemunha" : "Nova testemunha"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="test-nome">Nome</Label>
              <Input
                id="test-nome"
                value={draft.nome}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, nome: e.target.value }))
                }
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="test-cpf">
                  CPF{!editando && <span className="text-destructive"> *</span>}
                </Label>
                <Input
                  id="test-cpf"
                  value={draft.cpf}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, cpf: e.target.value }))
                  }
                  data-testid="testemunha-cpf-input"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="test-celular">Celular</Label>
                <Input
                  id="test-celular"
                  value={draft.celular}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, celular: e.target.value }))
                  }
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="test-email">E-mail</Label>
              <Input
                id="test-email"
                type="email"
                value={draft.email}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, email: e.target.value }))
                }
              />
              <p className="text-xs text-muted-foreground">
                Opcional — necessário apenas para enviar esta testemunha para
                assinatura digital.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={submit}
              disabled={!podeSalvar || salvando}
              data-testid="testemunha-salvar"
            >
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!removendo} onOpenChange={(o) => !o && setRemovendo(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover testemunha</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja remover {removendo?.nome} do cadastro? Ela
              deixa de aparecer para novos contratos.
              {removendo && removendo.contratos_em_uso > 0 && (
                <span
                  className="mt-2 block font-medium text-amber-700"
                  data-testid="testemunha-remover-em-uso"
                >
                  Atenção: {removendo.contratos_em_uso === 1
                    ? "1 contrato usa esta testemunha"
                    : `${removendo.contratos_em_uso} contratos usam esta testemunha`}
                  . Esses contratos não são alterados e continuam com ela.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => removendo && remover(removendo)}
              className="bg-destructive hover:bg-destructive/90"
              data-testid="testemunha-confirmar-remover"
            >
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
