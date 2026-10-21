/**
 * "Criar agente" (platform admin): registers an agent by key — an EMPTY shell that grows over time; nothing
 * is required to create it and missing texts are progress, not errors. No endpoint lists the creatable keys
 * yet, so the key is a text input (with the registered key `julia` suggested); the server's 422
 * `chave_nao_registrada` is surfaced verbatim.
 */
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import { useCreatePlatformAgent } from "@/hooks/studio/useAgentLifecycle";
import { lifecycleError } from "@/lib/agentLifecycle";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm font-mono text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

export function CriarAgentePlataformaDialog({ onClose }: { onClose: () => void }) {
  const create = useCreatePlatformAgent();
  const navigate = useNavigate();
  const [key, setKey] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const created = await create.mutateAsync({ key: key.trim() });
      toast.success("Agente criado. Ele começa vazio e cresce com o tempo.");
      onClose();
      navigate(`/studio/${encodeURIComponent(created.key)}`);
    } catch (err) {
      setErro(lifecycleError(err).message);
    }
  }

  return (
    <Dialog open onClose={onClose} title="Criar agente" className="max-w-lg">
      <form onSubmit={submit}>
        <DialogHeader>
          <h2 className="text-base font-semibold text-foreground">Criar agente da plataforma</h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          <div>
            <label htmlFor="criar-agente-key" className="mb-1 block text-sm font-medium">
              Chave do agente *
            </label>
            <input
              id="criar-agente-key"
              className={INPUT_CLASS}
              value={key}
              list="criar-agente-chaves"
              required
              placeholder="julia"
              onChange={(e) => setKey(e.target.value.toLowerCase())}
              data-testid="criar-agente-key"
            />
            <datalist id="criar-agente-chaves">
              <option value="julia" />
            </datalist>
            <p className="mt-1 text-xs text-muted-foreground">
              O agente nasce vazio — nenhum conteúdo é exigido para criar. Só a publicação exige os textos completos.
            </p>
          </div>
          {erro && (
            <p className="text-sm text-destructive" data-testid="criar-agente-erro">
              {erro}
            </p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" disabled={!key.trim() || create.isPending} data-testid="criar-agente-submit">
            {create.isPending ? "Criando..." : "Criar agente"}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  );
}
