/**
 * Agent Studio — "Ferramentas" (Julia v2 CONTRACT §2.2/§2.3): per tool on/off, the description the
 * model reads, the description of each parameter and the skill that must be opened first
 * (`agent_version_ferramentas`). The tool SCHEMA is code; only its words are rows.
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState, Switch, Textarea } from "@noctusai/lib/design-system";
import type { FerramentaRow } from "@/api/studio/types-julia";
import { ConflictBanner, RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useEditableRows } from "@/components/studio/useEditableRows";
import { useSaveDraftSet, useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";

const NOME_RE = /^[a-z][a-z0-9_]{1,63}$/;
const DESC_MAX = 2000;
const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

export default function FerramentasTab({ agentKey }: { agentKey: string }) {
  const { refs, versionId, isDraft } = useContentTarget(agentKey);
  const q = useVersionContent(agentKey, "ferramentas", versionId);
  const save = useSaveDraftSet(agentKey, "ferramentas", versionId);
  const ed = useEditableRows<FerramentaRow>(q.data?.itens, q.isPlaceholderData, versionId ?? "");
  const [novo, setNovo] = useState("");
  const [novoParam, setNovoParam] = useState<Record<number, string>>({});
  const [erro, setErro] = useState<string | null>(null);

  if (refs.showSkeleton || (versionId && q.showSkeleton)) return <StudioLoading rows={4} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (q.isError) return <RestrictedNotice error={q.error} />;

  const patch = (i: number, p: Partial<FerramentaRow>) => ed.setRows((rows) => rows.map((r, j) => (j === i ? { ...r, ...p } : r)));

  function add() {
    if (!NOME_RE.test(novo)) {
      setErro("O nome da ferramenta usa letras minúsculas, números e _ (ex.: buscar_imoveis).");
      return;
    }
    if (ed.rows.some((r) => r.ferramenta === novo)) {
      setErro("Esta ferramenta já está na lista.");
      return;
    }
    setErro(null);
    ed.setRows((rows) => [...rows, { ferramenta: novo, ativo: true, descricao: "", parametros: {}, obrigatoria_skill: null }]);
    setNovo("");
  }

  async function handleSave() {
    setErro(null);
    const semDescricao = ed.rows.find((r) => !r.descricao.trim());
    if (semDescricao) {
      setErro(`A ferramenta "${semDescricao.ferramenta}" precisa de uma descrição.`);
      return;
    }
    try {
      await save.mutateAsync({ itens: ed.rows.map(({ id: _id, ...r }) => r), baseSnapshot: ed.base });
      ed.markSaved(ed.rows);
      toast.success("Ferramentas salvas no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="ferramentas-tab">
      <VersionBar agentKey={agentKey} rotulo="Ferramentas" />
      {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {ed.serverMoved && <ConflictBanner onReload={ed.reload} />}
      {ed.rows.length === 0 && <EmptyState message="Esta versão ainda não tem ferramentas cadastradas." />}

      {ed.rows.map((r, i) => (
        <section key={r.ferramenta} className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`ferramenta-${r.ferramenta}`}>
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm font-semibold">{r.ferramenta}</span>
            <Badge variant={r.ativo ? "default" : "muted"}>{r.ativo ? "Ativa" : "Desligada"}</Badge>
            <div className="ml-auto flex items-center gap-2">
              <Switch
                checked={r.ativo}
                disabled={!isDraft}
                aria-label={`Ativar ${r.ferramenta}`}
                onCheckedChange={(v) => patch(i, { ativo: v })}
              />
              {isDraft && (
                <button type="button" className="text-muted-foreground hover:text-destructive" aria-label={`Remover ${r.ferramenta}`} onClick={() => ed.setRows((rows) => rows.filter((_, j) => j !== i))}>
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </div>
          </div>
          <div>
            <label htmlFor={`fd-${r.ferramenta}`} className="mb-1 block text-xs font-medium">Descrição para o modelo</label>
            <Textarea id={`fd-${r.ferramenta}`} rows={3} maxLength={DESC_MAX} readOnly={!isDraft} value={r.descricao} onChange={(e) => patch(i, { descricao: e.target.value })} />
          </div>
          <div>
            <label htmlFor={`fs-${r.ferramenta}`} className="mb-1 block text-xs font-medium">Skill que precisa ser aberta antes</label>
            <input
              id={`fs-${r.ferramenta}`}
              className={INPUT_CLASS}
              readOnly={!isDraft}
              placeholder="(nenhuma)"
              value={r.obrigatoria_skill ?? ""}
              onChange={(e) => patch(i, { obrigatoria_skill: e.target.value.trim() ? e.target.value.trim() : null })}
            />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium">Descrição dos parâmetros</p>
            {Object.entries(r.parametros).length === 0 && <p className="text-xs text-muted-foreground">Nenhum parâmetro descrito.</p>}
            {Object.entries(r.parametros).map(([p, d]) => (
              <div key={p} className="flex items-center gap-2">
                <span className="w-40 shrink-0 truncate font-mono text-xs">{p}</span>
                <input
                  aria-label={`Descrição de ${p}`}
                  className={INPUT_CLASS}
                  readOnly={!isDraft}
                  value={d}
                  onChange={(e) => patch(i, { parametros: { ...r.parametros, [p]: e.target.value } })}
                />
                {isDraft && (
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-destructive"
                    aria-label={`Remover parâmetro ${p}`}
                    onClick={() => patch(i, { parametros: Object.fromEntries(Object.entries(r.parametros).filter(([k]) => k !== p)) })}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
            {isDraft && (
              <div className="flex gap-2">
                <input
                  aria-label={`Novo parâmetro de ${r.ferramenta}`}
                  className={`${INPUT_CLASS} font-mono`}
                  placeholder="nome_do_parametro ou parametro.valor"
                  value={novoParam[i] ?? ""}
                  onChange={(e) => setNovoParam((p) => ({ ...p, [i]: e.target.value }))}
                />
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    const nome = (novoParam[i] ?? "").trim();
                    if (!nome || nome in r.parametros) return;
                    patch(i, { parametros: { ...r.parametros, [nome]: "" } });
                    setNovoParam((p) => ({ ...p, [i]: "" }));
                  }}
                >
                  Adicionar parâmetro
                </Button>
              </div>
            )}
          </div>
        </section>
      ))}

      {isDraft && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <label htmlFor="ferramentas-nova" className="mb-1 block text-xs font-medium">Nova ferramenta</label>
            <input id="ferramentas-nova" className={`${INPUT_CLASS} font-mono`} value={novo} placeholder="nome_da_ferramenta" onChange={(e) => setNovo(e.target.value.toLowerCase())} />
          </div>
          <Button size="sm" variant="outline" onClick={add}>
            <Plus className="mr-1 h-4 w-4" /> Adicionar ferramenta
          </Button>
        </div>
      )}
      <SaveError message={erro} />
      {isDraft && (
        <div className="flex justify-end">
          <Button variant="primary" disabled={!ed.dirty || save.isPending || ed.serverMoved} onClick={handleSave} data-testid="ferramentas-salvar">
            {save.isPending ? "Salvando..." : "Salvar no rascunho"}
          </Button>
        </div>
      )}
    </div>
  );
}
