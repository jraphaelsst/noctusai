/**
 * Agent Studio — `/studio/biblioteca-skills/:chave`: ONE library skill (platform admin only).
 * Edit its nome/descricao, browse its versions, and work the DRAFT: `descricao_modelo` (the short text
 * the model always sees), `corpo` (the full playbook, loaded on demand by `abrir_skill`), notes and the
 * reference files (`ler_arquivo_skill`). Published/archived versions are read-only. Publishing never
 * moves agents — they keep the version they pinned until re-pinned.
 */
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, FilePlus2, Plus, Rocket, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useConfirm } from "@noctusai/lib/components";
import { Badge, Button, EmptyState, Select, Textarea } from "@noctusai/lib/design-system";
import type { BibliotecaSkill, SkillArquivo, SkillVersao } from "@/api/studio/types-julia";
import { ConflictBanner, RestrictedNotice, SaveError } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useBuffered } from "@/components/studio/useBuffered";
import {
  useBibliotecaSkills,
  useCriarRascunhoSkill,
  useDescartarRascunhoSkill,
  useEditarSkill,
  usePublicarSkill,
  useRemoverArquivoSkill,
  useSalvarArquivoSkill,
  useSalvarRascunhoSkill,
  useSkillVersao,
  useSkillVersoes,
} from "@/hooks/studio/useBiblioteca";
import { errorMessage } from "@/lib/errors";
import { SKILLS_BIBLIOTECA_HREF } from "./skillsRoutes";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

const STATUS_LABEL = { rascunho: "Rascunho", publicada: "Publicada", arquivada: "Arquivada" } as const;

// ── skill header (nome / descricao) ─────────────────────────────────────────────

