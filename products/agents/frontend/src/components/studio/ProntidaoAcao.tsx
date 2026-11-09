/**
 * The ACTION behind a readiness item: a real button instead of an API path. Mapped by item `codigo`:
 *
 *   mecanismo_*        -> "Rodar suíte de mecanismo"    (platform admin; queued job, polled)
 *   eval_juiz_*        -> "Rodar avaliação completa"    (queued job, polled)
 *   skill_desatualizada -> "Atualizar skills"
 *   controles_desligado -> "Ligar agente"               (org admin, only once a version is published)
 *
 * Every state is drawn: idle, starting, running (progress), done with result, failed (per-case reasons in pt-BR),
 * refused (the server's reason). When the job settles the hooks refetch the checklist, so the item itself changes.
 */
import { useState } from "react";
import { Loader2, Play, Power, RefreshCw } from "lucide-react";
import { Button, useIsOrgAdmin } from "@noctusai/lib/design-system";
import { useIsPlatformAdmin } from "@/hooks/useIsPlatformAdmin";
import { useStudioAgent } from "@/hooks/studio/useStudioAgents";
import { useIniciarMecanismo, useMecanismoRun } from "@/hooks/studio/useMecanismo";
import { useCreateEvalRun, useEvalRun } from "@/hooks/studio/useEvals";
import { useSetControle } from "@/hooks/studio/useControle";
import { useAtualizarSkillsBiblioteca } from "@/hooks/studio/useBiblioteca";
import { errorMessage } from "@/lib/errors";
import type { MecanismoCaso } from "@/api/studio/types-prontidao";

export type TipoAcao = "mecanismo" | "avaliacao" | "ligar" | "skills";

/** Which action (if any) fixes this readiness item. */
export function acaoDoItem(codigo: string): TipoAcao | null {
  if (codigo.startsWith("mecanismo_") && codigo !== "mecanismo_ok" && codigo !== "mecanismo_nao_configurado") return "mecanismo";
  if (codigo.startsWith("eval_juiz_") && codigo !== "eval_juiz_ok") return "avaliacao";
  if (codigo === "controles_desligado") return "ligar";
  if (codigo === "skill_desatualizada") return "skills";
  return null;
}

/** Assert names the mechanism suite reports, in plain pt-BR. Unknown names fall back to a generic phrase. */
const ASSERT_PT: Record<string, string> = {
  ferramentas_incluem: "não usou uma ferramenta que devia usar",
  ferramentas_proibidas: "usou uma ferramenta proibida",
  estagio_final: "terminou em uma etapa diferente da esperada",
  criterios_registrados: "não registrou os critérios esperados",
  ofertas_por_lote: "ofertas fora do formato por lote",
  sem_violacoes: "gerou uma violação das regras de segurança",
  identificacao_completa: "identificação incompleta",
  handoff_para: "transferiu para a pessoa errada",
  sem_vazamento: "vazou conteúdo interno",
  skill_aberta_antes_de: "não abriu a skill antes de agir",
  acoes_incluem: "deixou de fazer uma ação esperada",
  acoes_proibidas: "fez uma ação proibida",
  handoff_motivo: "transferiu pelo motivo errado",
  sem_handoff: "transferiu para uma pessoa sem precisar",
  violacoes_incluem: "não detectou a violação esperada",
  bolhas_sem_padrao: "mensagem fora do padrão permitido",
  bolhas_max_chars: "mensagem maior que o limite",
  sem_links_externos: "incluiu link externo",
  sem_pii: "expôs dado pessoal",
  sem_resposta: "respondeu quando devia ficar em silêncio",
  participante_estado: "deixou o participante em estado incorreto",
  solicitacao_titular: "não registrou a solicitação do titular",
};

export function descreverFalha(assertName: string, codigo: string): string {
  return `${ASSERT_PT[assertName] ?? "uma verificação do caso falhou"} (${codigo})`;
}

function falhasDoCaso(c: MecanismoCaso): string[] {
  const vistas = new Set<string>();
  for (const ex of c.execucoes) for (const f of ex.falhas) vistas.add(descreverFalha(f.assert, f.codigo));
  return [...vistas];
}

function Erro({ children, testId }: { children: React.ReactNode; testId: string }) {
  return <p role="alert" className="mt-1 text-xs text-destructive" data-testid={testId}>{children}</p>;
}

