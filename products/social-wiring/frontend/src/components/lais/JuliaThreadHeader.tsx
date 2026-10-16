/**
 * Julia's slice of a WhatsApp thread header (contract 11.4) — plugged into the
 * seed `ChatWindow` through its `ThreadHeaderExtra` seam.
 *
 *   - chip "Julia atendendo" / "Atendimento humano" (from the chat's
 *     `agente_pausado`, kept live by the realtime `chat.upsert`);
 *   - admin toggle that pauses / resumes Julia on THIS chat;
 *   - admin action "Apagar dados deste contato (LGPD)" behind a confirm dialog.
 *
 * Reads/writes are server-enforced (admin only); the UI only hides what the
 * server would refuse (`useIsOrgAdmin` is UX, not authorization).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Bot, Loader2, Trash2, UserRound } from "lucide-react";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";
import type { ChatThread } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useApagarDadosChat, useSetChatAgentePausado } from "@/hooks/useWhatsAppChats";
import { PainelLead } from "@/components/lais/PainelLead";
import { useLaisAgente, mensagemErroLais } from "@/hooks/useLaisAgente";
import { ConversaAcoes, contatoMeta } from "@/components/lais/conversas/ConversaAcoes";

export function JuliaThreadHeader({
  scopeId,
  thread,
}: {
  scopeId: string | null;
  thread: ChatThread;
}) {
  const isAdmin = useIsOrgAdmin();
  const { data: agente } = useLaisAgente();
  const pausar = useSetChatAgentePausado(scopeId);
  const apagar = useApagarDadosChat(scopeId);
  const [confirmando, setConfirmando] = useState(false);

  const pausado = thread.meta?.agente_pausado === true;
  // Present only when the thread comes from the Lais Conversas v2 feed.
  const contato = contatoMeta(thread.meta);
  // The chip only means something on a connection where Julia is switched on.
  const juliaLigada =
    agente?.conexoes.find((c) => c.connection_id === scopeId)?.agente_leads_ativo === true;

  function alternar() {
    pausar.mutate(
      { chatId: thread.id, pausado: !pausado },
      {
        onSuccess: () =>
          toast.success(pausado ? "Julia voltou a atender esta conversa" : "Atendimento humano ativado"),
        onError: (e) => toast.error(mensagemErroLais(e, "Não foi possível alterar o atendimento.")),
      },
    );
  }

  function apagarDados() {
    apagar.mutate(
      { chatId: thread.id },
      {
        onSuccess: (r) => {
          setConfirmando(false);
          toast.success(
            r.agents_ok
              ? "Dados deste contato apagados."
              : "Dados apagados aqui; a exclusão no Agents falhou — tente novamente.",
          );
        },
        onError: (e) => toast.error(mensagemErroLais(e, "Não foi possível apagar os dados.")),
      },
    );
  }

  return (
    <div className="flex flex-shrink-0 items-center gap-2" data-testid="julia-thread-header">
      {contato && <ConversaAcoes contato={contato} />}
      {juliaLigada && <PainelLead connectionId={scopeId} chatId={thread.id} />}
      {juliaLigada && (
        <span
          data-testid="julia-chip"
          data-pausado={pausado ? "true" : "false"}
          className={
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium " +
            (pausado ? "bg-amber-100 text-amber-900" : "bg-primary/10 text-primary")
          }
        >
          {pausado ? <UserRound className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
          {pausado ? "Atendimento humano" : "Julia atendendo"}
        </span>
      )}
      {isAdmin && juliaLigada && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          disabled={pausar.isPending}
          onClick={alternar}
          data-testid="julia-toggle"
        >
          {pausar.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
          {pausado ? "Devolver à Julia" : "Assumir conversa"}
        </Button>
      )}
      {isAdmin && (
        <>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label="Apagar dados deste contato (LGPD)"
            title="Apagar dados deste contato (LGPD)"
            onClick={() => setConfirmando(true)}
            data-testid="julia-apagar-dados"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <AlertDialog open={confirmando} onOpenChange={setConfirmando}>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Apagar dados deste contato?</AlertDialogTitle>
                <AlertDialogDescription>
                  Remove as mensagens e o contato desta conversa e pede ao Agents que apague o histórico da
                  Julia. Use apenas a pedido do titular (LGPD). Não pode ser desfeito.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => {
                    e.preventDefault();
                    apagarDados();
                  }}
                  disabled={apagar.isPending}
                  data-testid="julia-confirmar-apagar"
                >
                  {apagar.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                  Apagar dados
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </>
      )}
    </div>
  );
}
