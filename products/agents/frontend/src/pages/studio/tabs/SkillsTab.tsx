/**
 * Agent Studio — "Skills" (CONTRACT §G, §D1): the draft's skills — list +
 * editor (nome, descrição with the 1024 counter, corpo) + attached reference
 * files (add / edit / delete). Skills are served just-in-time by the
 * `abrir_skill` tool (§E3); only nome + descrição reach the master prompt.
 * Without a draft (or for members) everything is read-only.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, FileText, Plus, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, EmptyState } from "@noctusai/lib/design-system";
import {
  CAMINHO_RE,
  SKILL_DESCRICAO_MAX,
  SKILL_NOME_MAX,
  SLUG_RE,
  type Skill,
  type SkillFileSummary,
} from "@/api/studio/types";
import { PromptMarkdownField } from "@/components/studio/PromptMarkdownField";
import { SkillFilesUploadDialog } from "@/components/studio/SkillFilesUploadDialog";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import {
  useAgentVersionRefs,
  useCreateSkill,
  useDeleteSkill,
  useDeleteSkillFile,
  useSkillFile,
  useUpdateSkill,
  useUpsertSkillFile,
  useVersion,
} from "@/hooks/studio/useVersions";
import { useIsAdmin } from "@/hooks/useIsAdmin";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-70";

const NOVA = "__nova__";

interface SkillForm {
  nome: string;
  descricao: string;
  corpo: string;
  ordem: number;
  ativo: boolean;
}

const emptySkill = (ordem: number): SkillForm => ({ nome: "", descricao: "", corpo: "", ordem, ativo: true });

function skillToForm(s: Skill): SkillForm {
  return { nome: s.nome, descricao: s.descricao, corpo: s.corpo, ordem: s.ordem, ativo: s.ativo };
}

function validateSkill(f: SkillForm): string | null {
  if (!SLUG_RE.test(f.nome) || f.nome.length > SKILL_NOME_MAX)
    return `Nome inválido — minúsculas, números e hífens, até ${SKILL_NOME_MAX} caracteres.`;
  if (f.descricao.trim().length < 1 || f.descricao.length > SKILL_DESCRICAO_MAX)
    return `A descrição é obrigatória (até ${SKILL_DESCRICAO_MAX} caracteres) — é o que o modelo lê para decidir usar a skill.`;
  return null;
}

// ── Files ─────────────────────────────────────────────────────────────────────

function SkillFilesPanel({
  agentKey,
  draftId,
  skill,
  editable,
}: {
  agentKey: string;
  draftId: string | null;
  skill: Skill;
  editable: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null); // file id or NOVA
  const file = useSkillFile(agentKey, skill.id, selected && selected !== NOVA ? selected : null);
  const upsert = useUpsertSkillFile(agentKey, draftId);
  const del = useDeleteSkillFile(agentKey, draftId);
  const [caminho, setCaminho] = useState("");
  const [titulo, setTitulo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    setSelected(null);
  }, [skill.id]);

  useEffect(() => {
    if (selected === NOVA) {
      setCaminho("references/");
      setTitulo("");
      setConteudo("");
      setErro(null);
    }
  }, [selected]);

  useEffect(() => {
    if (!file.data || file.isPlaceholderData || selected === NOVA) return;
    setCaminho(file.data.caminho);
    setTitulo(file.data.titulo ?? "");
    setConteudo(file.data.conteudo);
    setErro(null);
  }, [file.data, file.isPlaceholderData, selected]);

  async function handleSave() {
    if (!CAMINHO_RE.test(caminho) || caminho.includes("..")) {
      setErro("Caminho inválido — minúsculas, números, “.”, “_”, “-” e “/”, sem “..”.");
      return;
    }
    try {
      const saved = await upsert.mutateAsync({
        skillId: skill.id,
        file: { caminho, titulo: titulo.trim() || null, conteudo },
      });
      toast.success(`Arquivo ${saved.caminho} salvo.`);
      setSelected(saved.id);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleDelete(f: SkillFileSummary) {
    if (!window.confirm(`Remover o arquivo ${f.caminho}?`)) return;
    try {
      await del.mutateAsync({ skillId: skill.id, fileId: f.id });
      if (selected === f.id) setSelected(null);
      toast.success("Arquivo removido.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-3" data-testid="skill-files">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">Arquivos de referência</h3>
        <span className="text-xs text-muted-foreground">lidos sob demanda com ler_arquivo_skill</span>
        {editable && (
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowUpload(true)} data-testid="skill-files-upload-toggle">
              <Upload className="mr-1 h-3.5 w-3.5" /> Enviar arquivos
            </Button>
            <Button size="sm" variant="outline" onClick={() => setSelected(NOVA)}>
              <Plus className="mr-1 h-3.5 w-3.5" /> Arquivo
            </Button>
          </div>
        )}
      </div>
      {showUpload && (
        <SkillFilesUploadDialog agentKey={agentKey} draftId={draftId} skillId={skill.id} onClose={() => setShowUpload(false)} />
      )}
      {skill.arquivos.length === 0 && selected !== NOVA ? (
        <p className="text-xs text-muted-foreground">Nenhum arquivo anexado.</p>
      ) : (
        <ul className="divide-y divide-border rounded border border-border">
          {skill.arquivos.map((f) => (
            <li key={f.id} className={cn("flex items-center gap-2 px-2 py-1.5 text-xs", selected === f.id && "bg-accent")}>
              <FileText className="h-3.5 w-3.5 text-muted-foreground" />
              <button type="button" className="font-mono hover:underline" onClick={() => setSelected(f.id)}>
                {f.caminho}
              </button>
              {f.titulo && <span className="text-muted-foreground">— {f.titulo}</span>}
              <span className="ml-auto tabular-nums text-muted-foreground">{f.chars.toLocaleString("pt-BR")} caracteres</span>
              {editable && (
                <Button size="icon" variant="ghost" aria-label={`Remover ${f.caminho}`} onClick={() => handleDelete(f)}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="space-y-2 rounded border border-border p-2" data-testid="skill-file-editor">
          {selected !== NOVA && file.showSkeleton ? (
            <StudioLoading rows={2} />
          ) : selected !== NOVA && file.isError ? (
            <StudioError error={file.error} onRetry={file.refetch} />
          ) : (
            <>
              <div className="grid gap-2 sm:grid-cols-2">
                <input
                  aria-label="Caminho do arquivo"
                  className={`${INPUT_CLASS} font-mono`}
                  value={caminho}
                  disabled={!editable || selected !== NOVA}
                  onChange={(e) => setCaminho(e.target.value.toLowerCase())}
                />
                <input
                  aria-label="Título do arquivo"
                  className={INPUT_CLASS}
                  value={titulo}
                  placeholder="Título (opcional)"
                  disabled={!editable}
                  onChange={(e) => setTitulo(e.target.value)}
                />
              </div>
              <PromptMarkdownField
                aria-label="Conteúdo do arquivo"
                value={conteudo}
                onChange={setConteudo}
                readOnly={!editable}
                rows={10}
              />
              {erro && <p className="text-xs text-destructive">{erro}</p>}
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                  Fechar
                </Button>
                {editable && (
                  <Button size="sm" variant="primary" onClick={handleSave} disabled={upsert.isPending}>
                    {upsert.isPending ? "Salvando..." : "Salvar arquivo"}
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab ───────────────────────────────────────────────────────────────────────

export default function SkillsTab({ agentKey }: { agentKey: string }) {
  const isAdmin = useIsAdmin();
  const [params, setParams] = useSearchParams();
  const refs = useAgentVersionRefs(agentKey);
  const target = refs.draft ?? refs.ativa;
  const version = useVersion(agentKey, target?.id);
  const draftId = refs.draft?.id ?? null;
  const create = useCreateSkill(agentKey, draftId);
  const update = useUpdateSkill(agentKey, draftId);
  const remove = useDeleteSkill(agentKey, draftId);

  const data = version.isPlaceholderData ? undefined : version.data;
  const editable = isAdmin && !!data && data.status === "rascunho";
  const skills = [...(data?.skills ?? [])].sort((a, b) => a.ordem - b.ordem || a.nome.localeCompare(b.nome));
  const selectedId = params.get("skill");
  const selected = skills.find((s) => s.id === selectedId) ?? null;
  const creating = selectedId === NOVA;

  const [form, setForm] = useState<SkillForm>(emptySkill(10));
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    setErro(null);
    if (creating) setForm(emptySkill(((skills[skills.length - 1]?.ordem ?? 0) as number) + 10));
    else if (selected) setForm(skillToForm(selected));
    // `skills` identity changes every render; the selected skill's server copy is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [creating, selected?.id, selected?.nome, selected?.descricao, selected?.corpo, selected?.ordem, selected?.ativo]);

  function select(id: string | null) {
    const next = new URLSearchParams(params);
    if (id) next.set("skill", id);
    else next.delete("skill");
    setParams(next);
  }

  if (refs.showSkeleton || (target && version.showSkeleton)) return <StudioLoading rows={4} />;
  if (refs.isError) return <StudioError error={refs.error} onRetry={refs.refetch} />;
  if (version.isError) return <StudioError error={version.error} onRetry={version.refetch} />;
  if (!target) return <EmptyState message="Este agente ainda não tem versões." />;

  async function handleSave() {
    const problem = validateSkill(form);
    setErro(problem);
    if (problem) return;
    try {
      if (creating) {
        const created = await create.mutateAsync(form);
        toast.success(`Skill ${created.nome} criada.`);
        select(created.id);
      } else if (selected) {
        const patch: Partial<SkillForm> = {};
        (Object.keys(form) as (keyof SkillForm)[]).forEach((k) => {
          if (form[k] !== skillToForm(selected)[k]) (patch as Record<string, unknown>)[k] = form[k];
        });
        if (Object.keys(patch).length === 0) {
          toast.info("Nada para salvar.");
          return;
        }
        await update.mutateAsync({ skillId: selected.id, patch });
        toast.success("Skill salva.");
      }
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleDelete(s: Skill) {
    if (!window.confirm(`Remover a skill ${s.nome} e seus arquivos do rascunho?`)) return;
    try {
      await remove.mutateAsync({ skillId: s.id });
      select(null);
      toast.success("Skill removida.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  /**
   * Reorders `skills` (position `idx` ↔ `idx + delta`), then renumbers by
   * position (10, 20, …, mirroring `PromptTab.tsx`'s `rowsToPayload`) —
   * safer than swapping the two `ordem` values directly, which is a no-op
   * when two skills share an `ordem` (the list's own tie-break falls back
   * to `nome`, so a tie is reachable). Only the skills whose `ordem`
   * actually changes get PATCHed.
   */
  async function moveSkill(idx: number, delta: -1 | 1) {
    const j = idx + delta;
    if (j < 0 || j >= skills.length) return;
    const next = [...skills];
    [next[idx], next[j]] = [next[j], next[idx]];
    const patches = next
      .map((s, i) => ({ skillId: s.id, ordem: (i + 1) * 10 }))
      .filter((p) => skills.find((s) => s.id === p.skillId)?.ordem !== p.ordem);
    try {
      await Promise.all(patches.map((p) => update.mutateAsync({ skillId: p.skillId, patch: { ordem: p.ordem } })));
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const pending = create.isPending || update.isPending;

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]" data-testid="skills-tab">
      <aside className="space-y-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Skills · v{target.versao}</h2>
          {version.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
          {editable && (
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => select(NOVA)} data-testid="skills-nova">
              <Plus className="mr-1 h-3.5 w-3.5" /> Skill
            </Button>
          )}
        </div>
        {!editable && (
          <p className="text-xs text-muted-foreground">
            {refs.draft ? "Somente administradores editam o rascunho." : "Versão publicada — somente leitura."}
          </p>
        )}
        {skills.length === 0 ? (
          <EmptyState message="Nenhuma skill nesta versão." />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border bg-card">
            {skills.map((s, idx) => (
              <li key={s.id} className="flex items-center gap-1 px-1">
                <button
                  type="button"
                  onClick={() => select(s.id)}
                  className={cn("min-w-0 flex-1 px-2 py-2 text-left hover:bg-accent", s.id === selectedId && "bg-accent")}
                  data-testid={`skill-item-${s.nome}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-medium">{s.nome}</span>
                    {!s.ativo && <Badge variant="muted">Inativa</Badge>}
                    {s.ativo && !s.corpo.trim() && <Badge variant="destructive">Sem corpo</Badge>}
                  </div>
                  <p className="line-clamp-2 text-[11px] text-muted-foreground">{s.descricao}</p>
                </button>
                {editable && (
                  <div className="flex flex-col">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Subir ${s.nome}`}
                      disabled={idx === 0 || update.isPending}
                      onClick={() => moveSkill(idx, -1)}
                      data-testid={`skill-move-up-${s.nome}`}
                    >
                      <ArrowUp className="h-3 w-3" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Descer ${s.nome}`}
                      disabled={idx === skills.length - 1 || update.isPending}
                      onClick={() => moveSkill(idx, 1)}
                      data-testid={`skill-move-down-${s.nome}`}
                    >
                      <ArrowDown className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="min-w-0">
        {!selected && !creating ? (
          <EmptyState message="Selecione uma skill para ver ou editar." />
        ) : (
          <div className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="skill-editor">
            <div className="grid gap-3 sm:grid-cols-[1fr_100px_auto]">
              <div>
                <label className="mb-1 block text-xs font-medium" htmlFor="skill-nome">
                  Nome
                </label>
                <input
                  id="skill-nome"
                  className={`${INPUT_CLASS} font-mono`}
                  value={form.nome}
                  maxLength={SKILL_NOME_MAX}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, nome: e.target.value.toLowerCase() })}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium" htmlFor="skill-ordem">
                  Ordem
                </label>
                <input
                  id="skill-ordem"
                  type="number"
                  className={INPUT_CLASS}
                  value={form.ordem}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, ordem: Number(e.target.value) })}
                />
              </div>
              <label className="flex items-end gap-1 pb-2 text-xs">
                <input
                  type="checkbox"
                  checked={form.ativo}
                  disabled={!editable}
                  onChange={(e) => setForm({ ...form, ativo: e.target.checked })}
                />
                ativa
              </label>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" htmlFor="skill-descricao">
                Descrição (entra no prompt — o modelo decide usar a skill por ela)
              </label>
              <PromptMarkdownField
                id="skill-descricao"
                value={form.descricao}
                onChange={(v) => setForm({ ...form, descricao: v })}
                max={SKILL_DESCRICAO_MAX}
                readOnly={!editable}
                rows={3}
                mono={false}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium" htmlFor="skill-corpo">
                Corpo (devolvido por abrir_skill)
              </label>
              <PromptMarkdownField
                id="skill-corpo"
                value={form.corpo}
                onChange={(v) => setForm({ ...form, corpo: v })}
                readOnly={!editable}
                rows={16}
              />
            </div>
            {erro && (
              <p className="text-sm text-destructive" role="alert">
                {erro}
              </p>
            )}
            {editable && (
              <div className="flex gap-2">
                {selected && (
                  <Button variant="ghost" onClick={() => handleDelete(selected)} disabled={remove.isPending}>
                    <Trash2 className="mr-1 h-4 w-4 text-destructive" /> Remover skill
                  </Button>
                )}
                <Button variant="primary" className="ml-auto" onClick={handleSave} disabled={pending} data-testid="skill-save">
                  {pending ? "Salvando..." : creating ? "Criar skill" : "Salvar skill"}
                </Button>
              </div>
            )}
            {selected && <SkillFilesPanel agentKey={agentKey} draftId={draftId} skill={selected} editable={editable} />}
          </div>
        )}
      </section>
    </div>
  );
}
