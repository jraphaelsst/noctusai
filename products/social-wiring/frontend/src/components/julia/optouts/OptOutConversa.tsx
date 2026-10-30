/**
 * The opt-out of the lead behind ONE conversation, for the HUMAN operator (owner 2026-10-21: "humans can message with a
 * warning, not blocking").
 *
 *   `OptOutAviso`  -- the warning above the chat: "Este lead pediu para não ser contatado em <data> — <motivo>". It never
 *                     blocks a send. When the state cannot be read it says so ("não foi possível verificar") and the send
 *                     stays allowed -- an unreadable state is never shown as "no opt-out".
 *   `OptOutAcoes`  -- the header chip + the admin actions: "Marcar como não contatar" (reason required) or, on an active
 *                     opt-out, "Reativar atendimento" (reason required). The server enforces who may.
 */
import { useState } from "react";
import { AlertTriangle, ShieldOff } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  formatarDataHora, optOutEstadoKey, useMarcarNaoContatar, useOptOutEstado, useReativarLead,
} from "@/hooks/useJuliaOptOuts";
import { mensagemErroServidor } from "@/lib/erroServidor";
import { useQueryClient } from "@tanstack/react-query";
import { MotivoDialog } from "./MotivoDialog";

export function OptOutAviso({ connectionId, chatId }: { connectionId: string | null; chatId: string | null }) {
  const q = useOptOutEstado(connectionId, chatId);
  if (!chatId || (q.isPending && !q.data)) return null;
  if (q.isError || (q.data && !q.data.verificado)) {
    return (
      <div role="status" className="rounded-md border border-warning/40 bg-warning-light px-3 py-2 text-sm text-warning-foreground" data-testid="optout-aviso-nao-verificado">
        <AlertTriangle className="mr-1 inline h-4 w-4" />
        Não foi possível verificar se este lead pediu para não ser contatado. Você ainda pode enviar a mensagem.
      </div>
    );
  }
  if (!q.data?.opt_out_ativo) return null;
  return (
    <div role="alert" className="rounded-md border border-destructive/40 bg-danger-light px-3 py-2 text-sm text-destructive" data-testid="optout-aviso">
      <ShieldOff className="mr-1 inline h-4 w-4" />
      Este lead pediu para não ser contatado em {formatarDataHora(q.data.opt_out_em)}
      {q.data.motivo ? ` — ${q.data.motivo}` : ""}. Você pode enviar mesmo assim, com cuidado.
    </div>
  );
}

export function OptOutAcoes({ connectionId, chatId, contatoId }: { connectionId: string; chatId: string; contatoId: string }) {
  const q = useOptOutEstado(connectionId, chatId);
  const isAdmin = useIsOrgAdmin();
  const marcar = useMarcarNaoContatar();
  const reativar = useReativarLead();
  const qc = useQueryClient();
  const [modo, setModo] = useState<"marcar" | "reativar" | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const ativo = q.data?.verificado === true && q.data.opt_out_ativo;
  const verificado = q.data?.verificado === true;

  function confirmar(motivo: string) {
    setErro(null);
    const m = modo === "reativar" ? reativar : marcar;
    m.mutate({ contatoId, motivo }, {
      onSuccess: () => {
        setModo(null);
        qc.invalidateQueries({ queryKey: optOutEstadoKey(connectionId, chatId) });
        toast.success(modo === "reativar" ? "Atendimento reativado." : "Lead marcado como não contatar.");
      },
      onError: (e) => setErro(mensagemErroServidor(e, "Não foi possível concluir a ação.")),
    });
  }

  return (
    <>
      {ativo && (
        <span className="inline-flex items-center gap-1 rounded-full bg-danger-light px-2 py-0.5 text-xs font-medium text-destructive" data-testid="optout-badge">
          <ShieldOff className="h-3 w-3" /> opt-out
        </span>
      )}
      {isAdmin && verificado && (
        <Button
          variant="outline" size="sm" className="h-7 text-xs" data-testid={ativo ? "optout-reativar-conversa" : "optout-marcar"}
          onClick={() => { setErro(null); setModo(ativo ? "reativar" : "marcar"); }}
        >
          {ativo ? "Reativar atendimento" : "Marcar como não contatar"}
        </Button>
      )}
      <MotivoDialog
        aberto={modo !== null}
        titulo={modo === "reativar" ? "Reativar atendimento" : "Marcar como não contatar"}
        descricao={modo === "reativar"
          ? "O lead volta para o fluxo dos agentes e poderá ser contatado novamente. Informe por que a reativação é legítima."
          : "Os agentes deixam de contatar este lead e as conversas automáticas são encerradas. Informe o motivo."}
        confirmar={modo === "reativar" ? "Reativar atendimento" : "Marcar como não contatar"}
        pendente={marcar.isPending || reativar.isPending} erro={erro}
        onConfirmar={confirmar} onFechar={() => setModo(null)}
      />
    </>
  );
}
