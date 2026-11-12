/**
 * "Contatos permitidos" (migration 084, owner 2026-11-12): the agent's phone allow-list. EMPTY = the agent answers every
 * number; with numbers it answers ONLY them (the on/off is the mode switch above). The list on screen is the last server
 * answer (the cache write draws the change at once and the server's answer commits it); the server decides every message.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@noctusai/lib/design-system";
import type { Controle } from "@/api/studio/types-julia";
import { useSetControle } from "@/hooks/studio/useControle";
import { errorMessage } from "@/lib/errors";

/** Same plausibility rule as the server (`normalizar_e164`): 8..15 digits. Returns the E.164 form or null. */
export function normalizarTelefone(bruto: string): string | null {
  const digitos = bruto.replace(/\D/g, "");
  return digitos.length >= 8 && digitos.length <= 15 ? `+${digitos}` : null;
}

export function ContatosPermitidosSection({ agentKey, c, isAdmin }: { agentKey: string; c: Controle; isAdmin: boolean }) {
  const set = useSetControle(agentKey);
  const [novo, setNovo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const lista = c.contatos_permitidos ?? [];
  const vazia = lista.length === 0;

  async function salvar(proxima: string[], ok: string): Promise<boolean> {
    setErro(null);
    try {
      await set.mutateAsync({ modo: c.modo, contatos_permitidos: proxima });
      toast.success(ok);
      return true;
    } catch (err) {
      setErro(errorMessage(err));
      return false;
    }
  }

  async function adicionar() {
    const n = normalizarTelefone(novo);
    if (!n) {
      setErro("Informe um número válido, com DDI e DDD (ex.: +55 11 99999-0000).");
      return;
    }
    if (lista.includes(n)) {
      setErro("Esse número já está na lista.");
      return;
    }
    if (await salvar([...lista, n], "Número adicionado.")) setNovo("");
  }

  return (
    <div className="space-y-2" data-testid="contatos-permitidos">
      <h3 className="text-sm font-semibold">Contatos permitidos</h3>
      <p className="text-xs text-muted-foreground" data-testid="contatos-permitidos-resumo">
        {vazia
          ? "Lista vazia: o agente responde qualquer número (quando está ligado)."
          : `O agente responde somente a ${lista.length} número(s) da lista; os demais não recebem resposta.`}
      </p>
      {!vazia && (
        <ul className="space-y-1" data-testid="contatos-permitidos-lista">
          {lista.map((n) => (
            <li key={n} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`contato-permitido-${n}`}>
              <span className="tabular-nums">{n}</span>
              {isAdmin && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={set.isPending}
                  aria-label={`Remover ${n}`}
                  onClick={() => void salvar(lista.filter((x) => x !== n), "Número removido.")}
                >
                  Remover
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {isAdmin ? (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label htmlFor="contato-permitido-novo" className="mb-1 block text-xs font-medium">Número (com DDI e DDD)</label>
            <input
              id="contato-permitido-novo"
              type="tel"
              inputMode="tel"
              placeholder="+55 11 99999-0000"
              className="h-9 w-64 rounded-md border border-input bg-background px-3 text-sm"
              value={novo}
              onChange={(e) => {
                setNovo(e.target.value);
                setErro(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void adicionar();
              }}
            />
          </div>
          <Button size="sm" variant="outline" disabled={!novo.trim() || set.isPending} onClick={() => void adicionar()} data-testid="contato-permitido-adicionar">
            {set.isPending ? "Salvando..." : "Adicionar"}
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Somente administradores da organização alteram a lista.</p>
      )}
      {erro && <p className="text-sm text-destructive" role="alert" data-testid="contatos-permitidos-erro">{erro}</p>}
    </div>
  );
}
