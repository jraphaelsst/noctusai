/**
 * Julia › Equipe (`/julia/equipe-whatsapp`): THE per-org staff list of the WhatsApp lines (owner 2026-10-21: "staff will be set in-org.
 * only those registered on the sw are staff and their roles ... by default, if not in the staff list, it's an incoming lead").
 *
 * A number on this list is a colleague (never a lead); the role decides the route (admin / operador drive the One Chat agent from their
 * number; the others are noticed to the admins). Everything else that writes to a Julia line is a lead. Org-admin only.
 *
 * Loading = two signals off `data` (never `isLoading`); removal asks in a design-system AlertDialog, never a browser dialog.
 */
import { useState } from "react";
import { AlertCircle, Loader2, Pencil, Plus, Trash2, Users } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { MembroDialog } from "@/components/julia/equipe/MembroDialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  EXPLICACAO_PAPEL, ROTULO_PAPEL, formatarTelefone, useAtualizarMembro, useCriarMembro, useEquipeWhatsapp, useRemoverMembro,
  useUsuariosDaOrg, type MembroEntrada, type MembroEquipe,
} from "@/hooks/useJuliaEquipeWhatsapp";
import { mensagemErroServidor } from "@/lib/erroServidor";

export default function JuliaEquipeWhatsapp() {
  const isAdmin = useIsOrgAdmin();
  const q = useEquipeWhatsapp(isAdmin);
  const usuarios = useUsuariosDaOrg(isAdmin);
  const criar = useCriarMembro();
  const atualizar = useAtualizarMembro();
  const remover = useRemoverMembro();
  const [editando, setEditando] = useState<MembroEquipe | "novo" | null>(null);
  const [removendo, setRemovendo] = useState<MembroEquipe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [erroRemocao, setErroRemocao] = useState<string | null>(null);

  function salvar(corpo: MembroEntrada) {
    setErro(null);
    const ok = () => { setEditando(null); toast.success("Equipe atualizada."); };
    const falha = (e: unknown) => setErro(mensagemErroServidor(e, "Não foi possível salvar."));
    if (editando && editando !== "novo") atualizar.mutate({ id: editando.id, campos: corpo }, { onSuccess: ok, onError: falha });
    else criar.mutate(corpo, { onSuccess: ok, onError: falha });
  }
  function alternarAtivo(m: MembroEquipe) {
    atualizar.mutate({ id: m.id, campos: { ativo: !m.ativo } }, {
      onSuccess: () => toast.success(m.ativo ? "Membro desativado: o próximo contato dele é tratado como lead." : "Membro reativado."),
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível alterar o membro.")),
    });
  }
  function confirmarRemocao() {
    if (!removendo) return;
    setErroRemocao(null);
    remover.mutate({ id: removendo.id }, {
      onSuccess: () => { setRemovendo(null); toast.success("Membro removido: o próximo contato dele é tratado como lead."); },
      onError: (e) => setErroRemocao(mensagemErroServidor(e, "Não foi possível remover.")),
    });
  }

  return (
    <div className="container max-w-4xl space-y-5 py-6">
      <header className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">Equipe do WhatsApp</h1>
          <p className="text-sm text-muted-foreground">
            Quem é da equipe nas linhas da organização. Só os números cadastrados aqui são equipe; qualquer outro número que escreva
            para a linha pública é um lead, sempre.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => { setErro(null); setEditando("novo"); }} data-testid="equipe-adicionar">
            <Plus className="mr-1 h-4 w-4" /> Adicionar
          </Button>
        )}
      </header>

      {!isAdmin && (
        <p className="rounded-md border border-warning/40 bg-warning-light px-3 py-2 text-sm text-warning-foreground" data-testid="equipe-sem-permissao">
          Somente owner ou admin da organização vê e edita a equipe.
        </p>
      )}

      {isAdmin && q.showSkeleton && <div className="h-48 animate-pulse rounded-lg bg-muted" data-testid="equipe-skeleton" />}
      {isAdmin && q.isError && !q.data && (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="equipe-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">{mensagemErroServidor(q.error, "Não foi possível carregar a equipe.")}</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>Tentar de novo</Button>
        </div>
      )}
      {isAdmin && q.data && q.data.items.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed py-16 text-center" data-testid="equipe-vazia">
          <Users className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhum membro cadastrado: todos os números que escrevem são tratados como leads.</p>
        </div>
      )}
      {isAdmin && q.data && q.data.items.length > 0 && (
        <div className="space-y-2">
          {q.isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="equipe-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <ul className="space-y-2" data-testid="equipe-lista">
            {q.data.items.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 rounded-md border p-3" data-testid="equipe-item">
                <div className="min-w-0 space-y-0.5">
                  <p className="truncate font-medium">
                    {m.nome}
                    {!m.ativo && <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs font-normal" data-testid="equipe-inativo">inativo</span>}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    <span data-testid="equipe-papel">{ROTULO_PAPEL[m.papel]}</span> · {formatarTelefone(m.telefone)}
                  </p>
                  <p className="text-xs text-muted-foreground">{EXPLICACAO_PAPEL[m.papel]}</p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button variant="outline" size="sm" onClick={() => alternarAtivo(m)} disabled={atualizar.isPending} data-testid="equipe-alternar">
                    {m.ativo ? "Desativar" : "Reativar"}
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Editar ${m.nome}`} onClick={() => { setErro(null); setEditando(m); }} data-testid="equipe-editar">
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" aria-label={`Remover ${m.nome}`} onClick={() => { setErroRemocao(null); setRemovendo(m); }} data-testid="equipe-remover">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {editando !== null && q.data && (
        <MembroDialog
          key={editando === "novo" ? "novo" : editando.id}
          aberto membro={editando === "novo" ? null : editando} papeis={q.data.papeis} usuarios={usuarios.data ?? []}
          pendente={criar.isPending || atualizar.isPending} erro={erro} onSalvar={salvar} onFechar={() => setEditando(null)}
        />
      )}

      <AlertDialog open={removendo !== null} onOpenChange={(o) => { if (!o && !remover.isPending) setRemovendo(null); }}>
        <AlertDialogContent data-testid="equipe-remover-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Remover {removendo?.nome} da equipe?</AlertDialogTitle>
            <AlertDialogDescription>
              Depois de removido, o próximo contato desse número com a linha pública é tratado como lead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {erroRemocao && <p role="alert" className="text-sm text-destructive" data-testid="equipe-remover-erro">{erroRemocao}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remover.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); confirmarRemocao(); }} disabled={remover.isPending} data-testid="equipe-remover-confirmar"
            >
              {remover.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
