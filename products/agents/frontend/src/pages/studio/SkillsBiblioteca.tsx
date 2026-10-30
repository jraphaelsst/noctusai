/**
 * Agent Studio — `/studio/biblioteca-skills`: the shared skills LIBRARY (platform admin only).
 * Lists every library skill with its published version / open draft and creates new ones. A new
 * skill has NO version yet — open it to create the first draft, fill it in and publish; only a
 * published version can be pinned on an agent (Skills da biblioteca tab).
 */
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Plus } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { SKILL_CHAVE_RE } from "@/api/studio/types-julia";
import { SaveError, RestrictedNotice } from "@/components/studio/ConteudoChrome";
import { StudioEmpty, StudioLoading } from "@/components/studio/StudioStates";
import { useBibliotecaSkills, useCriarSkill } from "@/hooks/studio/useBiblioteca";
import { errorMessage } from "@/lib/errors";
import { SKILLS_BIBLIOTECA_HREF, skillHref } from "./skillsRoutes";

const INPUT_CLASS =
  "w-full h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50";

function NovaSkillForm({ onDone }: { onDone: (chave: string) => void }) {
  const criar = useCriarSkill();
  const [chave, setChave] = useState("");
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const chaveInvalida = chave.length > 0 && (!SKILL_CHAVE_RE.test(chave) || chave.length > 64);

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const s = await criar.mutateAsync({ chave, nome: nome.trim(), descricao: descricao.trim() || null });
      toast.success(`Skill ${s.chave} criada. Crie o primeiro rascunho para preenchê-la.`);
      onDone(s.chave);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  return (
    <form onSubmit={enviar} className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="skill-nova-form">
      <h2 className="text-sm font-semibold">Nova skill</h2>
      <div>
        <label htmlFor="skill-chave" className="mb-1 block text-xs font-medium">Chave</label>
        <input id="skill-chave" className={INPUT_CLASS} value={chave} maxLength={64} onChange={(e) => setChave(e.target.value)} placeholder="ex.: qualificar-lead" aria-invalid={chaveInvalida} />
        <p className={`mt-1 text-xs ${chaveInvalida ? "text-destructive" : "text-muted-foreground"}`} data-testid="skill-chave-ajuda">
          Letras minúsculas e números, separados por hífen (sem espaços, acentos ou hífen nas pontas). Não pode ser alterada depois.
        </p>
      </div>
      <div>
        <label htmlFor="skill-nome" className="mb-1 block text-xs font-medium">Nome</label>
        <input id="skill-nome" className={INPUT_CLASS} value={nome} maxLength={200} onChange={(e) => setNome(e.target.value)} />
      </div>
      <div>
        <label htmlFor="skill-descricao" className="mb-1 block text-xs font-medium">Descrição (para quem administra a biblioteca)</label>
        <input id="skill-descricao" className={INPUT_CLASS} value={descricao} maxLength={1024} onChange={(e) => setDescricao(e.target.value)} />
      </div>
      <SaveError message={erro} />
      <div className="flex justify-end gap-2">
        <Button type="submit" variant="primary" size="sm" disabled={!chave || chaveInvalida || !nome.trim() || criar.isPending} data-testid="skill-nova-salvar">
          Criar skill
        </Button>
      </div>
    </form>
  );
}

export default function SkillsBiblioteca() {
  const navigate = useNavigate();
  const { data: skills, showSkeleton, isRefreshing, isError, error, refetch } = useBibliotecaSkills();
  const [novaAberta, setNovaAberta] = useState(false);

  return (
    <div className="space-y-4" data-testid="skills-biblioteca">
      <Link to="/agentes" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3.5 w-3.5" /> Agentes
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Biblioteca de skills</h1>
          <p className="text-sm text-muted-foreground">
            Playbooks compartilhados que os agentes fixam por versão. Publicar uma versão não muda os agentes que já a fixaram.
          </p>
        </div>
        {isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
        <Button variant="primary" className="ml-auto" onClick={() => setNovaAberta((v) => !v)} data-testid="skill-nova">
          <Plus className="mr-1 h-4 w-4" /> Nova skill
        </Button>
      </div>

      {novaAberta && <NovaSkillForm onDone={(c) => navigate(skillHref(c))} />}

      {showSkeleton ? (
        <StudioLoading rows={4} testId="skills-skeleton" />
      ) : isError ? (
        <div className="space-y-2">
          <RestrictedNotice error={error} />
          <Button size="sm" variant="outline" onClick={refetch}>Tentar novamente</Button>
        </div>
      ) : !skills || skills.length === 0 ? (
        <StudioEmpty titulo="Nenhuma skill na biblioteca ainda.">
          <p className="text-xs">Use “Nova skill” para criar a primeira.</p>
        </StudioEmpty>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2" data-testid="skills-lista">
          {skills.map((s) => (
            <li key={s.id} className="rounded-lg border border-border bg-card p-4" data-testid={`skill-${s.chave}`}>
              <Link to={skillHref(s.chave)} className="font-medium text-primary hover:underline">{s.nome}</Link>{" "}
              <span className="font-mono text-xs text-muted-foreground">{s.chave}</span>
              {s.descricao && <p className="mt-1 text-xs text-muted-foreground">{s.descricao}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                <Badge variant={s.versao_publicada !== null ? "default" : "muted"}>
                  {s.versao_publicada !== null ? `Publicada v${s.versao_publicada}` : "Sem versão publicada"}
                </Badge>
                {s.tem_rascunho && <Badge variant="outline">rascunho em edição</Badge>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
