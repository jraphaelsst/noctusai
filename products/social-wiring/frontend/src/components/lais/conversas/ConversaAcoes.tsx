/**
 * Per-conversation actions in the thread header (contract wave 7): assign a
 * responsável, like/dislike/"Deixar feedback" on Julia's service, archive,
 * block the number, copy the history link. Archive / block / assign each ask
 * for confirmation; the server enforces who may do what (UX only here).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Archive, ArchiveRestore, Ban, Link2, MessageSquareText, ThumbsDown, ThumbsUp, UserPlus } from "lucide-react";
import { useConfirm } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useTeamMembers } from "@/hooks/useTeam";
import {
  linkHistorico, mensagemErroConversas, useFeedbackJulia, usePatchContato,
} from "@/hooks/useLaisConversas";

export interface ContatoMeta {
  contatoId: string;
  arquivado: boolean;
  bloqueado: boolean;
  responsavelUserId: string | null;
}

/** Read the adapter-owned `meta` the Conversas feed puts on each thread. */
export function contatoMeta(meta: Record<string, unknown> | undefined): ContatoMeta | null {
  const id = meta?.contato_id;
  if (typeof id !== "string" || !id) return null;
  return {
    contatoId: id,
    arquivado: meta?.arquivado === true,
    bloqueado: meta?.bloqueado === true,
    responsavelUserId: typeof meta?.responsavel_user_id === "string" ? meta.responsavel_user_id : null,
  };
}

