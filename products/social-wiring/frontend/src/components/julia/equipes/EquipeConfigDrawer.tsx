/** Team "Configurações" — edit name, post-Julia flag, distribution mode, keep-last. */
import { useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAtualizarEquipe, type Equipe } from "@/hooks/useJuliaEquipes";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { Passo1Campos, Passo3Campos, type CamposValor } from "./CamposEquipe";

export function EquipeConfigDrawer({ equipe, onClose }: { equipe: Equipe; onClose: () => void }) {
  const [c, setC] = useState<CamposValor>({
    nome: equipe.nome, atende_apos_julia: equipe.atende_apos_julia, modo: equipe.modo, manter_ultimo: equipe.manter_ultimo,
  });
  const salvar = useAtualizarEquipe();
  const set = (p: Partial<CamposValor>) => setC((x) => ({ ...x, ...p }));
  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title={`Configurações — ${equipe.nome}`}
      width="sm"
      testId="equipe-config"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={salvar.isPending || !c.nome.trim()} onClick={() =>
            salvar.mutate({ id: equipe.id, ...c, nome: c.nome.trim() }, {
              onSuccess: () => { toast.success("Equipe atualizada."); onClose(); },
              onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar a equipe.")),
            })}>Salvar</Button>
        </div>
      }
    >
      <div className="space-y-8">
        <Passo1Campos valor={c} onChange={set} />
        <Passo3Campos valor={c} onChange={set} />
      </div>
    </SideDrawer>
  );
}
