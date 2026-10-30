/**
 * Julia › Proteção (`/julia/protecao`): every abuse limit of the org -- visible, with its default and range -- and the per-org number
 * blocklist (owner 2026-10-21: "set limits and rate limitings ... so we protect our operation from someone trying to break our system
 * on purpose"). Org-admin only.
 *
 *   Limites           per-number inbound rate, media AI budget per chat / per line a day, the automatic temporary block
 *   Texto do documento  what the vision model is asked for a lead's document (type + a non-identifying summary)
 *   Números bloqueados  manual or automatic-temporary blocks: reason, who, when, until; unblock with a confirmation
 *
 * Loading = two signals off `data` (never `isLoading`); confirmations are design-system dialogs, never browser dialogs.
 */
import { useState } from "react";
import { AlertCircle, Loader2, ShieldAlert } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { BloqueioDialog } from "@/components/julia/protecao/BloqueioDialog";
import { LimitesForm } from "@/components/julia/protecao/LimitesForm";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { formatarDataHora } from "@/hooks/useJuliaOptOuts";
import {
  ROTULO_GATILHO, useBloqueios, useBloquearNumero, useConfigProtecao, useDesbloquearNumero, type Bloqueio,
} from "@/hooks/useJuliaProtecao";
import { formatarTelefone } from "@/hooks/useJuliaEquipeWhatsapp";
import { mensagemErroServidor } from "@/lib/erroServidor";

function rotuloNumero(n: string): string {
  return n.endsWith("@lid") ? "Contato sem número (LID)" : formatarTelefone(n);
}

