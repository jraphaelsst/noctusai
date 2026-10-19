/** Team "Usuários" — add / remove members and set their round-robin order. */
import { SideDrawer } from "@noctusai/lib/components";
import { ArrowDown, ArrowUp, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAdicionarMembro, useOrdenarMembros, useRemoverMembro, type Equipe } from "@/hooks/useJuliaEquipes";
import { useTeamMembers } from "@/hooks/useTeam";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function EquipeUsuariosDrawer({ equipe, onClose }: { equipe: Equipe; onClose: () => void }) {
  const { data: usuarios = [] } = useTeamMembers();
  const add = useAdicionarMembro();
  const rem = useRemoverMembro();
  const ord = useOrdenarMembros();
  const membros = [...equipe.membros].sort((a, b) => a.ordem - b.ordem);
  const ids = new Set(membros.map((m) => m.user_id));
  const livres = usuarios.filter((u) => !ids.has(u.id));
  const erro = (e: unknown) => toast.error(mensagemErroServidor(e, "Não foi possível atualizar os usuários."));

  function mover(i: number, delta: number) {
    const lista = membros.map((m) => m.user_id);
    const j = i + delta;
    if (j < 0 || j >= lista.length) return;
    [lista[i], lista[j]] = [lista[j], lista[i]];
    ord.mutate({ id: equipe.id, user_ids: lista }, { onError: erro });
  }

  return (
    <SideDrawer open onOpenChange={(o) => { if (!o) onClose(); }} title={`Usuários — ${equipe.nome}`} width="sm" testId="equipe-usuarios">
      <div className="space-y-5">
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Membros</h3>
          {membros.length === 0 && <p className="text-sm text-muted-foreground">Nenhum membro nesta equipe.</p>}
          {membros.map((m, i) => (
            <div key={m.user_id} className="flex items-center gap-1 rounded border px-2 py-1.5 text-sm" data-testid="membro-linha">
              <span className="flex-1">{m.nome}</span>
              <Button variant="ghost" size="icon" aria-label={`Subir ${m.nome}`} disabled={i === 0} onClick={() => mover(i, -1)}><ArrowUp className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" aria-label={`Descer ${m.nome}`} disabled={i === membros.length - 1} onClick={() => mover(i, 1)}><ArrowDown className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" aria-label={`Remover ${m.nome}`}
                onClick={() => rem.mutate({ id: equipe.id, user_id: m.user_id }, { onError: erro })}><X className="h-4 w-4" /></Button>
            </div>
          ))}
        </section>
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Adicionar usuário</h3>
          {livres.length === 0 && <p className="text-sm text-muted-foreground">Todos os usuários já estão na equipe.</p>}
          {livres.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded border px-2 py-1.5 text-sm">
              <span>{u.nome || u.email}</span>
              <Button size="sm" variant="outline" disabled={add.isPending} aria-label={`Adicionar ${u.nome || u.email}`}
                onClick={() => add.mutate({ id: equipe.id, user_id: u.id }, { onError: erro })}>Adicionar</Button>
            </div>
          ))}
        </section>
      </div>
    </SideDrawer>
  );
}
