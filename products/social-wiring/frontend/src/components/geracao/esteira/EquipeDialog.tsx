/** Equipe (§5.2/§6.1): list, add, deactivate/reactivate the members shown on cards. */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAtualizarMembro, useCriarMembro, useEquipe } from "@/hooks/geracao/useEsteira";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function EquipeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const equipe = useEquipe(true);
  const criar = useCriarMembro();
  const atualizar = useAtualizarMembro();
  const [nome, setNome] = useState("");
  const [funcao, setFuncao] = useState("");

  function adicionar() {
    criar.mutate(
      { nome: nome.trim(), funcao: funcao.trim() || undefined },
      {
        onSuccess: () => {
          setNome("");
          setFuncao("");
        },
        onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível adicionar o membro.")),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Equipe</DialogTitle>
        </DialogHeader>
        {equipe.showSkeleton ? (
          <Skeleton className="h-24 w-full" />
        ) : equipe.isError && !equipe.data ? (
          <p className="text-sm text-destructive">Não foi possível carregar a equipe.</p>
        ) : (equipe.data ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">Nenhum membro ainda.</p>
        ) : (
          <ul className="space-y-2" data-testid="equipe-lista">
            {(equipe.data ?? []).map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-2 text-sm">
                <span className={m.ativo ? "" : "text-muted-foreground line-through"}>
                  {m.nome}
                  {m.funcao ? <span className="text-muted-foreground"> · {m.funcao}</span> : null}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={atualizar.isPending}
                  onClick={() =>
                    atualizar.mutate(
                      { id: m.id, patch: { ativo: !m.ativo } },
                      { onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível atualizar o membro.")) },
                    )
                  }
                >
                  {m.ativo ? "Desativar" : "Reativar"}
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex gap-2">
          <Input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome" aria-label="Nome do membro" />
          <Input value={funcao} onChange={(e) => setFuncao(e.target.value)} placeholder="Função" aria-label="Função do membro" />
          <Button disabled={!nome.trim() || criar.isPending} onClick={adicionar}>
            Adicionar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
