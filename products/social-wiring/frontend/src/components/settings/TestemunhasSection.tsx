/**
 * `<TestemunhasSection/>` — the imobiliária's up-to-two standing witnesses,
 * reused in every contract's signature block.
 *
 * A sibling Card to `DadosImobiliariaTab` on the Settings "Imobiliária" tab,
 * not a merge into it: a different resource, a different hook, a different
 * lifecycle (add/edit/delete rows vs. one form with a single Save).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";

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

import {
  useCreateTestemunha,
  useDeleteTestemunha,
  useTestemunhas,
  useUpdateTestemunha,
  type Testemunha,
  type TestemunhaCreate,
} from "@/hooks/useTestemunhas";

const MAX_TESTEMUNHAS = 2;

interface Draft {
  nome: string;
  cpf: string;
  rg: string;
}

const EMPTY_DRAFT: Draft = { nome: "", cpf: "", rg: "" };

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

  // 🔴 Two signals, never `isLoading`. → KB § PATTERNS/frontend/lying-loading-state.md
  const showSkeleton = query.isPending && !query.data;
  const isRefreshing = query.isFetching && !!query.data;
  const items = query.data?.items ?? [];
  const noLimite = items.length >= MAX_TESTEMUNHAS;

  function abrirNova() {
    setEditando(null);
    setDraft(EMPTY_DRAFT);
    setOpen(true);
  }

  function abrirEdicao(t: Testemunha) {
    setEditando(t);
    setDraft({ nome: t.nome, cpf: t.cpf ?? "", rg: t.rg ?? "" });
    setOpen(true);
  }

  function submit() {
    const payload: TestemunhaCreate = {
      nome: draft.nome.trim(),
      cpf: draft.cpf.trim() || null,
      rg: draft.rg.trim() || null,
    };
    const onSuccess = () => {
      setOpen(false);
      toast.success(
        editando ? "Testemunha atualizada." : "Testemunha adicionada.",
      );
    };
    const onError = (err: unknown) =>
      toast.error(errorMessage(err, "Não foi possível salvar a testemunha."));

    if (editando) {
      atualizar.mutate({ id: editando.id, patch: payload }, { onSuccess, onError });
    } else {
      criar.mutate(payload, { onSuccess, onError });
    }
  }

  function remover(t: Testemunha) {
    excluir.mutate(t.id, {
      onError: (err) =>
        toast.error(errorMessage(err, "Não foi possível remover a testemunha.")),
    });
  }

  const salvando = criar.isPending || atualizar.isPending;

  return (
    <Card data-testid="testemunhas-section">
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle>Testemunhas</CardTitle>
          <CardDescription>
            Até {MAX_TESTEMUNHAS} testemunhas padrão para os blocos de
            assinatura dos contratos.
          </CardDescription>
        </div>
        <Button
          size="sm"
          onClick={abrirNova}
          disabled={noLimite}
          title={noLimite ? `Máximo de ${MAX_TESTEMUNHAS} testemunhas` : undefined}
          data-testid="testemunha-nova"
        >
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
                  <p className="text-sm font-medium">{t.nome}</p>
                  <p className="text-xs text-muted-foreground">
                    {[t.cpf, t.rg].filter(Boolean).join(" · ") || "—"}
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
                    onClick={() => remover(t)}
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
                <Label htmlFor="test-cpf">CPF</Label>
                <Input
                  id="test-cpf"
                  value={draft.cpf}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, cpf: e.target.value }))
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="test-rg">RG</Label>
                <Input
                  id="test-rg"
                  value={draft.rg}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, rg: e.target.value }))
                  }
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={submit}
              disabled={!draft.nome.trim() || salvando}
              data-testid="testemunha-salvar"
            >
              {salvando ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
