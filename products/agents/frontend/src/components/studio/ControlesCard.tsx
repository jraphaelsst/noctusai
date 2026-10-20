/**
 * "Controles" (Julia v2 CONTRACT §5.3): the agent's 3-state switch (ligado / drenando / desligado),
 * the open-conversation count and the drain progress. A change always goes through a confirmation
 * dialog that says what happens to the conversations already open. The state on screen is the last
 * server answer; the server decides every turn (this card is not a gate).
 */
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Dialog, DialogBody, DialogFooter, DialogHeader } from "@noctusai/lib/design-system";
import type { Controle, ModoOperacao } from "@/api/studio/types-julia";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useControle, useSetControle } from "@/hooks/studio/useControle";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

const MODOS: ReadonlyArray<{ valor: ModoOperacao; rotulo: string }> = [
  { valor: "ligado", rotulo: "Ligado" },
  { valor: "drenando", rotulo: "Drenando" },
  { valor: "desligado", rotulo: "Desligado" },
];

export function consequencia(modo: ModoOperacao, c: Controle, dias: number): string {
  const abertas = c.threads_abertas;
  if (modo === "ligado") {
    return "O agente passa a atender novos leads e as conversas abertas.";
  }
  if (modo === "drenando") {
    return (
      `O agente deixa de aceitar novos leads. As ${abertas} conversa(s) aberta(s) continuam sendo atendidas; ` +
      `uma conversa em que o lead não responde há ${dias} dia(s) ou mais é encerrada (e fica fora da contagem). ` +
      "Quando todas terminarem, a drenagem está concluída."
    );
  }
  return (
    `O agente para de responder imediatamente, inclusive nas ${abertas} conversa(s) aberta(s). ` +
    "As mensagens dos leads continuam sendo registradas, sem resposta automática."
  );
}

function Drenagem({ c }: { c: Controle }) {
  const d = c.drenagem;
  return (
    <div className="space-y-1 text-sm" data-testid="controle-drenagem">
      <p>
        <span className="font-semibold tabular-nums" data-testid="controle-abertas">{c.threads_abertas}</span> conversa(s) aberta(s)
        {d.ociosas > 0 && <> · <span className="tabular-nums">{d.ociosas}</span> ociosa(s) há {c.dreno_inatividade_dias}+ dias</>}
      </p>
      {c.modo === "drenando" && (
        <p className="text-xs text-muted-foreground" data-testid="controle-drenagem-progresso">
          {d.concluida ? "Drenagem concluída: nenhuma conversa ativa." : `${d.efetivas} ainda ativa(s); a mais antiga está parada há ${d.idade_max_dias} dia(s).`}
        </p>
      )}
      {d.idades_dias.length > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="controle-idades">
          Dias desde a última mensagem do lead: {d.idades_dias.slice(0, 12).join(", ")}
          {d.idades_dias.length > 12 ? "…" : ""}
        </p>
      )}
    </div>
  );
}