export function ConversaAcoes({ contato }: { contato: ContatoMeta }) {
  const confirm = useConfirm();
  const patch = usePatchContato();
  const feedback = useFeedbackJulia(contato.contatoId);
  const { data: membros = [] } = useTeamMembers();
  const [atribuindo, setAtribuindo] = useState(false);
  const [feedbackAberto, setFeedbackAberto] = useState(false);
  const [nota, setNota] = useState<"like" | "dislike">("like");
  const [comentario, setComentario] = useState("");

  const falha = (msg: string) => (e: unknown) => toast.error(mensagemErroConversas(e, msg));

  async function atribuir(id: string | null, nome: string) {
    setAtribuindo(false);
    const ok = await confirm({
      title: id ? `Atribuir esta conversa a ${nome}?` : "Remover o responsável desta conversa?",
      confirmLabel: "Atribuir",
    });
    if (!ok) return;
    patch.mutate({ id: contato.contatoId, responsavel_user_id: id }, {
      onSuccess: () => toast.success("Responsável atualizado"), onError: falha("Não foi possível atribuir."),
    });
  }
  async function arquivar() {
    const ok = await confirm({
      title: contato.arquivado ? "Desarquivar esta conversa?" : "Arquivar esta conversa?",
      description: contato.arquivado ? undefined : "A Julia volta a atender quando o contato enviar uma nova mensagem.",
      confirmLabel: contato.arquivado ? "Desarquivar" : "Arquivar",
    });
    if (!ok) return;
    patch.mutate({ id: contato.contatoId, arquivado: !contato.arquivado }, {
      onSuccess: () => toast.success(contato.arquivado ? "Conversa desarquivada" : "Conversa arquivada"),
      onError: falha("Não foi possível arquivar."),
    });
  }
  async function bloquear() {
    const ok = await confirm({
      title: contato.bloqueado ? "Desbloquear este número?" : "Bloquear este número?",
      description: contato.bloqueado ? undefined : "Mensagens deste número deixam de ser respondidas pela Julia.",
      confirmLabel: contato.bloqueado ? "Desbloquear" : "Bloquear",
      tone: contato.bloqueado ? undefined : "danger",
    });
    if (!ok) return;
    patch.mutate({ id: contato.contatoId, bloqueado: !contato.bloqueado }, {
      onSuccess: () => toast.success(contato.bloqueado ? "Número desbloqueado" : "Número bloqueado"),
      onError: falha("Não foi possível alterar o bloqueio."),
    });
  }
  function enviarFeedback(n: "like" | "dislike", c?: string) {
    feedback.mutate({ nota: n, comentario: c?.trim() || undefined }, {
      onSuccess: () => { toast.success("Feedback registrado"); setFeedbackAberto(false); setComentario(""); },
      onError: falha("Não foi possível registrar o feedback."),
    });
  }
  async function copiar() {
    try {
      await navigator.clipboard.writeText(linkHistorico(contato.contatoId));
      toast.success("Link copiado");
    } catch {
      toast.error("Não foi possível copiar o link.");
    }
  }

  return (
    <div className="flex flex-shrink-0 items-center gap-0.5" data-testid="conversa-acoes">
      <Popover open={atribuindo} onOpenChange={setAtribuindo}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="sm" className="h-7 gap-1 text-xs" data-testid="acao-atribuir">
            <UserPlus className="h-3.5 w-3.5" /> Atribuir responsável
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-60 p-1">
          <ul className="max-h-56 overflow-y-auto">
            <li>
              <button type="button" className="w-full rounded px-2 py-1 text-left text-sm hover:bg-muted"
                onClick={() => void atribuir(null, "")}>Sem responsável</button>
            </li>
            {membros.map((m) => (
              <li key={m.id}>
                <button type="button" aria-current={m.id === contato.responsavelUserId}
                  className="w-full rounded px-2 py-1 text-left text-sm hover:bg-muted aria-[current=true]:font-semibold"
                  onClick={() => void atribuir(m.id, m.nome || m.email)}>{m.nome || m.email}</button>
              </li>
            ))}
          </ul>
        </PopoverContent>
      </Popover>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Gostei do atendimento da Julia" title="Gostei do atendimento da Julia"
        disabled={feedback.isPending} onClick={() => enviarFeedback("like")} data-testid="acao-like">
        <ThumbsUp className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Não gostei do atendimento da Julia" title="Não gostei do atendimento da Julia"
        disabled={feedback.isPending} onClick={() => { setNota("dislike"); setFeedbackAberto(true); }} data-testid="acao-dislike">
        <ThumbsDown className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Deixar feedback" title="Deixar feedback"
        onClick={() => { setNota("like"); setFeedbackAberto(true); }} data-testid="acao-feedback">
        <MessageSquareText className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={contato.arquivado ? "Desarquivar" : "Arquivar"}
        title={contato.arquivado ? "Desarquivar" : "Arquivar"} disabled={patch.isPending} onClick={() => void arquivar()} data-testid="acao-arquivar">
        {contato.arquivado ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={contato.bloqueado ? "Desbloquear número" : "Bloquear número"}
        title={contato.bloqueado ? "Desbloquear número" : "Bloquear número"} disabled={patch.isPending} onClick={() => void bloquear()} data-testid="acao-bloquear">
        <Ban className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Copiar link do histórico" title="Copiar link do histórico"
        onClick={() => void copiar()} data-testid="acao-link">
        <Link2 className="h-4 w-4" />
      </Button>

      <Dialog open={feedbackAberto} onOpenChange={setFeedbackAberto}>
        <DialogContent>
          <DialogHeader><DialogTitle>Feedback sobre o atendimento da Julia</DialogTitle></DialogHeader>
          <div className="flex gap-2">
            <Button variant={nota === "like" ? "default" : "outline"} size="sm" onClick={() => setNota("like")}>
              <ThumbsUp className="mr-1 h-4 w-4" /> Gostei
            </Button>
            <Button variant={nota === "dislike" ? "default" : "outline"} size="sm" onClick={() => setNota("dislike")}>
              <ThumbsDown className="mr-1 h-4 w-4" /> Não gostei
            </Button>
          </div>
          <Textarea placeholder="Comentário (opcional)" value={comentario} onChange={(e) => setComentario(e.target.value)} maxLength={2000} aria-label="Comentário" />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setFeedbackAberto(false)}>Cancelar</Button>
            <Button disabled={feedback.isPending} onClick={() => enviarFeedback(nota, comentario)} data-testid="feedback-enviar">Enviar feedback</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
