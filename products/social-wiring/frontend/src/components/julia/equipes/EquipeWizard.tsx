/** "Configurar nova equipe" — 3-step SideDrawer wizard (live Julia §59.0b). */
import { useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useCriarEquipe } from "@/hooks/useJuliaEquipes";
import { useTeamMembers } from "@/hooks/useTeam";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { CAMPOS_PADRAO, Passo1Campos, Passo3Campos, type CamposValor } from "./CamposEquipe";

export function EquipeWizard({ onClose }: { onClose: () => void }) {
  const [passo, setPasso] = useState(1);
  const [campos, setCampos] = useState<CamposValor>(CAMPOS_PADRAO);
  const [sel, setSel] = useState<string[]>([]);
  const { data: usuarios = [], isPending, isError } = useTeamMembers();
  const criar = useCriarEquipe();
  const set = (p: Partial<CamposValor>) => setCampos((c) => ({ ...c, ...p }));
  const nomeOk = campos.nome.trim().length > 0;

  function concluir() {
    criar.mutate({ ...campos, nome: campos.nome.trim(), user_ids: sel }, {
      onSuccess: () => { toast.success("Equipe criada."); onClose(); },
      onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível criar a equipe.")),
    });
  }

  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Configurar nova equipe"
      description={`Passo ${passo} de 3`}
      width="sm"
      testId="equipe-wizard"
      footer={
        <div className="flex justify-between gap-2">
          <Button variant="outline" disabled={passo === 1} onClick={() => setPasso(passo - 1)}>Voltar</Button>
          {passo < 3
            ? <Button disabled={passo === 1 && !nomeOk} onClick={() => setPasso(passo + 1)}>Próximo</Button>
            : <Button disabled={criar.isPending || !nomeOk} onClick={concluir}>Concluir</Button>}
        </div>
      }
    >
      <p className="mb-4 text-xs text-muted-foreground">Passo {passo} de 3</p>
      {passo === 1 && <Passo1Campos valor={campos} onChange={set} />}
      {passo === 2 && (
        <fieldset className="space-y-2" data-testid="passo-membros">
          <legend className="text-sm font-medium">Quem faz parte da equipe?</legend>
          {isPending && <p className="text-sm text-muted-foreground">Carregando usuários…</p>}
          {isError && <p className="text-sm text-destructive">Não foi possível carregar os usuários.</p>}
          {!isPending && !isError && usuarios.length === 0 && <p className="text-sm text-muted-foreground">Nenhum usuário na organização.</p>}
          {usuarios.map((u) => (
            <label key={u.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={sel.includes(u.id)}
                onChange={() => setSel((s) => s.includes(u.id) ? s.filter((x) => x !== u.id) : [...s, u.id])} />
              {u.nome || u.email}
            </label>
          ))}
        </fieldset>
      )}
      {passo === 3 && <Passo3Campos valor={campos} onChange={set} />}
    </SideDrawer>
  );
}
