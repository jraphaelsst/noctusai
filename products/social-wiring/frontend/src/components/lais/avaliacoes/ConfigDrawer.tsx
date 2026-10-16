/** Config drawer (admin): Google review link + CAPI qualification-signal switch. */
import { useEffect, useState } from "react";
import { SideDrawer } from "@noctusai/lib/components";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAvaliacoesConfig, useSalvarAvaliacoesConfig, type AvaliacoesConfig } from "@/hooks/useLaisAvaliacoes";
import { mensagemErroServidor } from "@/lib/erroServidor";

export function AvaliacoesConfigDrawer({ onClose }: { onClose: () => void }) {
  const q = useAvaliacoesConfig(true);
  const salvar = useSalvarAvaliacoesConfig();
  const [f, setF] = useState<AvaliacoesConfig | null>(null);
  useEffect(() => { if (q.data && !f) setF(q.data); }, [q.data, f]);

  return (
    <SideDrawer
      open
      onOpenChange={(o) => { if (!o) onClose(); }}
      title="Configurar avaliações"
      width="sm"
      testId="avaliacoes-config-drawer"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button disabled={!f || salvar.isPending}
            onClick={() => f && salvar.mutate(
              { ...f, google_review_url: f.google_review_url?.trim() || null },
              {
                onSuccess: () => { toast.success("Configuração salva."); onClose(); },
                onError: (e) => toast.error(mensagemErroServidor(e, "Não foi possível salvar.")),
              })}>Salvar</Button>
        </div>
      }
    >
      {!f ? (
        q.isError
          ? <p className="text-sm text-destructive" data-testid="avaliacoes-config-erro">Não foi possível carregar a configuração.</p>
          : <div className="h-24 animate-pulse rounded bg-muted" />
      ) : (
        <div className="space-y-5">
          <label className="block space-y-1 text-sm">
            Link de avaliação do Google
            <input aria-label="Link de avaliação do Google" type="url" placeholder="https://g.page/r/…/review"
              className="h-9 w-full rounded-md border bg-background px-2 text-sm"
              value={f.google_review_url ?? ""} onChange={(e) => setF({ ...f, google_review_url: e.target.value })} />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            Enviar sinais de qualificação para a Meta (CAPI)
            <Switch aria-label="Enviar sinais de qualificação para a Meta (CAPI)" checked={f.capi_ativo}
              onCheckedChange={(v) => setF({ ...f, capi_ativo: v })} />
          </label>
        </div>
      )}
    </SideDrawer>
  );
}
