/** "Usar como referência" (platform admin): marks the agent as a model other agents' AI generation can copy. */
import { useState } from "react";
import { toast } from "sonner";
import { Switch } from "@noctusai/lib/design-system";
import { useSetExemplar } from "@/hooks/studio/useExemplar";
import { errorMessage } from "@/lib/errors";

export function ExemplarSwitch({ agentKey, exemplar }: { agentKey: string; exemplar: boolean }) {
  const set = useSetExemplar(agentKey);
  const [erro, setErro] = useState<string | null>(null);

  async function alternar(v: boolean) {
    setErro(null);
    try {
      await set.mutateAsync({ exemplar: v });
      toast.success(v ? "Agente marcado como referência." : "Agente não é mais referência.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4" data-testid="exemplar-card">
      <div className="flex items-center gap-3">
        <Switch
          id="exemplar-switch"
          checked={exemplar}
          disabled={set.isPending}
          onCheckedChange={(v) => void alternar(v)}
          data-testid="exemplar-switch"
        />
        <label htmlFor="exemplar-switch" className="text-sm font-medium">
          Usar como referência
        </label>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Agentes de referência aparecem no formulário de geração com IA como modelo de estrutura.
      </p>
      {erro && (
        <p className="mt-1 text-xs text-destructive" role="alert" data-testid="exemplar-erro">
          {erro}
        </p>
      )}
    </div>
  );
}
