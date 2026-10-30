/**
 * Julia's slice of a WhatsApp thread header (contract 11.4) — plugged into the
 * seed `ChatWindow` through its `ThreadHeaderExtra` seam.
 *
 *   - state chip (ativo / pausado / concluído / transferido) as AGENTS reports it
 *     (`GET .../chats/{chat}/agente`), with its source flag: `agents` live, `espelho`
 *     (agents unreachable: last known, possibly stale) or `nenhuma` (Julia never served
 *     this chat) — SW decides nothing, it displays;
 *   - computed stage chip: stage label + score ONLY (rule and points are platform IP);
 *   - admin toggle that pauses / resumes Julia on THIS chat (proxied to agents; disabled
 *     while the live state is unknown);
 *   - admin action "Apagar dados deste contato (LGPD)" behind a confirm dialog.
 *
 * Reads/writes are server-enforced (admin only); the UI only hides what the
 * server would refuse (`useIsOrgAdmin` is UX, not authorization).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Bot, Loader2, Trash2, TrendingUp, UserRound } from "lucide-react";
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
import { PainelLead } from "@/components/julia/PainelLead";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import { useJuliaRoteamento } from "@/hooks/useJuliaRoteamento";
import { AVISO_FONTE, ROTULO_ESTADO, useJuliaConversaEstado, type EstadoConversa } from "@/hooks/useJuliaConversaEstado";
import { useJuliaContato } from "@/hooks/useJuliaPerguntas";
import { ConversaAcoes, contatoMeta } from "@/components/julia/conversas/ConversaAcoes";
import { OptOutAcoes } from "@/components/julia/optouts/OptOutConversa";

export function JuliaThreadHeader({
  scopeId,
  thread,
}: {
  scopeId: string | null;
  thread: ChatThread;
}) {
  const isAdmin = useIsOrgAdmin();
  const { data: rot } = useJuliaRoteamento();
  const pausar = useSetChatAgentePausado(scopeId);
  const apagar = useApagarDadosChat(scopeId);
  const [confirmando, setConfirmando] = useState(false);

  // Present only when the thread comes from the Julia Conversas v2 feed.
  const contato = contatoMeta(thread.meta);
  // The chip only means something on a line that feeds Julia.
  const juliaLigada = rot?.linhas.find((c) => c.connection_id === scopeId)?.alimenta === true;
  const estadoQ = useJuliaConversaEstado(scopeId, thread.id, juliaLigada);
  const lead = useJuliaContato(juliaLigada ? scopeId : null, juliaLigada ? thread.id : null);
  // `useJuliaContato` keeps the previous chat's data while the next loads: never show ITS stage on this lead.
  const chipEstagio = lead.isPlaceholderData ? null : (lead.data?.qualificacao ?? null);
  // Two signals off `data`; when the live read FAILED we fall back to the mirror the chat row carries, flagged stale.
  const estado: EstadoConversa | null =
    estadoQ.data ??
    (estadoQ.isError
      ? {
          thread_id: null,
          estado: (thread.meta?.agente_estado as EstadoConversa["estado"]) ?? (thread.meta?.agente_pausado === true ? "pausado" : null),
          pausado: thread.meta?.agente_pausado === true,
          reengajamento_suprimido: null,
          motivo: null,
          fonte: "espelho",
        }
      : null);
  const pausado = estado?.estado === "pausado";
  const podeAlternar = estado?.fonte === "agents" && (estado.estado === "ativo" || estado.estado === "pausado");

  function alternar() {
    pausar.mutate(
      { chatId: thread.id, pausado: !pausado },
      {
        onSuccess: () =>
          toast.success(pausado ? "Julia voltou a atender esta conversa" : "Atendimento humano ativado"),
        onError: (e) => toast.error(mensagemErroJulia(e, "Não foi possível alterar o atendimento.")),
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
        onError: (e) => toast.error(mensagemErroJulia(e, "Não foi possível apagar os dados.")),
      },
    );
  }

  return (
    <div className="flex flex-shrink-0 items-center gap-2" data-testid="julia-thread-header">
      {contato && <ConversaAcoes contato={contato} />}
      {contato && scopeId && <OptOutAcoes connectionId={scopeId} chatId={thread.id} contatoId={contato.contatoId} />}
      {juliaLigada && <PainelLead connectionId={scopeId} chatId={thread.id} />}
      {juliaLigada && !estado && (
        <span className="h-5 w-28 animate-pulse rounded-full bg-muted" data-testid="julia-chip-skeleton" />
      )}
      {juliaLigada && estado && (
        <span
          data-testid="julia-chip"
          data-estado={estado.estado ?? "nenhum"}
          data-fonte={estado.fonte}
          data-pausado={pausado ? "true" : "false"}
          title={AVISO_FONTE[estado.fonte] ?? undefined}
          className={
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium " +
            (estado.fonte !== "agents"
              ? "bg-muted text-muted-foreground"
              : estado.estado === "ativo"
                ? "bg-primary/10 text-primary"
                : "bg-warning-light text-warning-foreground")
          }
        >
          {estado.estado === "ativo" ? <Bot className="h-3 w-3" /> : <UserRound className="h-3 w-3" />}
          {estado.estado ? ROTULO_ESTADO[estado.estado] : "Julia ainda não atendeu"}
          {estado.fonte === "espelho" && " (último estado conhecido)"}
        </span>
      )}
      {juliaLigada && estado && AVISO_FONTE[estado.fonte] && (
        <span className="sr-only" data-testid="julia-fonte-aviso">
          {AVISO_FONTE[estado.fonte]}
        </span>
      )}
      {juliaLigada && chipEstagio && (
        <span
          data-testid="julia-estagio"
          className="inline-flex items-center gap-1 rounded-full bg-success-light px-2 py-0.5 text-xs font-medium text-success"
        >
          <TrendingUp className="h-3 w-3" />
          {chipEstagio.rotulo || chipEstagio.estagio}
          {typeof chipEstagio.score === "number" && ` · ${chipEstagio.score}`}
        </span>
      )}
      {isAdmin && juliaLigada && podeAlternar && (
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
