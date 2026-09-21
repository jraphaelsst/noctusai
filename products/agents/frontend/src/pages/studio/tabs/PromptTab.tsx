/**
 * Agent Studio — "Prompt" (CONTRACT §G): the DRAFT's ordered prompt sections.
 * ▲▼ reorder, add, remove, toggle ativo, edit título/chave/conteúdo in a
 * monospace markdown field with char/token counter. Save = full replace via
 * `PUT .../draft/sections` (§D1). Without a draft the active version is shown
 * read-only with a "Criar rascunho" CTA. Deep link: `?secao=<id>&chave=<chave>`
 * expands + scrolls to a section (the inspector's click-through).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, FilePlus2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { SLUG_RE, type Section, type SectionInput } from "@/api/studio/types";
import { estimateTokens } from "@/components/studio/compiledSegments";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { StudioEmpty, StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { VersionStatusBadge } from "@/components/studio/VersionStatusBadge";
import { useAgentVersionRefs, useCreateDraft, useSaveSections, useVersion } from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-70";

interface Row extends SectionInput {
  uid: string;
}

let uidSeq = 0;
const nextUid = () => `nova-${++uidSeq}`;

function toRows(secoes: Section[]): Row[] {
  return [...secoes]
    .sort((a, b) => a.ordem - b.ordem)
    .map((s) => ({ uid: s.id, id: s.id, chave: s.chave, titulo: s.titulo, ordem: s.ordem, conteudo: s.conteudo, ativo: s.ativo }));
}

/** Renumbers `ordem` by position (10, 20, …) — the list order IS the order. */
function rowsToPayload(rows: Row[]): SectionInput[] {
  return rows.map((r, i) => {
    const out: SectionInput = {
      chave: r.chave.trim(),
      titulo: r.titulo.trim(),
      ordem: (i + 1) * 10,
      conteudo: r.conteudo,
      ativo: r.ativo,
    };
    if (r.id) out.id = r.id;
    return out;
  });
}

function validate(rows: Row[]): string | null {
  const seen = new Set<string>();
  for (const r of rows) {
    const chave = r.chave.trim();
    if (!SLUG_RE.test(chave)) return `Chave inválida: “${chave || "(vazia)"}” — use minúsculas, números e hífens.`;
    if (seen.has(chave)) return `Chave repetida: “${chave}”.`;
    seen.add(chave);
    if (!r.titulo.trim()) return `A seção “${chave}” precisa de um título.`;
  }
  return null;
}