export function ControlesCard({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const q = useControle(agentKey);
  const set = useSetControle(agentKey);
  const [alvo, setAlvo] = useState<ModoOperacao | null>(null);
  const [dias, setDias] = useState<string>("");
  const [erro, setErro] = useState<string | null>(null);

  if (q.showSkeleton) return <StudioLoading rows={2} testId="controles-skeleton" />;
  if (q.isError) return <StudioError error={q.error} onRetry={q.refetch} />;
  const c = q.data;
  if (!c) return null;
  const diasAtuais = c.dreno_inatividade_dias;
  const diasNum = dias.trim() === "" ? diasAtuais : Number(dias);
  const diasValidos = Number.isInteger(diasNum) && diasNum >= 1 && diasNum <= 365;

  async function confirmar() {
    if (!alvo) return;
    setErro(null);
    try {
      await set.mutateAsync({ modo: alvo, ...(alvo === "drenando" || dias.trim() ? { dreno_inatividade_dias: diasNum } : {}) });
      toast.success(`Agente ${MODOS.find((m) => m.valor === alvo)?.rotulo.toLowerCase()}.`);
      setAlvo(null);
      setDias("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function salvarDias() {
    setErro(null);
    try {
      await set.mutateAsync({ modo: c!.modo, dreno_inatividade_dias: diasNum });
      toast.success("Prazo de inatividade salvo.");
      setDias("");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4" data-testid="controles-card">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">Controles</h2>
        <Badge variant={c.modo === "ligado" ? "default" : c.modo === "drenando" ? "outline" : "muted"} data-testid="controle-modo">
          {MODOS.find((m) => m.valor === c.modo)?.rotulo}
        </Badge>
        <span className="text-xs text-muted-foreground">{c.aceita_novos_leads ? "Aceita novos leads" : "Não aceita novos leads"}</span>
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>

      <div className="inline-flex rounded-md border border-input p-0.5" role="radiogroup" aria-label="Modo de operação">
        {MODOS.map((m) => (
          <button
            key={m.valor}
            type="button"
            role="radio"
            aria-checked={c.modo === m.valor}
            disabled={!isAdmin || set.isPending}
            data-testid={`controle-modo-${m.valor}`}
            onClick={() => {
              if (m.valor === c.modo) return;
              setErro(null);
              setAlvo(m.valor);
            }}
            className={cn(
              "rounded px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-60",
              c.modo === m.valor ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {m.rotulo}
          </button>
        ))}
      </div>
      {!isAdmin && <p className="text-xs text-muted-foreground">Somente administradores da organização alteram o modo.</p>}

      <Drenagem c={c} />

      {isAdmin && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="controle-dias" className="mb-1 block text-xs font-medium">Encerrar conversa parada após (dias)</label>
            <input
              id="controle-dias"
              type="number"
              min={1}
              max={365}
              className="h-9 w-28 rounded-md border border-input bg-background px-3 text-sm"
              value={dias === "" ? String(diasAtuais) : dias}
              onChange={(e) => setDias(e.target.value)}
            />
          </div>
          <Button size="sm" variant="outline" disabled={dias === "" || !diasValidos || set.isPending} onClick={salvarDias} data-testid="controle-dias-salvar">
            Salvar prazo
          </Button>
        </div>
      )}
      {erro && !alvo && (
        <p className="text-sm text-destructive" role="alert" data-testid="controle-erro">{erro}</p>
      )}

      <Dialog open={alvo !== null} onClose={() => setAlvo(null)} title="Alterar o modo do agente" className="max-w-lg">
        <DialogHeader>
          <h2 className="text-base font-semibold">
            Mudar para “{MODOS.find((m) => m.valor === alvo)?.rotulo}”?
          </h2>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {alvo && (
            <p className="text-sm" data-testid="controle-consequencia">
              {consequencia(alvo, c, diasNum)}
            </p>
          )}
          {alvo === "drenando" && (
            <div>
              <label htmlFor="controle-dias-dialog" className="mb-1 block text-xs font-medium">Dias de inatividade para encerrar</label>
              <input
                id="controle-dias-dialog"
                type="number"
                min={1}
                max={365}
                className="h-9 w-28 rounded-md border border-input bg-background px-3 text-sm"
                value={dias === "" ? String(diasAtuais) : dias}
                onChange={(e) => setDias(e.target.value)}
              />
            </div>
          )}
          {erro && (
            <p className="text-sm text-destructive" role="alert" data-testid="controle-erro-dialog">{erro}</p>
          )}
        </DialogBody>
        <DialogFooter className="gap-2">
          <Button variant="ghost" onClick={() => setAlvo(null)}>Cancelar</Button>
          <Button variant="primary" disabled={set.isPending || (alvo === "drenando" && !diasValidos)} onClick={confirmar} data-testid="controle-confirmar">
            {set.isPending ? "Aplicando..." : "Confirmar"}
          </Button>
        </DialogFooter>
      </Dialog>
    </section>
  );
}
