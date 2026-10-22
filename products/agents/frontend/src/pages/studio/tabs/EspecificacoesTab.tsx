/**
 * Agent Studio — "Especificações declaradas" (Julia v2 CONTRACT §2.6): the `{{org.chave}}`
 * placeholders the definition uses, declared per version (`agent_version_specs`): label, help,
 * type, required. The VALUES belong to each org (org admin form), never to this screen.
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button, EmptyState, Select, Switch, Textarea } from "@noctusai/lib/design-system";
import type { SpecDefRow } from "@/api/studio/types-julia";
import { ConflictBanner, RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useEditableRows } from "@/components/studio/useEditableRows";
import { useSaveDraftSet, useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";
import { GeradoBadge } from "@/components/studio/CompletudeCard";
import { useItensGerados } from "@/hooks/studio/useGeracoes";

const CHAVE_RE = /^[a-z][a-z0-9_]{1,63}$/;
const TIPOS: ReadonlyArray<{ valor: string; rotulo: string }> = [
  { valor: "texto", rotulo: "Texto curto" },
  { valor: "texto_longo", rotulo: "Texto longo" },
];
const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

export default function EspecificacoesTab({ agentKey }: { agentKey: string }) {
  const gerados = useItensGerados(agentKey);
  const { refs, versionId, isDraft } = useContentTarget(agentKey);
  const q = useVersionContent(agentKey, "specs", versionId);
  const save = useSaveDraftSet(agentKey, "specs", versionId);
  const ed = useEditableRows<SpecDefRow>(q.data?.itens, q.isPlaceholderData, versionId ?? "");
  const [novo, setNovo] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  if (refs.showSkeleton || (versionId && q.showSkeleton)) return <StudioLoading rows={3} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (q.isError) return <RestrictedNotice error={q.error} />;

  const patch = (i: number, p: Partial<SpecDefRow>) => ed.setRows((rows) => rows.map((r, j) => (j === i ? { ...r, ...p } : r)));

  function add() {
    if (!CHAVE_RE.test(novo)) {
      setErro("A chave usa letras minúsculas, números e _ (ex.: nome_imobiliaria).");
      return;
    }
    if (ed.rows.some((r) => r.chave === novo)) {
      setErro("Já existe uma especificação com esta chave.");
      return;
    }
    setErro(null);
    ed.setRows((rows) => [...rows, { chave: novo, rotulo: novo, descricao: "", tipo: "texto", obrigatoria: true, exemplo: null }]);
    setNovo("");
  }

  async function handleSave() {
    setErro(null);
    try {
      await save.mutateAsync({ itens: ed.rows.map(({ id: _id, ...r }) => r), baseSnapshot: ed.base });
      ed.markSaved(ed.rows);
      toast.success("Especificações salvas no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="especificacoes-tab">
      <VersionBar agentKey={agentKey} rotulo="Especificações declaradas" />
      <p className="text-xs text-muted-foreground">
        Cada organização preenche estes campos em “Especificações da org”. O texto do agente os usa como {"{{org.chave}}"}.
      </p>
      {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {ed.serverMoved && <ConflictBanner onReload={ed.reload} />}
      {ed.rows.length === 0 && <EmptyState message="Esta versão não declara especificações da organização." />}

      {ed.rows.map((r, i) => (
        <section key={r.chave} className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`spec-${r.chave}`}>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{`{{org.${r.chave}}}`}</span>
            {isDraft && <GeradoBadge estado={gerados.specs?.[r.chave]} />}
            {isDraft && (
              <button type="button" className="ml-auto text-muted-foreground hover:text-destructive" aria-label={`Remover ${r.chave}`} onClick={() => ed.setRows((rows) => rows.filter((_, j) => j !== i))}>
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor={`sr-${r.chave}`} className="mb-1 block text-xs font-medium">Rótulo</label>
              <input id={`sr-${r.chave}`} className={INPUT_CLASS} readOnly={!isDraft} value={r.rotulo} onChange={(e) => patch(i, { rotulo: e.target.value })} />
            </div>
            <div>
              <label htmlFor={`st-${r.chave}`} className="mb-1 block text-xs font-medium">Tipo</label>
              <Select id={`st-${r.chave}`} disabled={!isDraft} value={r.tipo} onChange={(e) => patch(i, { tipo: e.target.value })}>
                {TIPOS.map((t) => (
                  <option key={t.valor} value={t.valor}>{t.rotulo}</option>
                ))}
              </Select>
            </div>
          </div>
          <div>
            <label htmlFor={`sd-${r.chave}`} className="mb-1 block text-xs font-medium">Ajuda para a organização</label>
            <Textarea id={`sd-${r.chave}`} rows={2} readOnly={!isDraft} value={r.descricao} onChange={(e) => patch(i, { descricao: e.target.value })} />
          </div>
          <div>
            <label htmlFor={`se-${r.chave}`} className="mb-1 block text-xs font-medium">Exemplo (visível na ajuda)</label>
            <input id={`se-${r.chave}`} className={INPUT_CLASS} readOnly={!isDraft} value={r.exemplo ?? ""} onChange={(e) => patch(i, { exemplo: e.target.value || null })} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={r.obrigatoria} disabled={!isDraft} aria-label={`Obrigatória: ${r.chave}`} onCheckedChange={(v) => patch(i, { obrigatoria: v })} />
            Obrigatória (bloqueia ligar o agente enquanto vazia)
          </label>
        </section>
      ))}

      {isDraft && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <label htmlFor="specs-nova" className="mb-1 block text-xs font-medium">Nova especificação</label>
            <input id="specs-nova" className={`${INPUT_CLASS} font-mono`} value={novo} placeholder="chave_da_especificacao" onChange={(e) => setNovo(e.target.value.toLowerCase())} />
          </div>
          <Button size="sm" variant="outline" onClick={add}>
            <Plus className="mr-1 h-4 w-4" /> Adicionar especificação
          </Button>
        </div>
      )}
      <SaveError message={erro} />
      {isDraft && (
        <div className="flex justify-end">
          <Button variant="primary" disabled={!ed.dirty || save.isPending || ed.serverMoved} onClick={handleSave} data-testid="especificacoes-salvar">
            {save.isPending ? "Salvando..." : "Salvar no rascunho"}
          </Button>
        </div>
      )}
    </div>
  );
}
