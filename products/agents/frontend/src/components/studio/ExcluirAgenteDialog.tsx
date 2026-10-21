/** Destructive confirm: the admin must type the agent key. A 409 shows the server's reason + a short hint. */
import { useState } from "react";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { useDeleteStudioAgent } from "@/hooks/studio/useAgentLifecycle";
import { lifecycleError, type LifecycleError } from "@/lib/agentLifecycle";

export function ExcluirAgenteDialog({ agentKey, nome, onClose }: { agentKey: string; nome: string; onClose: () => void }) {
  const del = useDeleteStudioAgent();
  const [typed, setTyped] = useState("");
  const [erro, setErro] = useState<LifecycleError | null>(null);
  const match = typed === agentKey;

  async function confirm() {
    setErro(null);
    try {
      await del.mutateAsync(agentKey);
      toast.success(`Agente ${nome} excluído.`);
      onClose();
    } catch (err) {
      setErro(lifecycleError(err));
    }
  }

  return (
    <Dialog open onClose={onClose} title="Excluir agente" className="max-w-lg">
      <DialogHeader>
        <h2 className="text-base font-semibold text-foreground">Excluir “{nome}”?</h2>
        <p className="text-sm text-muted-foreground">Não dá para desfazer. Para confirmar, digite a chave do agente.</p>
      </DialogHeader>
      <DialogBody className="space-y-3">
        <label htmlFor="excluir-agente-key" className="block text-sm font-medium">
          Digite <code className="font-mono">{agentKey}</code>
        </label>
        <input
          id="excluir-agente-key"
          className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-mono"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          data-testid="excluir-agente-key"
        />
        {erro && (
          <div className="text-sm text-destructive" data-testid="excluir-agente-erro">
            <p>{erro.message}</p>
            {erro.hint && <p className="mt-1 text-xs" data-testid="excluir-agente-dica">{erro.hint}</p>}
          </div>
        )}
      </DialogBody>
      <DialogFooter className="gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
        <Button variant="destructive" onClick={confirm} disabled={!match || del.isPending} data-testid="excluir-agente-confirm">
          {del.isPending ? "Excluindo..." : "Excluir"}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}
