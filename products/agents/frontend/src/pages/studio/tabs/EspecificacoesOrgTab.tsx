/**
 * Agent Studio — "Especificações da org" (Julia v2 CONTRACT §2.6, Q2): the ORG's own values for the
 * placeholders the platform definition declares (agency name, regions, price bands, …). This is the
 * only content an org admin edits; the platform's prompt, rules and tool descriptions are never
 * shown. A text that contradicts a platform-locked rule is refused by the server
 * (422 `spec_conflita_com_regra_fixa`) and the refusal is shown on the offending field.
 */
import { useState } from "react";
import { Lock } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState, Textarea } from "@noctusai/lib/design-system";
import { SaveError } from "@/components/studio/ConteudoChrome";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useOrgSpecs, useUpdateOrgSpecs } from "@/hooks/studio/useConteudo";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { ApiError, errorMessage } from "@/lib/errors";

/** Labels of the platform-locked blocks. Names only: the rule text is never sent to an org. */
export const REGRA_FIXA_ROTULO: Record<string, string> = {
  divulgacao_ia: "Aviso de que é um assistente virtual",
  opt_out: "Pedido do lead para parar de receber mensagens",
  escalonamento_humano: "Passagem da conversa para uma pessoa",
  escopo_imobiliario: "Atendimento restrito a assuntos imobiliários",
};

const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

interface FieldError {
  chave: string | null;
  mensagem: string;
  conflitos: string[];
}

function parseError(err: unknown, chaves: string[]): FieldError {
  const mensagem = errorMessage(err);
  const conflitos = err instanceof ApiError && Array.isArray(err.field("conflitos")) ? (err.field("conflitos") as string[]) : [];
  const chave = chaves.find((c) => mensagem.startsWith(`${c}:`)) ?? null;
  return { chave, mensagem, conflitos };
}

export default function EspecificacoesOrgTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const q = useOrgSpecs(agentKey);
  const save = useUpdateOrgSpecs(agentKey);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<FieldError | null>(null);

  if (q.showSkeleton) return <StudioLoading rows={3} />;
  if (q.isError) return <StudioError error={q.error} onRetry={q.refetch} />;
  const data = q.data;
  if (!data) return null;
  if (data.declaradas.length === 0) {
    return <EmptyState message="A plataforma ainda não pediu nenhuma especificação para a sua organização." />;
  }

  const atual = Object.fromEntries(data.valores.map((v) => [v.chave, v.valor]));
  const valorDe = (chave: string) => edits[chave] ?? atual[chave] ?? "";
  const dirty = Object.keys(edits).some((k) => edits[k] !== (atual[k] ?? ""));

  async function handleSave() {
    setErro(null);
    try {
      const valores = Object.fromEntries(data!.declaradas.map((d) => [d.chave, valorDe(d.chave)]));
      await save.mutateAsync({ valores });
      setEdits({});
      toast.success("Especificações salvas.");
    } catch (err) {
      setErro(parseError(err, data!.declaradas.map((d) => d.chave)));
    }
  }

  return (
    <div className="space-y-4" data-testid="especificacoes-org-tab">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted-foreground">Preencha como o agente deve falar da sua empresa.</span>
        {data.faltando.length > 0 ? (
          <Badge variant="outline" data-testid="specs-faltando">{data.faltando.length} obrigatória(s) faltando</Badge>
        ) : (
          <Badge variant="default">Tudo preenchido</Badge>
        )}
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      <p className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="specs-bloco-travado">
        <Lock className="h-3.5 w-3.5" /> As regras da plataforma (aviso de assistente virtual, parar de receber mensagens, passagem para uma pessoa, escopo imobiliário) são fixas e não podem ser alteradas aqui.
      </p>

      {data.declaradas.map((d) => {
        const faltando = data.faltando.includes(d.chave);
        const fieldErr = erro?.chave === d.chave ? erro : null;
        return (
          <div key={d.chave} className="space-y-1 rounded-lg border border-border bg-card p-4" data-testid={`spec-org-${d.chave}`}>
            <label htmlFor={`so-${d.chave}`} className="flex items-center gap-2 text-sm font-medium">
              {d.rotulo}
              {d.obrigatoria && <span className="text-xs text-muted-foreground">obrigatória</span>}
              {faltando && <Badge variant="outline">faltando</Badge>}
            </label>
            {d.descricao && <p className="text-xs text-muted-foreground">{d.descricao}</p>}
            {d.tipo === "texto_longo" ? (
              <Textarea id={`so-${d.chave}`} rows={5} readOnly={!isAdmin} value={valorDe(d.chave)} onChange={(e) => setEdits((p) => ({ ...p, [d.chave]: e.target.value }))} />
            ) : (
              <input id={`so-${d.chave}`} className={INPUT_CLASS} readOnly={!isAdmin} value={valorDe(d.chave)} onChange={(e) => setEdits((p) => ({ ...p, [d.chave]: e.target.value }))} />
            )}
            {d.exemplo && <p className="text-[11px] text-muted-foreground">Exemplo: {d.exemplo}</p>}
            {fieldErr && (
              <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive" role="alert" data-testid={`spec-org-erro-${d.chave}`}>
                <p>{fieldErr.mensagem}</p>
                {fieldErr.conflitos.length > 0 && (
                  <ul className="ml-4 list-disc">
                    {fieldErr.conflitos.map((c) => (
                      <li key={c}>Bloco fixo da plataforma: {REGRA_FIXA_ROTULO[c] ?? "regra fixa"}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        );
      })}

      {erro && erro.chave === null && <SaveError message={erro.mensagem} />}
      {isAdmin && (
        <div className="flex justify-end">
          <Button variant="primary" disabled={!dirty || save.isPending} onClick={handleSave} data-testid="specs-org-salvar">
            {save.isPending ? "Salvando..." : "Salvar especificações"}
          </Button>
        </div>
      )}
    </div>
  );
}
