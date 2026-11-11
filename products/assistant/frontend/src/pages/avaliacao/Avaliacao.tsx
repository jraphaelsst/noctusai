/**
 * `/avaliacao` -- the owner labels, BLIND, whether a message deals with scheduling; the summary tab then compares the
 * labels with the model's verdict (counts only). Admin only. The labelling screen never receives the verdict: the
 * backend's blind sample omits it. Third-party message text is shown here, so the notice below is always visible and no
 * message text is ever logged or put in a URL / storage.
 */
import { useMemo, useState } from "react";
import { AIFeedbackButtons, useIsOrgAdmin } from "@noctusai/lib/design-system";
import { ShieldAlert } from "lucide-react";

import { ROTULOS, useAmostra, useConcordancia, useProgresso, useRegistrarRotulo, type Rotulo } from "./hooks";
import Resumo from "./Resumo";

const CHOICES = [
  { value: "agendamento", label: "Agendamento", shortcut: "1" },
  { value: "nao_agendamento", label: "Não é agendamento", shortcut: "2" },
  { value: "nao_sei", label: "Não sei", shortcut: "3" },
];

function erroDe(e: unknown): string {
  return e instanceof Error && e.message ? e.message : "Não foi possível concluir. Tente de novo.";
}

function Rotular() {
  const amostra = useAmostra();
  const progresso = useProgresso();
  const salvar = useRegistrarRotulo();
  // Items consumed in this draw. The draw itself is static (see useAmostra); the server excludes labelled messages
  // from the NEXT draw.
  const [feitas, setFeitas] = useState<ReadonlySet<string>>(new Set());

  const fila = useMemo(
    () => (amostra.data?.itens ?? []).filter((i) => !feitas.has(i.intake_id)),
    [amostra.data, feitas],
  );
  const atual = fila[0];

  const escolher = (valor: string) => {
    if (!atual || salvar.isPending || !ROTULOS.includes(valor as Rotulo)) return;
    salvar.mutate(
      { intake_id: atual.intake_id, output_id: atual.output_id, rotulo: valor as Rotulo, rodada: 1 },
      { onSuccess: () => setFeitas((prev) => new Set(prev).add(atual.intake_id)) },
    );
  };

  if (!amostra.data && amostra.isPending) {
    return <p className="text-sm text-muted-foreground" data-testid="avaliacao-carregando">Carregando mensagens…</p>;
  }
  if (amostra.isError && !amostra.data) {
    return (
      <div className="space-y-2" data-testid="avaliacao-erro" role="alert">
        <p className="text-sm text-destructive">Não foi possível carregar as mensagens: {erroDe(amostra.error)}</p>
        <button type="button" className="text-sm underline" onClick={() => void amostra.refetch()}>Tentar de novo</button>
      </div>
    );
  }

  const total = progresso.data?.rotuladas;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground" data-testid="avaliacao-progresso">
        {progresso.data ? `${total} rotulada${total === 1 ? "" : "s"} por você` : "Contando suas rotulagens…"}
        {atual ? ` · ${fila.length} restante${fila.length === 1 ? "" : "s"} neste lote` : ""}
      </p>
      {!atual ? (
        <div className="space-y-2" data-testid="avaliacao-vazio">
          <p className="text-sm text-foreground">
            {amostra.data?.itens.length ? "Lote concluído." : "Não há mensagens classificadas para rotular agora."}
          </p>
          <button
            type="button"
            className="text-sm underline"
            disabled={amostra.isFetching}
            onClick={() => { setFeitas(new Set()); void amostra.refetch(); }}
          >
            {amostra.isFetching ? "Buscando…" : "Buscar novas mensagens"}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <blockquote className="whitespace-pre-wrap rounded-lg border border-border bg-card p-4 text-base text-foreground" data-testid="avaliacao-mensagem">
            {atual.texto}
          </blockquote>
          <p className="text-sm text-muted-foreground">Esta mensagem trata de agendar, marcar, remarcar ou cancelar um horário?</p>
          <AIFeedbackButtons
            output_ref={`intake:${atual.intake_id}`}
            choices={CHOICES}
            selected={null}
            onChoose={escolher}
            disabled={salvar.isPending}
          />
          {salvar.isError && (
            <p className="text-sm text-destructive" role="alert" data-testid="avaliacao-erro-salvar">
              Não foi possível salvar o rótulo: {erroDe(salvar.error)} A mensagem continua aqui; escolha de novo.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function Avaliacao() {
  const isAdmin = useIsOrgAdmin();
  const [aba, setAba] = useState<"rotular" | "resumo">("rotular");
  const concordancia = useConcordancia(isAdmin && aba === "resumo");
  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground" data-testid="avaliacao-acesso-restrito">
        Esta página é restrita a administradores.
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Avaliação do classificador</h1>
        <p className="text-sm text-muted-foreground">Você rotula sem ver a resposta do modelo; a comparação aparece só no resumo.</p>
      </div>
      <p className="flex items-start gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-sm text-muted-foreground" data-testid="avaliacao-aviso-terceiros">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
        Conteúdo de terceiros, uso restrito à avaliação. Não copie nem compartilhe estas mensagens.
      </p>
      <div role="tablist" className="flex gap-2 border-b border-border">
        {(["rotular", "resumo"] as const).map((a) => (
          <button
            key={a}
            type="button"
            role="tab"
            aria-selected={aba === a}
            data-testid={`avaliacao-aba-${a}`}
            onClick={() => setAba(a)}
            className={`px-3 py-2 text-sm ${aba === a ? "border-b-2 border-primary font-medium text-foreground" : "text-muted-foreground"}`}
          >
            {a === "rotular" ? "Rotular" : "Resumo"}
          </button>
        ))}
      </div>
      {aba === "rotular" ? <Rotular /> : <Resumo query={concordancia} />}
    </div>
  );
}
