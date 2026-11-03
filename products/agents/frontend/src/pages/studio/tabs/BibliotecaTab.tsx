/**
 * Agent Studio — "Skills da biblioteca" (Julia v2 CONTRACT D7/D8, §4.2): the shared skill library
 * and the versions this agent version PINS. A pin says which published skill version the agent
 * uses and `obrigatoria_para` — the tools that refuse until the skill was opened in the thread.
 * When the library has a newer published version, the pin shows a "nova versão" badge and a
 * one-click re-pin (draft only: a pin change re-stamps the draft's hash server-side).
 *
 * The routes live on branch `feat/julia-v2-a-skills`; this tab is built against that router.
 */
import { useState } from "react";
import { ArrowUpCircle, Pin, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Badge, Button, EmptyState, Select } from "@noctusai/lib/design-system";
import type { BibliotecaRef } from "@/api/studio/types-julia";
import { RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useBibliotecaRefs, useBibliotecaSkills, useFixarSkill, useRemoverSkillFixada } from "@/hooks/studio/useBiblioteca";
import { useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";
import { SKILLS_BIBLIOTECA_HREF, skillHref } from "../skillsRoutes";

/** The skill-opening tools can never be gated on a skill having been opened (circular). */
const FERRAMENTAS_ABRIR_SKILL = ["abrir_skill", "ler_arquivo_skill"];

const mesmoConjunto = (a: string[], b: string[]) => a.length === b.length && a.every((x) => b.includes(x));

type Pendencia = { selecao: string[]; erro: string | null };

function Pino({
  r,
  isDraft,
  ferramentas,
  pendente,
  onChange,
  onSalvar,
  onDescartar,
  onAtualizar,
  onRemove,
  busy,
  salvando,
}: {
  r: BibliotecaRef;
  isDraft: boolean;
  ferramentas: string[];
  pendente: Pendencia | undefined;
  onChange: (r: BibliotecaRef, selecao: string[]) => void;
  onSalvar: (r: BibliotecaRef) => void;
  onDescartar: (skill: string) => void;
  onAtualizar: (r: BibliotecaRef, versao: number) => void;
  onRemove: (skill: string) => void;
  busy: boolean;
  salvando: boolean;
}) {
  const selecao = pendente?.selecao ?? r.obrigatoria_para;
  const sujo = !!pendente && !mesmoConjunto(pendente.selecao, r.obrigatoria_para);
  const travado = busy || salvando;
  return (
    <li className="space-y-2 rounded-lg border border-border bg-card p-4" data-testid={`pino-${r.skill}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold">{r.skill}</span>
        <Badge variant="outline">v{r.versao}</Badge>
        {r.nova_versao !== null && (
          <Badge variant="default" data-testid={`pino-nova-${r.skill}`}>Nova versão v{r.nova_versao}</Badge>
        )}
        {sujo && <Badge variant="outline" data-testid={`pino-sujo-${r.skill}`}>Alterações não salvas</Badge>}
        {isDraft && (
          <div className="ml-auto flex items-center gap-2">
            {sujo && (
              <>
                <Button size="sm" variant="outline" disabled={travado} onClick={() => onDescartar(r.skill)} data-testid={`pino-descartar-${r.skill}`}>
                  Descartar
                </Button>
                <Button size="sm" disabled={travado} onClick={() => onSalvar(r)} data-testid={`pino-salvar-${r.skill}`}>
                  {salvando ? "Salvando…" : "Salvar"}
                </Button>
              </>
            )}
            {r.nova_versao !== null && (
              <Button size="sm" variant="outline" disabled={travado} onClick={() => onAtualizar(r, r.nova_versao as number)} data-testid={`pino-atualizar-${r.skill}`}>
                <ArrowUpCircle className="mr-1 h-3.5 w-3.5" /> Atualizar para v{r.nova_versao}
              </Button>
            )}
            <button type="button" className="text-muted-foreground hover:text-destructive" aria-label={`Desafixar ${r.skill}`} disabled={travado} onClick={() => onRemove(r.skill)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
      <fieldset className="space-y-1" disabled={!isDraft || salvando}>
        <legend className="text-xs font-medium">Obrigatória para as ferramentas</legend>
        <p className="text-xs text-muted-foreground">Uma ferramenta marcada é recusada até o agente abrir esta skill na conversa.</p>
        {ferramentas.length === 0 && <p className="text-xs text-muted-foreground">Esta versão não tem ferramentas cadastradas.</p>}
        <div className="flex flex-wrap gap-3">
          {ferramentas.map((f) => {
            const circular = FERRAMENTAS_ABRIR_SKILL.includes(f);
            return (
              <label key={f} className="flex items-center gap-1.5 text-xs" title={circular ? "Não pode exigir a skill: é a ferramenta que a abre." : undefined}>
                <input
                  type="checkbox"
                  disabled={circular}
                  checked={!circular && selecao.includes(f)}
                  onChange={(e) => onChange(r, e.target.checked ? [...selecao, f] : selecao.filter((x) => x !== f))}
                />
                <span className="font-mono">{f}</span>
                {circular && <span className="text-muted-foreground">(abre a skill)</span>}
              </label>
            );
          })}
        </div>
        {r.obrigatoria_para.filter((f) => !ferramentas.includes(f)).map((f) => (
          <p key={f} className="text-xs text-muted-foreground">Ferramenta fora da lista desta versão: <span className="font-mono">{f}</span></p>
        ))}
        {pendente?.erro && <p className="text-xs text-destructive" role="alert" data-testid={`pino-erro-${r.skill}`}>{pendente.erro}</p>}
      </fieldset>
    </li>
  );
}

export default function BibliotecaTab({ agentKey }: { agentKey: string }) {
  const { refs, versionId, isDraft } = useContentTarget(agentKey);
  const pins = useBibliotecaRefs(agentKey, versionId);
  const biblioteca = useBibliotecaSkills();
  const ferr = useVersionContent(agentKey, "ferramentas", versionId);
  const fixar = useFixarSkill(agentKey);
  const remover = useRemoverSkillFixada(agentKey);
  const [escolhida, setEscolhida] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  // Local pending selection per skill (key present = the card was edited). Ticking never hits the network.
  const [pend, setPend] = useState<Record<string, Pendencia>>({});
  const [salvando, setSalvando] = useState<Set<string>>(new Set());

  if (refs.showSkeleton || (versionId && pins.showSkeleton)) return <StudioLoading rows={3} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (pins.isError) return <RestrictedNotice error={pins.error} />;

  const ferramentas = (ferr.data?.itens ?? []).map((f) => f.ferramenta);
  const fixadas = pins.data ?? [];
  const haPublicada = (biblioteca.data ?? []).some((s) => s.versao_publicada !== null);
  const disponiveis = (biblioteca.data ?? []).filter((s) => s.versao_publicada !== null && !fixadas.some((p) => p.skill === s.chave));

  const sujo = (r: BibliotecaRef) => !!pend[r.skill] && !mesmoConjunto(pend[r.skill].selecao, r.obrigatoria_para);
  const sujas = fixadas.filter(sujo);

  function alterar(r: BibliotecaRef, selecao: string[]) {
    // Back to the server value = not dirty: drop the entry so a later server change re-syncs the card.
    if (mesmoConjunto(selecao, r.obrigatoria_para)) return descartar(r.skill);
    setPend((p) => ({ ...p, [r.skill]: { selecao, erro: null } }));
  }

  function descartar(skill: string) {
    setPend((p) => {
      const { [skill]: _, ...resto } = p;
      return resto;
    });
  }

  /** ONE PUT with the full list; on failure the local selection stays and the card shows the error. */
  async function salvarCard(r: BibliotecaRef): Promise<boolean> {
    const selecao = pend[r.skill]?.selecao;
    if (!selecao) return true;
    setSalvando((s) => new Set(s).add(r.skill));
    try {
      await fixar.mutateAsync({ skill: r.skill, ref: { versao: r.versao, obrigatoria_para: selecao, ordem: r.ordem } });
      descartar(r.skill);
      return true;
    } catch (err) {
      setPend((p) => ({ ...p, [r.skill]: { selecao, erro: errorMessage(err) } }));
      return false;
    } finally {
      setSalvando((s) => {
        const n = new Set(s);
        n.delete(r.skill);
        return n;
      });
    }
  }

  async function salvarTudo() {
    for (const r of sujas) await salvarCard(r);
  }

  async function atualizar(r: BibliotecaRef, versao: number) {
    setErro(null);
    try {
      await fixar.mutateAsync({ skill: r.skill, ref: { versao, obrigatoria_para: r.obrigatoria_para, ordem: r.ordem } });
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function desafixar(skill: string) {
    setErro(null);
    try {
      await remover.mutateAsync({ skill });
      toast.success(`Skill ${skill} desafixada do rascunho.`);
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  async function fixarNova() {
    if (!escolhida) return;
    setErro(null);
    try {
      await fixar.mutateAsync({ skill: escolhida, ref: { obrigatoria_para: [], ordem: fixadas.length } });
      setEscolhida("");
      toast.success("Skill fixada no rascunho.");
    } catch (err) {
      setErro(errorMessage(err));
    }
  }

  const busy = remover.isPending || (fixar.isPending && salvando.size === 0);

  return (
    <div className="space-y-4" data-testid="biblioteca-tab">
      <VersionBar agentKey={agentKey} rotulo="Skills fixadas" />
      {pins.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {isDraft && sujas.length >= 2 && (
        <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-sm" data-testid="biblioteca-salvar-tudo-barra">
          <span>{sujas.length} skills com alterações não salvas.</span>
          <Button size="sm" className="ml-auto" disabled={salvando.size > 0} onClick={salvarTudo} data-testid="biblioteca-salvar-tudo">
            Salvar tudo
          </Button>
        </div>
      )}
      {fixadas.length === 0 ? (
        <EmptyState message="Nenhuma skill da biblioteca fixada nesta versão." />
      ) : (
        <ul className="space-y-3">
          {fixadas.map((r) => (
            <Pino
              key={r.skill}
              r={r}
              isDraft={isDraft}
              ferramentas={ferramentas}
              pendente={pend[r.skill]}
              onChange={alterar}
              onSalvar={salvarCard}
              onDescartar={descartar}
              onAtualizar={atualizar}
              onRemove={desafixar}
              busy={busy}
              salvando={salvando.has(r.skill)}
            />
          ))}
        </ul>
      )}
      <SaveError message={erro} />

      {isDraft && (
        <section className="space-y-2 rounded-lg border border-border bg-card p-4">
          <h2 className="text-sm font-semibold">Fixar da biblioteca</h2>
          {biblioteca.showSkeleton ? (
            <StudioLoading rows={1} />
          ) : biblioteca.isError ? (
            <RestrictedNotice error={biblioteca.error} />
          ) : disponiveis.length === 0 ? (
            haPublicada ? (
              <p className="text-xs text-muted-foreground">Todas as skills publicadas já estão fixadas.</p>
            ) : (
              <p className="text-xs text-muted-foreground" data-testid="biblioteca-sem-publicadas">
                Nenhuma skill publicada ainda —{" "}
                <Link to={SKILLS_BIBLIOTECA_HREF} className="text-primary hover:underline">publique na Biblioteca de skills</Link>.
              </p>
            )
          ) : (
            <div className="flex gap-2">
              <Select aria-label="Skill da biblioteca" value={escolhida} onChange={(e) => setEscolhida(e.target.value)}>
                <option value="">Escolha uma skill…</option>
                {disponiveis.map((s) => (
                  <option key={s.chave} value={s.chave}>{s.nome} (v{s.versao_publicada})</option>
                ))}
              </Select>
              <Button size="sm" variant="outline" disabled={!escolhida || busy} onClick={fixarNova} data-testid="biblioteca-fixar">
                <Pin className="mr-1 h-3.5 w-3.5" /> Fixar
              </Button>
            </div>
          )}
        </section>
      )}

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Biblioteca</h2>
          <Link to={SKILLS_BIBLIOTECA_HREF} className="text-xs text-primary hover:underline" data-testid="biblioteca-gerenciar">Gerenciar skills</Link>
        </div>
        {biblioteca.data && biblioteca.data.length > 0 && (
          <ul className="grid gap-2 sm:grid-cols-2" data-testid="biblioteca-lista">
            {biblioteca.data.map((s) => (
              <li key={s.id} className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <Link to={skillHref(s.chave)} className="font-medium text-primary hover:underline">{s.nome}</Link> <span className="font-mono text-xs text-muted-foreground">{s.chave}</span>
                <p className="text-xs text-muted-foreground">
                  {s.versao_publicada !== null ? `Publicada v${s.versao_publicada}` : "Sem versão publicada"}
                  {s.tem_rascunho ? " · rascunho em edição" : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
