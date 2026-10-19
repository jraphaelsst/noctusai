/**
 * Julia › history of ONE contact (`/julia/conversas/h/:contatoId`, contract A7).
 * Chrome-light, read-only, login required (mounted as an unwrapped route).
 * Access is decided by the server: 403 `sem_acesso` → "Você não tem acesso a
 * esta conversa", 404 → not found.
 */
import { useParams } from "react-router-dom";
import { AlertCircle, Loader2, Lock, SearchX } from "lucide-react";

import { InteracoesLista, fmtData } from "@/components/julia/conversas/InteracoesLista";
import { codigoHttp, useHistorico } from "@/hooks/useJuliaConversas";

function Estado({ icon, titulo, texto }: { icon: React.ReactNode; titulo: string; texto?: string }) {
  return (
    <div role="alert" className="flex h-64 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
      {icon}
      <p className="text-sm font-medium text-foreground">{titulo}</p>
      {texto && <p className="text-xs">{texto}</p>}
    </div>
  );
}

export default function JuliaHistorico() {
  const { contatoId = null } = useParams<{ contatoId: string }>();
  const { data, isPending, isError, error } = useHistorico(contatoId);

  let corpo: React.ReactNode;
  if (isPending && !data) {
    corpo = <div className="flex h-64 items-center justify-center gap-2 text-muted-foreground" data-testid="historico-carregando"><Loader2 className="h-5 w-5 animate-spin" /> Carregando histórico...</div>;
  } else if (isError && !data) {
    const c = codigoHttp(error);
    corpo = c === 403
      ? <Estado icon={<Lock className="h-8 w-8" />} titulo="Você não tem acesso a esta conversa" texto="Só o responsável pela conversa e os administradores da organização podem abri-la." />
      : c === 404
        ? <Estado icon={<SearchX className="h-8 w-8" />} titulo="Conversa não encontrada" />
        : <Estado icon={<AlertCircle className="h-8 w-8 text-destructive" />} titulo="Não foi possível carregar o histórico." texto="Tente novamente em instantes." />;
  } else if (data) {
    const { contato, interacoes, mensagens } = data;
    corpo = (
      <div className="space-y-6">
        <header>
          <h1 className="text-xl font-semibold">{contato.nome ?? "Contato"}</h1>
          <p className="text-sm text-muted-foreground">
            {[contato.telefone, contato.operacao, contato.responsavel_nome && `Responsável: ${contato.responsavel_nome}`].filter(Boolean).join(" · ")}
          </p>
        </header>
        <section aria-label="Interações">
          <h2 className="mb-2 text-sm font-semibold">Interações</h2>
          <InteracoesLista interacoes={interacoes} />
        </section>
        <section aria-label="Mensagens">
          <h2 className="mb-2 text-sm font-semibold">Mensagens</h2>
          {mensagens.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nenhuma mensagem.</p>
          ) : (
            <ol className="space-y-2" data-testid="historico-mensagens">
              {mensagens.map((m) =>
                m.tipo === "evento" ? (
                  <li key={m.id} className="text-center text-xs italic text-muted-foreground">{m.body} · {fmtData(m.created_at)}</li>
                ) : (
                  <li key={m.id} className={"max-w-[80%] rounded-lg px-3 py-2 text-sm " + (m.direction === "outbound" ? "ml-auto bg-primary/10" : "bg-muted")}>
                    <p className="whitespace-pre-wrap">{m.body}</p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">{fmtData(m.created_at)}</p>
                  </li>
                ),
              )}
            </ol>
          )}
        </section>
      </div>
    );
  }
  return <main className="mx-auto max-w-2xl p-4" data-testid="julia-historico">{corpo}</main>;
}