export default function PromptTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const [params] = useSearchParams();
  const refs = useAgentVersionRefs(agentKey);
  const target = refs.draft ?? refs.ativa;
  const version = useVersion(agentKey, target?.id);
  const createDraft = useCreateDraft(agentKey);
  const save = useSaveSections(agentKey);

  const editable = isAdmin && !!refs.draft && version.data?.status === "rascunho";
  const [rows, setRows] = useState<Row[]>([]);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const seededFor = useRef<string | null>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const data = version.isPlaceholderData ? undefined : version.data;
  const pristine = useMemo(() => (data ? toRows(data.secoes) : []), [data]);

  // Seed the form from the server copy — on first load, on version change, and
  // after every save (the PUT response replaces the cached version).
  useEffect(() => {
    if (!data) return;
    setRows(pristine);
    if (seededFor.current !== data.id) {
      seededFor.current = data.id;
      setErro(null);
    }
  }, [data, pristine]);

  // Inspector click-through: expand + scroll the linked section.
  const deepId = params.get("secao");
  const deepChave = params.get("chave");
  const deepUid = useMemo(() => {
    const hit = rows.find((r) => (deepId && r.id === deepId) || (deepChave && r.chave === deepChave));
    return hit?.uid ?? null;
  }, [rows, deepId, deepChave]);
  useEffect(() => {
    if (!deepUid) return;
    setOpen((prev) => new Set(prev).add(deepUid));
    const t = window.setTimeout(() => rowRefs.current[deepUid]?.scrollIntoView?.({ behavior: "smooth", block: "start" }), 50);
    return () => window.clearTimeout(t);
  }, [deepUid]);

  if (refs.showSkeleton || (target && version.showSkeleton)) return <StudioLoading rows={4} />;
  if (refs.isError) return <StudioError error={refs.error} onRetry={refs.refetch} />;
  if (version.isError) return <StudioError error={version.error} onRetry={version.refetch} />;

  async function handleCreateDraft() {
    try {
      const d = await createDraft.mutateAsync();
      toast.success(`Rascunho v${d.versao} criado.`);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const draftCta = isAdmin && !refs.draft && (
    <Button variant="primary" onClick={handleCreateDraft} disabled={createDraft.isPending} data-testid="prompt-criar-rascunho">
      <FilePlus2 className="mr-1 h-4 w-4" /> {createDraft.isPending ? "Criando..." : "Criar rascunho"}
    </Button>
  );

  if (!target) {
    return <StudioEmpty titulo="Este agente ainda não tem versões.">{draftCta}</StudioEmpty>;
  }

  const dirty = JSON.stringify(rowsToPayload(rows)) !== JSON.stringify(rowsToPayload(pristine));
  const totalTokens = rows.filter((r) => r.ativo).reduce((acc, r) => acc + estimateTokens(r.conteudo), 0);

  function patch(uid: string, p: Partial<Row>) {
    setRows((prev) => prev.map((r) => (r.uid === uid ? { ...r, ...p } : r)));
  }
  function move(idx: number, delta: -1 | 1) {
    setRows((prev) => {
      const next = [...prev];
      const j = idx + delta;
      if (j < 0 || j >= next.length) return prev;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  }
  function add() {
    const uid = nextUid();
    setRows((prev) => [...prev, { uid, chave: "", titulo: "", ordem: 0, conteudo: "", ativo: true }]);
    setOpen((prev) => new Set(prev).add(uid));
  }
  function remove(uid: string) {
    setRows((prev) => prev.filter((r) => r.uid !== uid));
  }
  function toggleOpen(uid: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid);
      else next.add(uid);
      return next;
    });
  }

  async function handleSave() {
    const problem = validate(rows);
    setErro(problem);
    if (problem) return;
    try {
      await save.mutateAsync({ secoes: rowsToPayload(rows) });
      toast.success("Seções salvas no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="prompt-tab">
      <div className="flex flex-wrap items-center gap-2">
        {version.data && <VersionStatusBadge status={version.data.status} />}
        <span className="text-sm text-muted-foreground">
          v{target.versao} · {rows.length} seções · ~{totalTokens.toLocaleString("pt-BR")} tokens ativos
        </span>
        {version.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        {dirty && <Badge variant="outline">Alterações não salvas</Badge>}
        <div className="ml-auto flex gap-2">
          {draftCta}
          {editable && (
            <>
              <Button variant="outline" onClick={add} data-testid="prompt-add-section">
                <Plus className="mr-1 h-4 w-4" /> Seção
              </Button>
              <Button variant="ghost" onClick={() => setRows(pristine)} disabled={!dirty || save.isPending}>
                Descartar alterações
              </Button>
              <Button variant="primary" onClick={handleSave} disabled={!dirty || save.isPending} data-testid="prompt-save">
                {save.isPending ? "Salvando..." : "Salvar seções"}
              </Button>
            </>
          )}
        </div>
      </div>

      {!editable && (
        <p className="text-xs text-muted-foreground" data-testid="prompt-readonly">
          {refs.draft
            ? "Somente administradores editam o rascunho."
            : "Versão publicada — somente leitura. Crie um rascunho para editar."}
        </p>
      )}
      {erro && (
        <p className="text-sm text-destructive" role="alert" data-testid="prompt-erro">
          {erro}
        </p>
      )}

      {rows.length === 0 ? (
        <StudioEmpty titulo="Nenhuma seção ainda.">
          {editable && <p className="text-xs">Adicione a primeira seção do prompt.</p>}
        </StudioEmpty>
      ) : (
        <div className="space-y-2">
          {rows.map((r, idx) => {
            const isOpen = open.has(r.uid);
            const highlighted = r.uid === deepUid;
            return (
              <div
                key={r.uid}
                ref={(el) => {
                  rowRefs.current[r.uid] = el;
                }}
                className={cn(
                  "scroll-mt-4 rounded-lg border bg-card",
                  highlighted ? "border-primary ring-2 ring-primary/30" : "border-border",
                  !r.ativo && "opacity-60",
                )}
                data-testid={`prompt-section-${r.chave || r.uid}`}
              >
                <div className="flex items-center gap-2 px-3 py-2">
                  <button type="button" onClick={() => toggleOpen(r.uid)} aria-label={isOpen ? "Recolher" : "Expandir"}>
                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  </button>
                  <span className="w-6 text-right text-xs tabular-nums text-muted-foreground">{idx + 1}</span>
                  <span className="text-sm font-medium">{r.titulo || <em className="text-muted-foreground">sem título</em>}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{r.chave}</span>
                  {!r.ativo && <Badge variant="muted">Inativa</Badge>}
                  {r.ativo && !r.conteudo.trim() && <Badge variant="destructive">Vazia — bloqueia publicação</Badge>}
                  <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">~{estimateTokens(r.conteudo)} tokens</span>
                  {editable && (
                    <>
                      <Button size="icon" variant="ghost" aria-label="Subir" disabled={idx === 0} onClick={() => move(idx, -1)}>
                        <ArrowUp className="h-3.5 w-3.5" />
                      </Button>
                      <Button size="icon" variant="ghost" aria-label="Descer" disabled={idx === rows.length - 1} onClick={() => move(idx, 1)}>
                        <ArrowDown className="h-3.5 w-3.5" />
                      </Button>
                      <label className="flex items-center gap-1 text-xs">
                        <input type="checkbox" checked={r.ativo} onChange={(e) => patch(r.uid, { ativo: e.target.checked })} />
                        ativa
                      </label>
                      <Button size="icon" variant="ghost" aria-label="Remover seção" onClick={() => remove(r.uid)}>
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </>
                  )}
                </div>
                {isOpen && (
                  <div className="space-y-3 border-t border-border p-3">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="mb-1 block text-xs font-medium" htmlFor={`sec-titulo-${r.uid}`}>
                          Título
                        </label>
                        <input
                          id={`sec-titulo-${r.uid}`}
                          className={INPUT_CLASS}
                          value={r.titulo}
                          disabled={!editable}
                          onChange={(e) => patch(r.uid, { titulo: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium" htmlFor={`sec-chave-${r.uid}`}>
                          Chave
                        </label>
                        <input
                          id={`sec-chave-${r.uid}`}
                          className={`${INPUT_CLASS} font-mono`}
                          value={r.chave}
                          disabled={!editable}
                          onChange={(e) => patch(r.uid, { chave: e.target.value.toLowerCase() })}
                        />
                      </div>
                    </div>
                    <PromptMarkdownField
                      aria-label={`Conteúdo da seção ${r.titulo || r.chave}`}
                      value={r.conteudo}
                      onChange={(v) => patch(r.uid, { conteudo: v })}
                      readOnly={!editable}
                      rows={12}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