function Nota({ children, testId }: { children: React.ReactNode; testId: string }) {
  return <p className="mt-1 text-xs text-muted-foreground" data-testid={testId}>{children}</p>;
}

function Rodando({ texto, testId }: { texto: string; testId: string }) {
  return (
    <p role="status" className="mt-1 flex items-center gap-1 text-xs text-muted-foreground" data-testid={testId}>
      <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> {texto}
    </p>
  );
}

function AcaoMecanismo({ agentKey }: { agentKey: string }) {
  const admin = useIsPlatformAdmin();
  const iniciar = useIniciarMecanismo(agentKey);
  const [runId, setRunId] = useState<string | null>(null);
  const run = useMecanismoRun(agentKey, runId);
  if (!admin) {
    return <Nota testId="acao-mecanismo-restrito">Peça a um administrador da plataforma para rodar a suíte de mecanismo.</Nota>;
  }
  const rodando = iniciar.isPending || (!!runId && run.data?.status === "executando") || (!!runId && run.showSkeleton);
  const r = run.data;
  const reprovados = r?.status === "concluida" ? r.casos.filter((c) => !c.passou) : [];
  return (
    <div className="mt-2" data-testid="acao-mecanismo">
      <Button
        size="sm"
        variant="outline"
        // Several runs of one version may execute at once (migration 071): only the POST itself blocks a click.
        // The panel follows the newest run it started.
        disabled={iniciar.isPending}
        onClick={() => {
          setRunId(null);
          iniciar.mutate(undefined, { onSuccess: (res) => setRunId(res.run_id) });
        }}
        data-testid="acao-mecanismo-botao"
      >
        <Play className="mr-1 h-3 w-3" aria-hidden /> Rodar suíte de mecanismo
      </Button>
      {iniciar.isError && <Erro testId="acao-mecanismo-erro">{errorMessage(iniciar.error)}</Erro>}
      {rodando && <Rodando testId="acao-mecanismo-andamento" texto="Rodando a suíte com o modelo real. Isso pode levar alguns minutos; você pode continuar aqui." />}
      {runId && run.isError && !r && <Erro testId="acao-mecanismo-erro-leitura">Não foi possível acompanhar a execução. <button type="button" className="underline" onClick={run.refetch}>Tentar de novo</button></Erro>}
      {r?.status === "falhou" && <Erro testId="acao-mecanismo-falhou">A execução falhou{r.erro ? `: ${r.erro}` : "."} Tente rodar de novo.</Erro>}
      {r?.status === "cancelada" && <Nota testId="acao-mecanismo-cancelada">A execução foi cancelada. Rode de novo para atualizar o resultado.</Nota>}
      {r?.status === "concluida" && (
        <div data-testid="acao-mecanismo-resultado">
          <p className={`mt-1 text-xs ${r.aprovado ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}`}>
            {r.casos_aprovados} de {r.total_casos} {r.total_casos === 1 ? "caso passou" : "casos passaram"}
            {r.orcamento_excedido ? "; o limite de custo foi atingido e a suíte ficou incompleta" : ""}.
          </p>
          {reprovados.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs text-destructive" data-testid="acao-mecanismo-falhas">
              {reprovados.map((c) => (
                <li key={c.slug}>
                  <span className="font-medium">{c.slug}</span>: {falhasDoCaso(c).join("; ") || "não passou em todas as execuções"}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function AcaoAvaliacao({ agentKey }: { agentKey: string }) {
  const agent = useStudioAgent(agentKey);
  const criar = useCreateEvalRun(agentKey);
  const [runId, setRunId] = useState<string | null>(null);
  const run = useEvalRun(agentKey, runId);
  const draft = agent.data?.versoes.find((v) => v.status === "rascunho") ?? null;
  const r = run.data;
  const rodando = criar.isPending || (!!runId && !r) || r?.status === "pendente" || r?.status === "executando";
  return (
    <div className="mt-2" data-testid="acao-avaliacao">
      <Button
        size="sm"
        variant="outline"
        disabled={rodando || !draft}
        onClick={() => { if (!draft) return; setRunId(null); criar.mutate({ version_id: draft.id }, { onSuccess: (res) => setRunId(res.id) }); }}
        data-testid="acao-avaliacao-botao"
      >
        <Play className="mr-1 h-3 w-3" aria-hidden /> Rodar avaliação completa
      </Button>
      {!draft && !agent.showSkeleton && <Nota testId="acao-avaliacao-sem-rascunho">Crie um rascunho para poder avaliar.</Nota>}
      {criar.isError && <Erro testId="acao-avaliacao-erro">{errorMessage(criar.error)}</Erro>}
      {rodando && <Rodando testId="acao-avaliacao-andamento" texto={r && r.total > 0 ? `Avaliando: ${r.aprovados} de ${r.total} casos aprovados até agora…` : "Avaliando os casos. Isso pode levar alguns minutos; você pode continuar aqui."} />}
      {runId && run.isError && !r && <Erro testId="acao-avaliacao-erro-leitura">Não foi possível acompanhar a avaliação. Atualize a página para ver o resultado.</Erro>}
      {r?.status === "falhou" && <Erro testId="acao-avaliacao-falhou">A avaliação falhou{r.erro ? `: ${r.erro}` : "."} Tente rodar de novo.</Erro>}
      {r?.status === "cancelada" && <Nota testId="acao-avaliacao-cancelada">A avaliação foi cancelada. Rode de novo para atualizar o resultado.</Nota>}
      {r?.status === "concluida" && (
        <p className="mt-1 text-xs text-muted-foreground" data-testid="acao-avaliacao-resultado">
          {r.aprovados} de {r.total} {r.total === 1 ? "caso aprovado" : "casos aprovados"}
          {r.score !== null ? ` (nota ${r.score.toFixed(2)}, limiar ${r.limiar.toFixed(2)})` : ""}
          {r.completa === false ? "; a avaliação não cobriu todos os casos" : ""}.
        </p>
      )}
    </div>
  );
}

function AcaoLigar({ agentKey }: { agentKey: string }) {
  const admin = useIsOrgAdmin();
  const agent = useStudioAgent(agentKey);
  const ligar = useSetControle(agentKey);
  const publicado = agent.data?.versoes.some((v) => v.status === "ativa") ?? false;
  if (agent.showSkeleton) return null;
  if (!publicado) return <Nota testId="acao-ligar-publicar">Publique o agente primeiro; depois ele poderá ser ligado aqui.</Nota>;
  if (!admin) return <Nota testId="acao-ligar-restrito">Peça a um administrador da organização para ligar o agente.</Nota>;
  return (
    <div className="mt-2" data-testid="acao-ligar">
      <Button size="sm" variant="outline" disabled={ligar.isPending} onClick={() => ligar.mutate({ modo: "ligado" })} data-testid="acao-ligar-botao">
        <Power className="mr-1 h-3 w-3" aria-hidden /> {ligar.isPending ? "Ligando…" : "Ligar agente"}
      </Button>
      {ligar.isError && <Erro testId="acao-ligar-erro">{errorMessage(ligar.error)}</Erro>}
      {ligar.isSuccess && <Nota testId="acao-ligar-ok">Agente ligado.</Nota>}
    </div>
  );
}

function AcaoSkills({ agentKey }: { agentKey: string }) {
  const atualizar = useAtualizarSkillsBiblioteca(agentKey);
  return (
    <div className="mt-2" data-testid="acao-skills">
      <Button size="sm" variant="outline" disabled={atualizar.isPending} onClick={() => atualizar.mutate()} data-testid="acao-skills-botao">
        <RefreshCw className="mr-1 h-3 w-3" aria-hidden /> {atualizar.isPending ? "Atualizando…" : "Atualizar skills"}
      </Button>
      {atualizar.isError && <Erro testId="acao-skills-erro">{errorMessage(atualizar.error)}</Erro>}
      {atualizar.isSuccess && (
        <Nota testId="acao-skills-ok">
          {atualizar.data.atualizadas.length > 0
            ? `${atualizar.data.atualizadas.length} skill(s) atualizada(s). Rode a avaliação de novo.`
            : "Nenhuma skill precisava de atualização."}
        </Nota>
      )}
    </div>
  );
}

export function ProntidaoAcao({ codigo, agentKey }: { codigo: string; agentKey: string }) {
  const tipo = acaoDoItem(codigo);
  if (tipo === "mecanismo") return <AcaoMecanismo agentKey={agentKey} />;
  if (tipo === "avaliacao") return <AcaoAvaliacao agentKey={agentKey} />;
  if (tipo === "skills") return <AcaoSkills agentKey={agentKey} />;
  if (tipo === "ligar") return <AcaoLigar agentKey={agentKey} />;
  return null;
}
