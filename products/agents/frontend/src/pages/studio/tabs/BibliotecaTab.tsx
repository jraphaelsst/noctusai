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
import { toast } from "sonner";
import { Badge, Button, EmptyState, Select } from "@noctusai/lib/design-system";
import type { BibliotecaRef } from "@/api/studio/types-julia";
import { RestrictedNotice, SaveError, VersionBar, useContentTarget } from "@/components/studio/ConteudoChrome";
import { StudioLoading } from "@/components/studio/StudioStates";
import { useBibliotecaRefs, useBibliotecaSkills, useFixarSkill, useRemoverSkillFixada } from "@/hooks/studio/useBiblioteca";
import { useVersionContent } from "@/hooks/studio/useConteudo";
import { errorMessage } from "@/lib/errors";

function Pino({
  r,
  isDraft,
  ferramentas,
  onSave,
  onRemove,
  busy,
}: {
  r: BibliotecaRef;
  isDraft: boolean;
  ferramentas: string[];
  onSave: (r: BibliotecaRef, patch: { versao?: number; obrigatoria_para?: string[] }) => void;
  onRemove: (skill: string) => void;
  busy: boolean;
}) {
  return (
    <li className="space-y-2 rounded-lg border border-border bg-card p-4" data-testid={`pino-${r.skill}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold">{r.skill}</span>
        <Badge variant="outline">v{r.versao}</Badge>
        {r.nova_versao !== null && (
          <Badge variant="default" data-testid={`pino-nova-${r.skill}`}>Nova versão v{r.nova_versao}</Badge>
        )}
        {isDraft && (
          <div className="ml-auto flex items-center gap-2">
            {r.nova_versao !== null && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onSave(r, { versao: r.nova_versao as number })} data-testid={`pino-atualizar-${r.skill}`}>
                <ArrowUpCircle className="mr-1 h-3.5 w-3.5" /> Atualizar para v{r.nova_versao}
              </Button>
            )}
            <button type="button" className="text-muted-foreground hover:text-destructive" aria-label={`Desafixar ${r.skill}`} disabled={busy} onClick={() => onRemove(r.skill)}>
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
      <fieldset className="space-y-1" disabled={!isDraft || busy}>
        <legend className="text-xs font-medium">Obrigatória para as ferramentas</legend>
        {ferramentas.length === 0 && <p className="text-xs text-muted-foreground">Esta versão não tem ferramentas cadastradas.</p>}
        <div className="flex flex-wrap gap-3">
          {ferramentas.map((f) => (
            <label key={f} className="flex items-center gap-1.5 text-xs">
              <input
                type="checkbox"
                checked={r.obrigatoria_para.includes(f)}
                onChange={(e) =>
                  onSave(r, { obrigatoria_para: e.target.checked ? [...r.obrigatoria_para, f] : r.obrigatoria_para.filter((x) => x !== f) })
                }
              />
              <span className="font-mono">{f}</span>
            </label>
          ))}
        </div>
        {r.obrigatoria_para.filter((f) => !ferramentas.includes(f)).map((f) => (
          <p key={f} className="text-xs text-muted-foreground">Ferramenta fora da lista desta versão: <span className="font-mono">{f}</span></p>
        ))}
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

  if (refs.showSkeleton || (versionId && pins.showSkeleton)) return <StudioLoading rows={3} />;
  if (refs.isError) return <RestrictedNotice error={refs.error} />;
  if (!versionId) return <EmptyState message="Este agente ainda não tem versão para editar." />;
  if (pins.isError) return <RestrictedNotice error={pins.error} />;

  const ferramentas = (ferr.data?.itens ?? []).map((f) => f.ferramenta);
  const fixadas = pins.data ?? [];
  const disponiveis = (biblioteca.data ?? []).filter((s) => s.versao_publicada !== null && !fixadas.some((p) => p.skill === s.chave));

  async function salvar(r: BibliotecaRef, patch: { versao?: number; obrigatoria_para?: string[] }) {
    setErro(null);
    try {
      await fixar.mutateAsync({
        skill: r.skill,
        ref: { versao: patch.versao ?? r.versao, obrigatoria_para: patch.obrigatoria_para ?? r.obrigatoria_para, ordem: r.ordem },
      });
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

  const busy = fixar.isPending || remover.isPending;

  return (
    <div className="space-y-4" data-testid="biblioteca-tab">
      <VersionBar agentKey={agentKey} rotulo="Skills fixadas" />
      {pins.isRefreshing && <span className="text-xs text-muted-foreground">Atualizando…</span>}
      {fixadas.length === 0 ? (
        <EmptyState message="Nenhuma skill da biblioteca fixada nesta versão." />
      ) : (
        <ul className="space-y-3">
          {fixadas.map((r) => (
            <Pino key={r.skill} r={r} isDraft={isDraft} ferramentas={ferramentas} onSave={salvar} onRemove={desafixar} busy={busy} />
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
            <p className="text-xs text-muted-foreground">Todas as skills publicadas já estão fixadas.</p>
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
        <h2 className="text-sm font-semibold">Biblioteca</h2>
        {biblioteca.data && biblioteca.data.length > 0 && (
          <ul className="grid gap-2 sm:grid-cols-2" data-testid="biblioteca-lista">
            {biblioteca.data.map((s) => (
              <li key={s.id} className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                <span className="font-medium">{s.nome}</span> <span className="font-mono text-xs text-muted-foreground">{s.chave}</span>
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
