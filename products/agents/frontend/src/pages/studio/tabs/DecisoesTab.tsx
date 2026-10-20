/**
 * Agent Studio — "Decisões" (Julia v2 CONTRACT §2.2): each decision the agent takes by a rule —
 * title, the rule text the model reads and its options with EXACTLY ONE default
 * (`agent_version_decisoes`). Draft-only edits.
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button, EmptyState, Textarea } from "@noctusai/lib/design-system";
import type { DecisaoRow } from "@/api/studio/types-julia";
import { ConflictBanner, RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useEditableRows } from "@/components/studio/useEditableRows";
import { useSaveDraftSet, useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";

const CHAVE_RE = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const REGRA_MAX = 8000;
const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

export default function DecisoesTab({ agentKey }: { agentKey: string }) {
  const { refs, versionId, isDraft } = useContentTarget(agentKey);
  const q = useVersionContent(agentKey, "decisoes", versionId);
  const save = useSaveDraftSet(agentKey, "decisoes", versionId);
  const ed = useEditableRows<DecisaoRow>(q.data?.itens, q.isPlaceholderData, versionId ?? "");
  const [novo, setNovo] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  if (refs.showSkeleton || (versionId && q.showSkeleton)) return <StudioLoading rows={3} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (q.isError) return <RestrictedNotice error={q.error} />;

  const patch = (i: number, p: Partial<DecisaoRow>) => ed.setRows((rows) => rows.map((r, j) => (j === i ? { ...r, ...p } : r)));

  function add() {
    if (!CHAVE_RE.test(novo)) {
      setErro("A chave usa letras minúsculas, números e hífens (ex.: escolher-tom).");
      return;
    }
    if (ed.rows.some((r) => r.chave === novo)) {
      setErro("Já existe uma decisão com esta chave.");
      return;
    }
    setErro(null);
    ed.setRows((rows) => [...rows, { chave: novo, titulo: novo, regra: "", opcoes: [] }]);
    setNovo("");
  }

  async function handleSave() {
    setErro(null);
    const ruim = ed.rows.find((r) => r.opcoes.length > 0 && r.opcoes.filter((o) => o.padrao).length !== 1);
    if (ruim) {
      setErro(`A decisão "${ruim.chave}" precisa ter exatamente uma opção padrão.`);
      return;
    }
    try {
      await save.mutateAsync({ itens: ed.rows.map(({ id: _id, ...r }) => r), baseSnapshot: ed.base });
      ed.markSaved(ed.rows);
      toast.success("Decisões salvas no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="decisoes-tab">
      <VersionBar agentKey={agentKey} rotulo="Decisões" />
      {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {ed.serverMoved && <ConflictBanner onReload={ed.reload} />}
      {ed.rows.length === 0 && <EmptyState message="Esta versão ainda não tem decisões." />}

      {ed.rows.map((r, i) => (
        <section key={r.chave} className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`decisao-${r.chave}`}>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{r.chave}</span>
            {isDraft && (
              <button type="button" className="ml-auto text-muted-foreground hover:text-destructive" aria-label={`Remover ${r.chave}`} onClick={() => ed.setRows((rows) => rows.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
          <div>
            <label htmlFor={`dt-${r.chave}`} className="mb-1 block text-xs font-medium">Título</label>
            <input id={`dt-${r.chave}`} className={INPUT_CLASS} readOnly={!isDraft} value={r.titulo} onChange={(e) => patch(i, { titulo: e.target.value })} />
          </div>
          <div>
            <label htmlFor={`dr-${r.chave}`} className="mb-1 block text-xs font-medium">Regra</label>
            <Textarea id={`dr-${r.chave}`} rows={4} maxLength={REGRA_MAX} readOnly={!isDraft} value={r.regra} onChange={(e) => patch(i, { regra: e.target.value })} />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium">Opções (uma é a padrão)</p>
            {r.opcoes.map((o, k) => (
              <div key={k} className="flex items-center gap-2">
                <input
                  type="radio"
                  name={`padrao-${r.chave}`}
                  aria-label={`Padrão: ${o.valor || `opção ${k + 1}`}`}
                  checked={o.padrao}
                  disabled={!isDraft}
                  onChange={() => patch(i, { opcoes: r.opcoes.map((x, n) => ({ ...x, padrao: n === k })) })}
                />
                <input aria-label={`Valor da opção ${k + 1}`} className={`${INPUT_CLASS} w-40 font-mono`} readOnly={!isDraft} value={o.valor} onChange={(e) => patch(i, { opcoes: r.opcoes.map((x, n) => (n === k ? { ...x, valor: e.target.value } : x)) })} />
                <input aria-label={`Rótulo da opção ${k + 1}`} className={INPUT_CLASS} readOnly={!isDraft} value={o.rotulo} onChange={(e) => patch(i, { opcoes: r.opcoes.map((x, n) => (n === k ? { ...x, rotulo: e.target.value } : x)) })} />
                {isDraft && (
                  <button type="button" className="text-muted-foreground hover:text-destructive" aria-label={`Remover opção ${k + 1}`} onClick={() => patch(i, { opcoes: r.opcoes.filter((_, n) => n !== k) })}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
            {isDraft && (
              <Button size="sm" variant="outline" onClick={() => patch(i, { opcoes: [...r.opcoes, { valor: "", rotulo: "", padrao: r.opcoes.length === 0 }] })}>
                <Plus className="mr-1 h-3.5 w-3.5" /> Adicionar opção
              </Button>
            )}
          </div>
        </section>
      ))}

      {isDraft && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <label htmlFor="decisoes-nova" className="mb-1 block text-xs font-medium">Nova decisão</label>
            <input id="decisoes-nova" className={`${INPUT_CLASS} font-mono`} value={novo} placeholder="chave-da-decisao" onChange={(e) => setNovo(e.target.value.toLowerCase())} />
          </div>
          <Button size="sm" variant="outline" onClick={add}>
            <Plus className="mr-1 h-4 w-4" /> Adicionar decisão
          </Button>
        </div>
      )}
      <SaveError message={erro} />
      {isDraft && (
        <div className="flex justify-end">
          <Button variant="primary" disabled={!ed.dirty || save.isPending || ed.serverMoved} onClick={handleSave} data-testid="decisoes-salvar">
            {save.isPending ? "Salvando..." : "Salvar no rascunho"}
          </Button>
        </div>
      )}
    </div>
  );
}