export default function JuliaProtecao() {
  const isAdmin = useIsOrgAdmin();
  const config = useConfigProtecao(isAdmin);
  const [historico, setHistorico] = useState(false);
  const bloqueios = useBloqueios(historico, isAdmin);
  const bloquear = useBloquearNumero();
  const desbloquear = useDesbloquearNumero();
  const [novo, setNovo] = useState(false);
  const [alvo, setAlvo] = useState<Bloqueio | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [erroDesbloqueio, setErroDesbloqueio] = useState<string | null>(null);

  function confirmarBloqueio(corpo: { numero: string; motivo: string; duracao_min?: number }) {
    setErro(null);
    bloquear.mutate(corpo, {
      onSuccess: () => { setNovo(false); toast.success("Número bloqueado."); },
      onError: (e) => setErro(mensagemErroServidor(e, "Não foi possível bloquear o número.")),
    });
  }
  function confirmarDesbloqueio() {
    if (!alvo) return;
    setErroDesbloqueio(null);
    desbloquear.mutate({ id: alvo.id }, {
      onSuccess: () => { setAlvo(null); toast.success("Número desbloqueado."); },
      onError: (e) => setErroDesbloqueio(mensagemErroServidor(e, "Não foi possível desbloquear.")),
    });
  }

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Proteção da linha pública</h1>
        <p className="text-sm text-muted-foreground">
          Limites e bloqueios que protegem a operação de quem tenta sobrecarregar ou abusar da Julia. Valem para toda a organização.
        </p>
      </header>

      {!isAdmin && (
        <p className="rounded-md border border-warning/40 bg-warning-light px-3 py-2 text-sm text-warning-foreground" data-testid="protecao-sem-permissao">
          Somente owner ou admin da organização vê e edita a proteção.
        </p>
      )}

      {isAdmin && config.showSkeleton && <div className="h-64 animate-pulse rounded-lg bg-muted" data-testid="protecao-skeleton" />}
      {isAdmin && config.isError && !config.data && (
        <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground" data-testid="protecao-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">{mensagemErroServidor(config.error, "Não foi possível carregar os limites.")}</p>
          <Button variant="outline" size="sm" onClick={() => config.refetch()}>Tentar de novo</Button>
        </div>
      )}
      {isAdmin && config.data && <LimitesForm key={config.data.atualizado_em ?? "padrao"} config={config.data} />}

      {isAdmin && (
        <section className="space-y-3" aria-labelledby="bloqueios-titulo">
          <div className="flex items-center justify-between gap-3">
            <h2 id="bloqueios-titulo" className="flex items-center gap-2 text-lg font-semibold">
              <ShieldAlert className="h-5 w-5" /> Números bloqueados
            </h2>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1 text-sm">
                <input type="checkbox" checked={historico} onChange={(e) => setHistorico(e.target.checked)} data-testid="bloqueios-historico" />
                Mostrar histórico
              </label>
              <Button size="sm" onClick={() => { setErro(null); setNovo(true); }} data-testid="bloqueio-novo">Bloquear número</Button>
            </div>
          </div>
          {bloqueios.showSkeleton && <div className="h-24 animate-pulse rounded-lg bg-muted" data-testid="bloqueios-skeleton" />}
          {bloqueios.isError && !bloqueios.data && (
            <p role="alert" className="text-sm text-destructive" data-testid="bloqueios-erro">
              {mensagemErroServidor(bloqueios.error, "Não foi possível carregar os bloqueios.")}
            </p>
          )}
          {bloqueios.data && bloqueios.data.length === 0 && (
            <p className="rounded-lg border border-dashed py-8 text-center text-sm text-muted-foreground" data-testid="bloqueios-vazio">
              Nenhum número bloqueado.
            </p>
          )}
          {bloqueios.data && bloqueios.data.length > 0 && (
            <>
              {bloqueios.isRefreshing && (
                <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="bloqueios-refreshing">
                  <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
                </span>
              )}
              <ul className="space-y-2" data-testid="bloqueios-lista">
                {bloqueios.data.map((b) => (
                  <li key={b.id} className="flex items-start justify-between gap-3 rounded-md border p-3" data-testid="bloqueio-item">
                    <div className="min-w-0 space-y-0.5 text-sm">
                      <p className="font-medium">
                        {rotuloNumero(b.numero)}
                        <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-xs font-normal" data-testid="bloqueio-origem">
                          {b.origem === "automatico" ? `Automático · ${ROTULO_GATILHO[b.gatilho] ?? b.gatilho}` : "Manual"}
                        </span>
                        {!b.ativo && <span className="ml-2 rounded-full bg-success-light px-2 py-0.5 text-xs font-normal text-success" data-testid="bloqueio-desfeito">desbloqueado</span>}
                      </p>
                      <p className="text-muted-foreground">{b.motivo}</p>
                      <p className="text-xs text-muted-foreground">
                        Desde {formatarDataHora(b.criado_em)}
                        {b.expira_em ? ` · até ${formatarDataHora(b.expira_em)}` : " · sem prazo"}
                        {b.desbloqueado_em ? ` · desbloqueado em ${formatarDataHora(b.desbloqueado_em)}` : ""}
                      </p>
                      {b.notificacao_status === "falhou" && (
                        <p className="text-xs text-destructive" data-testid="bloqueio-aviso-falhou">Os admins não puderam ser avisados deste bloqueio.</p>
                      )}
                    </div>
                    {b.ativo && (
                      <Button variant="outline" size="sm" onClick={() => { setErroDesbloqueio(null); setAlvo(b); }} data-testid="bloqueio-desbloquear">
                        Desbloquear
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {novo && <BloqueioDialog aberto pendente={bloquear.isPending} erro={erro} onConfirmar={confirmarBloqueio} onFechar={() => setNovo(false)} />}

      <AlertDialog open={alvo !== null} onOpenChange={(o) => { if (!o && !desbloquear.isPending) setAlvo(null); }}>
        <AlertDialogContent data-testid="desbloquear-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Desbloquear este número?</AlertDialogTitle>
            <AlertDialogDescription>
              As mensagens dele voltam a chegar à Julia. Os limites de proteção continuam valendo e um novo abuso pode bloqueá-lo de novo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {erroDesbloqueio && <p role="alert" className="text-sm text-destructive" data-testid="desbloquear-erro">{erroDesbloqueio}</p>}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={desbloquear.isPending}>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); confirmarDesbloqueio(); }} disabled={desbloquear.isPending} data-testid="desbloquear-confirmar">
              {desbloquear.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Desbloquear
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