function CabecalhoSkill({ skill }: { skill: BibliotecaSkill }) {
  const editar = useEditarSkill(skill.chave);
  const buf = useBuffered({ nome: skill.nome, descricao: skill.descricao ?? "" });
  const [erro, setErro] = useState<string | null>(null);

  async function salvar() {
    setErro(null);
    try {
      const r = await editar.mutateAsync({ nome: buf.value.nome.trim(), descricao: buf.value.descricao.trim() || null });
      buf.markSaved({ nome: r.nome, descricao: r.descricao ?? "" });
      toast.success("Skill atualizada.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="skill-cabecalho">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold">{skill.chave}</span>
        <Badge variant={skill.versao_publicada !== null ? "default" : "muted"}>
          {skill.versao_publicada !== null ? `Publicada v${skill.versao_publicada}` : "Sem versão publicada"}
        </Badge>
        {skill.tem_rascunho && <Badge variant="outline">rascunho em edição</Badge>}
      </div>
      {buf.conflict && <ConflictBanner onReload={buf.reload} />}
      <div>
        <label htmlFor="skill-edit-nome" className="mb-1 block text-xs font-medium">Nome</label>
        <input id="skill-edit-nome" className={INPUT_CLASS} maxLength={200} value={buf.value.nome} onChange={(e) => buf.setValue({ ...buf.value, nome: e.target.value })} />
      </div>
      <div>
        <label htmlFor="skill-edit-descricao" className="mb-1 block text-xs font-medium">Descrição (para quem administra a biblioteca)</label>
        <input id="skill-edit-descricao" className={INPUT_CLASS} maxLength={1024} value={buf.value.descricao} onChange={(e) => buf.setValue({ ...buf.value, descricao: e.target.value })} />
      </div>
      <SaveError message={erro} />
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={salvar} disabled={!buf.dirty || !buf.value.nome.trim() || editar.isPending} data-testid="skill-salvar-cabecalho">
          Salvar dados da skill
        </Button>
      </div>
    </section>
  );
}

// ── reference files ─────────────────────────────────────────────────────────────

function ArquivoEditor({ arquivo, chave, versaoId, editavel }: { arquivo: SkillArquivo; chave: string; versaoId: string; editavel: boolean }) {
  const salvar = useSalvarArquivoSkill(chave, versaoId);
  const remover = useRemoverArquivoSkill(versaoId);
  const confirm = useConfirm();
  const buf = useBuffered({ titulo: arquivo.titulo ?? "", conteudo: arquivo.conteudo });
  const [erro, setErro] = useState<string | null>(null);

  async function handleSalvar() {
    setErro(null);
    try {
      await salvar.mutateAsync({ caminho: arquivo.caminho, titulo: buf.value.titulo.trim() || null, conteudo: buf.value.conteudo });
      buf.markSaved(buf.value);
      toast.success(`Arquivo ${arquivo.caminho} salvo.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleRemover() {
    if (!(await confirm({ title: `Remover o arquivo ${arquivo.caminho}?`, tone: "danger", confirmLabel: "Remover" }))) return;
    setErro(null);
    try {
      await remover.mutateAsync({ caminho: arquivo.caminho });
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <li className="space-y-2 rounded-md border border-border p-3" data-testid={`skill-arquivo-${arquivo.caminho}`}>
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs font-semibold">{arquivo.caminho}</span>
        {editavel && (
          <button type="button" className="ml-auto text-muted-foreground hover:text-destructive" aria-label={`Remover ${arquivo.caminho}`} onClick={handleRemover} disabled={remover.isPending}>
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
      {buf.conflict && <ConflictBanner onReload={buf.reload} />}
      <input className={INPUT_CLASS} aria-label={`Título de ${arquivo.caminho}`} placeholder="Título (opcional)" maxLength={200} value={buf.value.titulo} readOnly={!editavel} onChange={(e) => buf.setValue({ ...buf.value, titulo: e.target.value })} />
      <Textarea aria-label={`Conteúdo de ${arquivo.caminho}`} rows={8} className="font-mono text-xs" maxLength={120000} value={buf.value.conteudo} readOnly={!editavel} onChange={(e) => buf.setValue({ ...buf.value, conteudo: e.target.value })} />
      <SaveError message={erro} />
      {editavel && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={handleSalvar} disabled={!buf.dirty || salvar.isPending}>Salvar arquivo</Button>
        </div>
      )}
    </li>
  );
}

function NovoArquivo({ chave, versaoId, existentes }: { chave: string; versaoId: string; existentes: string[] }) {
  const salvar = useSalvarArquivoSkill(chave, versaoId);
  const [caminho, setCaminho] = useState("");
  const [titulo, setTitulo] = useState("");
  const [conteudo, setConteudo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const cam = caminho.trim();
  const duplicado = existentes.includes(cam);

  async function adicionar() {
    setErro(null);
    try {
      await salvar.mutateAsync({ caminho: cam, titulo: titulo.trim() || null, conteudo });
      setCaminho("");
      setTitulo("");
      setConteudo("");
      toast.success(`Arquivo ${cam} adicionado.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-dashed border-border p-3" data-testid="skill-arquivo-novo">
      <p className="text-xs font-medium">Adicionar arquivo de referência</p>
      <input className={INPUT_CLASS} aria-label="Caminho do novo arquivo" placeholder="caminho, ex.: referencias/objecoes.md" value={caminho} onChange={(e) => setCaminho(e.target.value)} />
      <input className={INPUT_CLASS} aria-label="Título do novo arquivo" placeholder="Título (opcional)" maxLength={200} value={titulo} onChange={(e) => setTitulo(e.target.value)} />
      <Textarea aria-label="Conteúdo do novo arquivo" rows={5} className="font-mono text-xs" value={conteudo} onChange={(e) => setConteudo(e.target.value)} />
      {duplicado && <p className="text-xs text-muted-foreground">Já existe um arquivo com esse caminho — salvar substitui o conteúdo.</p>}
      <SaveError message={erro} />
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={adicionar} disabled={!cam || salvar.isPending} data-testid="skill-arquivo-adicionar">
          <Plus className="mr-1 h-3.5 w-3.5" /> Adicionar arquivo
        </Button>
      </div>
    </div>
  );
}

// ── version view / draft editor ───────────────────────────────────────────────────

function VersaoView({ versao, chave }: { versao: SkillVersao; chave: string }) {
  const editavel = versao.status === "rascunho";
  const confirm = useConfirm();
  const salvar = useSalvarRascunhoSkill(chave, versao.id);
  const publicar = usePublicarSkill(chave, versao.id);
  const descartar = useDescartarRascunhoSkill(chave);
  const buf = useBuffered({ descricao_modelo: versao.descricao_modelo, corpo: versao.corpo, notas: versao.notas ?? "" });
  const [erro, setErro] = useState<string | null>(null);

  async function handleSalvar() {
    setErro(null);
    try {
      const v = await salvar.mutateAsync({ descricao_modelo: buf.value.descricao_modelo, corpo: buf.value.corpo, notas: buf.value.notas });
      buf.markSaved({ descricao_modelo: v.descricao_modelo, corpo: v.corpo, notas: v.notas ?? "" });
      toast.success("Rascunho salvo.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handlePublicar() {
    setErro(null);
    const ok = await confirm({
      title: `Publicar a v${versao.versao} de ${chave}?`,
      description:
        "A versão publicada anterior será arquivada. Os agentes que já fixaram uma versão continuam nela até você fixar a nova; eles passam a mostrar “nova versão disponível”.",
      confirmLabel: "Publicar",
    });
    if (!ok) return;
    try {
      if (buf.dirty) {
        const v = await salvar.mutateAsync({ descricao_modelo: buf.value.descricao_modelo, corpo: buf.value.corpo, notas: buf.value.notas });
        buf.markSaved({ descricao_modelo: v.descricao_modelo, corpo: v.corpo, notas: v.notas ?? "" });
      }
      await publicar.mutateAsync();
      toast.success(`Skill ${chave} v${versao.versao} publicada.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function handleDescartar() {
    if (!(await confirm({ title: `Descartar o rascunho v${versao.versao}?`, description: "O conteúdo do rascunho será perdido.", tone: "danger", confirmLabel: "Descartar" }))) return;
    setErro(null);
    try {
      await descartar.mutateAsync({ versaoId: versao.id });
      toast.success("Rascunho descartado.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <div className="space-y-4" data-testid="skill-versao">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={editavel ? "default" : "muted"} data-testid="skill-estado">
          {editavel ? `Rascunho v${versao.versao} · editável` : `${STATUS_LABEL[versao.status]} v${versao.versao} · somente leitura`}
        </Badge>
        {editavel && (
          <div className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="primary" onClick={handlePublicar} disabled={publicar.isPending || salvar.isPending} data-testid="skill-publicar">
              <Rocket className="mr-1 h-3.5 w-3.5" /> Publicar
            </Button>
            <Button size="sm" variant="ghost" onClick={handleDescartar} disabled={descartar.isPending} data-testid="skill-descartar">
              <Trash2 className="mr-1 h-3.5 w-3.5" /> Descartar rascunho
            </Button>
          </div>
        )}
      </div>
      <SaveError message={erro} />
      {buf.conflict && <ConflictBanner onReload={buf.reload} />}

      <div>
        <label htmlFor="skill-desc-modelo" className="mb-1 block text-xs font-medium">Descrição para o modelo</label>
        <p className="mb-1 text-xs text-muted-foreground">É o que o modelo vê sempre, em toda conversa — diga em poucas linhas quando abrir esta skill.</p>
        <Textarea id="skill-desc-modelo" rows={3} maxLength={1024} value={buf.value.descricao_modelo} readOnly={!editavel} onChange={(e) => buf.setValue({ ...buf.value, descricao_modelo: e.target.value })} />
      </div>
      <div>
        <label htmlFor="skill-corpo" className="mb-1 block text-xs font-medium">Corpo (playbook completo)</label>
        <p className="mb-1 text-xs text-muted-foreground">Carregado sob demanda quando o modelo abre a skill (abrir_skill).</p>
        <Textarea id="skill-corpo" rows={22} maxLength={60000} className="font-mono text-xs" value={buf.value.corpo} readOnly={!editavel} onChange={(e) => buf.setValue({ ...buf.value, corpo: e.target.value })} />
      </div>
      <div>
        <label htmlFor="skill-notas" className="mb-1 block text-xs font-medium">Notas da versão</label>
        <Textarea id="skill-notas" rows={2} maxLength={2000} value={buf.value.notas} readOnly={!editavel} onChange={(e) => buf.setValue({ ...buf.value, notas: e.target.value })} />
      </div>
      {editavel && (
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={handleSalvar} disabled={!buf.dirty || salvar.isPending} data-testid="skill-salvar-rascunho">
            Salvar rascunho
          </Button>
        </div>
      )}

      <section className="space-y-2" data-testid="skill-arquivos">
        <h3 className="text-sm font-semibold">Arquivos de referência</h3>
        <p className="text-xs text-muted-foreground">O modelo os lê um a um, sob demanda (ler_arquivo_skill).</p>
        {versao.arquivos.length === 0 && <EmptyState message="Esta versão não tem arquivos de referência." />}
        <ul className="space-y-2">
          {versao.arquivos.map((a) => (
            <ArquivoEditor key={a.caminho} arquivo={a} chave={chave} versaoId={versao.id} editavel={editavel} />
          ))}
        </ul>
        {editavel && <NovoArquivo chave={chave} versaoId={versao.id} existentes={versao.arquivos.map((a) => a.caminho)} />}
      </section>
    </div>
  );
}

// ── page ──────────────────────────────────────────────────────────────────────────

export default function SkillBiblioteca() {
  const { chave = "" } = useParams<{ chave: string }>();
  const [params, setParams] = useSearchParams();
  const lista = useBibliotecaSkills();
  const skill = lista.data?.find((s) => s.chave === chave) ?? null;
  const versoes = useSkillVersoes(chave);
  const rascunho = versoes.data?.find((v) => v.status === "rascunho") ?? null;
  const publicada = versoes.data?.find((v) => v.status === "publicada") ?? null;
  const pedida = params.get("versao");
  const alvo = versoes.data?.find((v) => v.id === pedida) ?? rascunho ?? publicada ?? versoes.data?.[0] ?? null;
  const versao = useSkillVersao(alvo?.id);
  const criar = useCriarRascunhoSkill(chave);
  const [erro, setErro] = useState<string | null>(null);

  async function handleCriar() {
    setErro(null);
    try {
      const v = await criar.mutateAsync({ copiar_de: publicada?.id });
      setParams({ versao: v.id });
      toast.success(`Rascunho v${v.versao} criado.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  const voltar = (
    <Link to={SKILLS_BIBLIOTECA_HREF} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ArrowLeft className="h-3.5 w-3.5" /> Biblioteca de skills
    </Link>
  );

  if (lista.showSkeleton) return <div className="space-y-4">{voltar}<StudioLoading rows={4} /></div>;
  if (lista.isError) return <div className="space-y-4">{voltar}<RestrictedNotice error={lista.error} /></div>;
  if (!skill) {
    return <div className="space-y-4">{voltar}<EmptyState message={`Skill “${chave}” não encontrada na biblioteca.`} /></div>;
  }

  return (
    <div className="space-y-4" data-testid="skill-biblioteca">
      {voltar}
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{skill.nome}</h1>
        {(lista.isRefreshing || versoes.isRefreshing || versao.isRefreshing) && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      </div>
      <CabecalhoSkill key={skill.chave} skill={skill} />

      <section className="space-y-3" data-testid="skill-versoes">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="skill-versao-sel" className="mb-1 block text-xs font-medium">Versão</label>
            <Select id="skill-versao-sel" value={alvo?.id ?? ""} disabled={!versoes.data?.length} onChange={(e) => setParams({ versao: e.target.value })}>
              {(versoes.data ?? []).map((v) => (
                <option key={v.id} value={v.id}>v{v.versao} · {STATUS_LABEL[v.status]}</option>
              ))}
            </Select>
          </div>
          {!rascunho && !versoes.showSkeleton && !versoes.isError && (
            <Button size="sm" variant="outline" onClick={handleCriar} disabled={criar.isPending} data-testid="skill-criar-rascunho">
              <FilePlus2 className="mr-1 h-4 w-4" /> Criar rascunho{publicada ? ` a partir da v${publicada.versao}` : ""}
            </Button>
          )}
        </div>
        <SaveError message={erro} />

        {versoes.showSkeleton || (alvo && versao.showSkeleton) ? (
          <StudioLoading rows={3} />
        ) : versoes.isError ? (
          <RestrictedNotice error={versoes.error} />
        ) : !alvo ? (
          <EmptyState message="Esta skill ainda não tem versões. Crie um rascunho para começar." />
        ) : versao.isError ? (
          <RestrictedNotice error={versao.error} />
        ) : versao.data ? (
          <VersaoView key={versao.data.id} versao={versao.data} chave={chave} />
        ) : null}
      </section>
    </div>
  );
}
