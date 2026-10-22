/**
 * Agent Studio — "Textos do sistema" (Julia v2 CONTRACT §2.3): every string the runtime says or
 * shows the model that is not a prompt section — tool results, hand-off notes, fallbacks, headings.
 * They are DB rows of the version (`agent_version_textos`); this tab edits the DRAFT's set, and the
 * platform-wide texts (`textos_plataforma`) below it. Nothing is cached as truth: a save PUTs the
 * set and the server answer repaints the screen.
 */
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState, Textarea } from "@noctusai/lib/design-system";
import type { TextoRow } from "@/api/studio/types-julia";
import { ConflictBanner, RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useEditableRows } from "@/components/studio/useEditableRows";
import { usePlataformaTextos, useSaveDraftSet, useSetPlataformaTextos, useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";
import { GeradoBadge } from "@/components/studio/CompletudeCard";
import { useItensGerados } from "@/hooks/studio/useGeracoes";

const CHAVE_RE = /^[a-z0-9]+(\.[a-z0-9_]+)+$/;
const TEXTO_MAX = 8000;
const INPUT_CLASS =
  "h-9 w-full rounded-md border border-input bg-background px-3 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary/50";

function categoria(chave: string): string {
  return chave.split(".")[0] || "outros";
}

function PlataformaTextos() {
  const q = usePlataformaTextos();
  const save = useSetPlataformaTextos();
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<string | null>(null);
  if (q.showSkeleton) return <StudioLoading rows={2} />;
  if (q.isError) return <RestrictedNotice error={q.error} />;
  const itens = q.data?.itens ?? [];
  const dirty = Object.keys(edits).length > 0;

  async function handleSave() {
    setErro(null);
    try {
      const all = Object.fromEntries(itens.map((i) => [i.chave, edits[i.chave] ?? i.conteudo]));
      await save.mutateAsync({ itens: all });
      setEdits({});
      toast.success("Textos da plataforma salvos.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="textos-plataforma">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold">Textos da plataforma</h2>
        <Badge variant="outline">valem para todos os agentes · sem rascunho</Badge>
        {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      {itens.length === 0 ? (
        <EmptyState message="Nenhum texto da plataforma cadastrado." />
      ) : (
        itens.map((i) => (
          <div key={i.chave}>
            <label htmlFor={`pt-${i.chave}`} className="mb-1 block font-mono text-xs">{i.chave}</label>
            <Textarea
              id={`pt-${i.chave}`}
              rows={3}
              maxLength={TEXTO_MAX}
              value={edits[i.chave] ?? i.conteudo}
              onChange={(e) => setEdits((p) => ({ ...p, [i.chave]: e.target.value }))}
            />
          </div>
        ))
      )}
      <SaveError message={erro} />
      <div className="flex justify-end">
        <Button size="sm" variant="primary" disabled={!dirty || save.isPending} onClick={handleSave} data-testid="textos-plataforma-salvar">
          {save.isPending ? "Salvando..." : "Salvar textos da plataforma"}
        </Button>
      </div>
    </section>
  );
}

export default function TextosTab({ agentKey }: { agentKey: string }) {
  const gerados = useItensGerados(agentKey);
  const { refs, versionId, isDraft } = useContentTarget(agentKey);
  const q = useVersionContent(agentKey, "textos", versionId);
  const save = useSaveDraftSet(agentKey, "textos", versionId);
  const ed = useEditableRows<TextoRow>(q.data?.itens, q.isPlaceholderData, versionId ?? "");
  const [novaChave, setNovaChave] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  if (refs.showSkeleton || (versionId && q.showSkeleton)) return <StudioLoading rows={4} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (q.isError) return <RestrictedNotice error={q.error} />;

  const grupos = new Map<string, number[]>();
  ed.rows.forEach((r, i) => grupos.set(categoria(r.chave), [...(grupos.get(categoria(r.chave)) ?? []), i]));

  function update(i: number, conteudo: string) {
    ed.setRows((rows) => rows.map((r, j) => (j === i ? { ...r, conteudo } : r)));
  }

  function add() {
    if (!CHAVE_RE.test(novaChave)) {
      setErro("A chave usa letras minúsculas e números separados por ponto (ex.: contexto.cabecalho).");
      return;
    }
    if (ed.rows.some((r) => r.chave === novaChave)) {
      setErro("Já existe um texto com esta chave.");
      return;
    }
    setErro(null);
    ed.setRows((rows) => [...rows, { chave: novaChave, conteudo: "" }]);
    setNovaChave("");
  }

  async function handleSave() {
    setErro(null);
    try {
      const itens = ed.rows.map(({ id: _id, ...r }) => r);
      await save.mutateAsync({ itens, baseSnapshot: ed.base });
      ed.markSaved(ed.rows);
      toast.success("Textos salvos no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="textos-tab">
      <VersionBar agentKey={agentKey} rotulo="Textos do sistema" />
      {q.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {ed.serverMoved && <ConflictBanner onReload={ed.reload} />}

      {ed.rows.length === 0 ? (
        <EmptyState message="Esta versão ainda não tem textos do sistema." />
      ) : (
        [...grupos.entries()].map(([cat, idxs]) => (
          <section key={cat} className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid={`textos-grupo-${cat}`}>
            <h2 className="text-sm font-semibold capitalize">{cat}</h2>
            {idxs.map((i) => {
              const r = ed.rows[i];
              return (
                <div key={r.chave}>
                  <div className="mb-1 flex items-center gap-2">
                    <label htmlFor={`texto-${r.chave}`} className="font-mono text-xs">{r.chave}</label>
                    {isDraft && <GeradoBadge estado={gerados.textos?.[r.chave]} />}
                    {!r.conteudo.trim() && <Badge variant="outline">vazio</Badge>}
                    {isDraft && (
                      <button
                        type="button"
                        className="ml-auto text-muted-foreground hover:text-destructive"
                        aria-label={`Remover ${r.chave}`}
                        onClick={() => ed.setRows((rows) => rows.filter((_, j) => j !== i))}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                  <Textarea
                    id={`texto-${r.chave}`}
                    rows={3}
                    maxLength={TEXTO_MAX}
                    readOnly={!isDraft}
                    value={r.conteudo}
                    onChange={(e) => update(i, e.target.value)}
                  />
                  <p className="text-right text-[11px] text-muted-foreground">{r.conteudo.length}/{TEXTO_MAX}</p>
                </div>
              );
            })}
          </section>
        ))
      )}

      {isDraft && (
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-[16rem] flex-1">
            <label htmlFor="textos-nova-chave" className="mb-1 block text-xs font-medium">Nova chave</label>
            <input id="textos-nova-chave" className={INPUT_CLASS} value={novaChave} placeholder="categoria.nome" onChange={(e) => setNovaChave(e.target.value.toLowerCase())} />
          </div>
          <Button size="sm" variant="outline" onClick={add}>
            <Plus className="mr-1 h-4 w-4" /> Adicionar texto
          </Button>
        </div>
      )}
      <SaveError message={erro} />
      {isDraft && (
        <div className="flex justify-end">
          <Button variant="primary" disabled={!ed.dirty || save.isPending || ed.serverMoved} onClick={handleSave} data-testid="textos-salvar">
            {save.isPending ? "Salvando..." : "Salvar no rascunho"}
          </Button>
        </div>
      )}

      <PlataformaTextos />
    </div>
  );
}
