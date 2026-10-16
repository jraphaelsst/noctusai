/** Config drawer (admin): ativo, provedor (read-only, set server-side), apenas aluguel. */
import { useEffect, useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useCreditoConfig, useSalvarCreditoConfig, type CreditoConfig } from "@/hooks/useLaisCredito";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function CreditoConfigDrawer({ onClose }: { onClose: () => void }) {
  const q = useCreditoConfig();
  const salvar = useSalvarCreditoConfig();
  const [f, setF] = useState<CreditoConfig | null>(null);
  useEffect(() => { if (q.data && !f) setF(q.data); }, [q.data, f]);

  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Configurar análise de crédito"
      width="sm"
      testId="credito-config-drawer"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={!f || salvar.isPending}
            onClick={() => f && salvar.mutate(f, {
              onSuccess: () => { toast.success("Configuração salva."); onClose(); },
              onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar.")),
            })}>Salvar</Button>
        </div>
      }
    >
      {!f ? (
        q.isError
          ? <p className="text-sm text-destructive" data-testid="credito-config-erro">Não foi possível carregar a configuração.</p>
          : <div className="h-24 animate-pulse rounded bg-muted" />
      ) : (
        <div className="space-y-5">
          <label className="flex items-center justify-between gap-3 text-sm">
            Ativar análise de crédito
            <Switch aria-label="Ativar análise de crédito" checked={f.ativo} onCheckedChange={(v) => setF({ ...f, ativo: v })} />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            Apenas para aluguel
            <Switch aria-label="Apenas para aluguel" checked={f.apenas_aluguel} onCheckedChange={(v) => setF({ ...f, apenas_aluguel: v })} />
          </label>
          <p className="text-sm text-muted-foreground">Provedor: {f.provider ?? "não configurado"}</p>
        </div>
      )}
    </SideDrawer>
  );
}
