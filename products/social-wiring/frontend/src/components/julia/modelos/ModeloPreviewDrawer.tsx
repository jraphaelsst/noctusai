/** "Pré-visualização" drawer — WhatsApp bubble + per-parameter simulation + delete. */
import { useState } from "react";
import { toast } from "sonner";
import { SideDrawer, useConfirm } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PARAMETROS, parametrosDoTexto, simular, useExcluirModelo, type Modelo } from "@/hooks/useJuliaModelos";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";

export function ModeloPreviewDrawer({ modelo, onClose }: { modelo: Modelo | null; onClose: () => void }) {
  const confirmar = useConfirm();
  const excluir = useExcluirModelo();
  const [valores, setValores] = useState<Record<string, string>>({});
  const usados = modelo ? parametrosDoTexto(modelo.conteudo) : [];

  async function remover() {
    if (!modelo) return;
    if (!(await confirmar({ title: "Excluir modelo", description: `Excluir "${modelo.nome}"?`, confirmLabel: "Excluir", tone: "danger" }))) return;
    excluir.mutate(modelo.id, {
      onSuccess: () => {
        toast.success("Modelo excluído");
        onClose();
      },
      onError: (e) => toast.error(mensagemErroJulia(e, "Não foi possível excluir o modelo.")),
    });
  }

  return (
    <SideDrawer open={!!modelo} onOpenChange={(o) => !o && onClose()} title="Pré-visualização" description={modelo?.nome} testId="modelo-preview">
      {modelo && (
        <div className="mt-4 space-y-4">
          <div className="rounded-lg bg-success-light p-3 text-sm whitespace-pre-wrap" data-testid="preview-bolha">
            {simular(modelo.conteudo, valores)}
          </div>
          {usados.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Simule com exemplos</p>
              {usados.map((t) => {
                const p = PARAMETROS.find((x) => x.token === t);
                return (
                  <div key={t} className="space-y-1">
                    <Label htmlFor={`sim-${t}`}>{p?.label ?? t}</Label>
                    <Input
                      id={`sim-${t}`}
                      placeholder={p?.exemplo}
                      value={valores[t] ?? ""}
                      onChange={(e) => setValores((v) => ({ ...v, [t]: e.target.value }))}
                    />
                  </div>
                );
              })}
            </div>
          )}
          <div className="flex justify-between">
            <Button variant="outline" className="text-destructive" onClick={remover} disabled={excluir.isPending}>
              Excluir modelo
            </Button>
            <Button onClick={onClose}>OK</Button>
          </div>
        </div>
      )}
    </SideDrawer>
  );
}
