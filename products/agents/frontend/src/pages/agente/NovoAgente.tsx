/**
 * `/agentes/novo` — the new-agent wizard (agents-unified CONTRACT §6). Platform admins only: the server decides
 * (`GET /api/studio/modelo` serves `assistente` only to tier `plataforma`); anyone else gets the standard not-found.
 *
 * The journey is the seed `JourneyWizard` organ over `modelo.assistente.passos` — the steps, their order and
 * category, and every step's fields come from the model, never from this file. A step that mixes field groups
 * (definition + briefing) splits into subtabs. Two start modes: an empty definition, or "Gerar com IA" (the
 * briefing makes the server write the first DRAFT, cost-capped). The answers live in a local draft until
 * "Publicar" POSTs the §6 body to `POST /api/studio/plataforma/agents`; the listing and page caches receive the
 * new agent from the answer, and the page opens `/agentes/:key`.
 */
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Bot, Pencil, Sparkles, SquareDashed } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button } from "@noctusai/lib/design-system";
import { JourneyWizard, type JourneyStep } from "@noctusai/lib/journey";
import { UnsavedChangesNotice } from "@noctusai/lib";
import type { AreaModelo, PassoAssistente } from "@/api/agentes/types";
import { CampoAssistente } from "@/components/agentes/CampoAssistente";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useCreatePlatformAgent } from "@/hooks/studio/useAgentLifecycle";
import { useAgenteModelo, useAgentesPainel } from "@/hooks/useAgentesPainel";
import { useNovoAgenteRascunho, type NovoAgenteRascunho } from "@/hooks/useNovoAgenteRascunho";
import { lifecycleError } from "@/lib/agentLifecycle";
import {
  CATEGORIA_TITULO,
  GRUPO_TITULO,
  MODOS_INICIO,
  apresentacao,
  camposVisiveis,
  contarRespostas,
  gruposDoPasso,
  id,
  limiteGeracao,
  montarCorpo,
  obrigatorio,
  opcaoRotulo,
  primeiroPassoInvalido,
  validarPasso,
  type ErrosCampos,
  type ModoInicio,
} from "@/lib/assistente";
import { slugify } from "@/lib/briefing";
import { ApiError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import NotFound from "@/pages/NotFound";

/** CONTRACT §6 step 9: the step with no fields that summarises the answers. */
export const PASSO_RESUMO = "revisao";

function formatarUsd(v: number): string {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function NotaCusto({ limite }: { limite: number }) {
  return (
    <p className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground" data-testid="novo-agente-nota-custo">
      A geração por IA tem custo máximo de <span className="font-medium text-foreground">US$ {formatarUsd(limite)}</span> e
      escreve um RASCUNHO: revise e edite na página do agente — nada é publicado automaticamente.
    </p>
  );
}

function SeletorModo({ modo, onChange, limite }: { modo: ModoInicio; onChange: (m: ModoInicio) => void; limite: number }) {
  return (
    <div className="flex flex-col gap-3">
      <div role="radiogroup" aria-label="Como começar" className="grid gap-3 sm:grid-cols-2">
        {MODOS_INICIO.map((m) => {
          const on = modo === m.id;
          const Icone = m.id === "gerar" ? Sparkles : SquareDashed;
          return (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(m.id)}
              data-testid={`novo-agente-modo-${m.id}`}
              className={cn(
                "flex items-start gap-3 rounded-lg border p-4 text-left transition-all duration-200",
                on ? "border-primary bg-primary/5 shadow-sm" : "border-border bg-card hover:border-primary/40",
              )}
            >
              <span
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors duration-200",
                  on ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
                )}
              >
                <Icone className="h-4 w-4" />
              </span>
              <span className="flex flex-col gap-0.5">
                <span className="text-sm font-semibold text-foreground">{m.titulo}</span>
                <span className="text-xs text-muted-foreground">{m.descricao}</span>
              </span>
            </button>
          );
        })}
      </div>
      {modo === "gerar" && <NotaCusto limite={limite} />}
    </div>
  );
}

function CabecalhoPasso({ passo, modo, areas }: { passo: PassoAssistente; modo: ModoInicio; areas: AreaModelo[] }) {
  const titulos = passo.areas.map((a) => areas.find((x) => x.id === a)?.titulo ?? a);
  if (!passo.nota && (modo !== "gerar" || titulos.length === 0)) return null;
  return (
    <div className="flex flex-col gap-2">
      {passo.nota && <p className="text-sm text-muted-foreground">{passo.nota}</p>}
      {modo === "gerar" && titulos.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground" data-testid={`novo-agente-areas-${passo.id}`}>
          <span>Alimenta o rascunho:</span>
          {titulos.map((t) => (
            <Badge key={t} variant="outline">
              {t}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function valorLegivel(passo: PassoAssistente, chave: string, v: unknown): string {
  const campo = passo.campos.find((c) => id(c) === chave);
  if (v === undefined || v === null || (typeof v === "string" && v.trim() === "")) return "Não informado";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (campo?.tipo === "escolha") return opcaoRotulo(campo, String(v));
  return String(v);
}

function Resumo({ passos, r, irPara }: { passos: PassoAssistente[]; r: NovoAgenteRascunho; irPara: (id: string) => void }) {
  const modo = MODOS_INICIO.find((m) => m.id === r.modo);
  return (
    <div className="flex flex-col gap-4" data-testid="novo-agente-resumo">
      <p className="text-sm">
        Modo: <span className="font-medium text-foreground">{modo?.titulo}</span>
      </p>
      {passos
        .filter((p) => camposVisiveis(p, r.modo).length > 0)
        .map((p) => (
          <section key={p.id} className="rounded-md border border-border bg-background p-3" data-testid={`novo-agente-resumo-${p.id}`}>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-foreground">{p.titulo}</h3>
              <Button size="sm" variant="ghost" onClick={() => irPara(p.id)} data-testid={`novo-agente-editar-${p.id}`}>
                <Pencil className="mr-1 h-3.5 w-3.5" /> Editar
              </Button>
            </div>
            <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-[minmax(0,12rem)_1fr]">
              {camposVisiveis(p, r.modo).map((c) => (
                <div key={id(c)} className="contents">
                  <dt className="text-muted-foreground">{apresentacao(c).rotulo}</dt>
                  <dd className="whitespace-pre-wrap break-words text-foreground">{valorLegivel(p, id(c), r.valores[id(c)])}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
    </div>
  );
}

function salvoEmHora(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function Assistente({ passos, areas }: { passos: PassoAssistente[]; areas: AreaModelo[] }) {
  const r = useNovoAgenteRascunho(passos);
  const navigate = useNavigate();
  const create = useCreatePlatformAgent();
  const painel = useAgentesPainel();
  const [tentou, setTentou] = useState<Record<string, boolean>>({});
  const [erroEnvio, setErroEnvio] = useState<string | null>(null);

  const chavesExistentes = useMemo(() => new Set((painel.data ?? []).map((a) => a.key)), [painel.data]);
  const ctx = useMemo(() => ({ chavesExistentes }), [chavesExistentes]);
  const limite = limiteGeracao(passos) ?? 5;
  const passoAtual = passos.some((p) => p.id === r.passo) ? (r.passo as string) : passos[0].id;
  const { feitas, total } = contarRespostas(passos, r.modo, r.valores);
  const nome = String(r.valores["plataforma.nome"] ?? "").trim();
  const chave = String(r.valores["plataforma.key"] ?? "").trim();

  function mudar(campo: string, v: string | number | boolean) {
    r.setValor(campo, v);
    if (campo === "plataforma.key") r.setChaveTocada(true);
    if (campo === "plataforma.nome" && !r.chaveTocada) r.setValor("plataforma.key", slugify(String(v)));
  }

  function errosDe(passo: PassoAssistente): ErrosCampos {
    return validarPasso(passo, r.modo, r.valores, ctx);
  }

  function campos(passo: PassoAssistente, lista: ReturnType<typeof camposVisiveis>) {
    const erros = tentou[passo.id] ? errosDe(passo) : {};
    return (
      <div className="flex flex-col gap-4">
        {lista.map((c) => (
          <CampoAssistente key={id(c)} campo={c} valor={r.valores[id(c)]} erro={erros[id(c)]} onChange={(v) => mudar(id(c), v)} />
        ))}
      </div>
    );
  }

  async function publicar() {
    if (create.isPending) return;
    setErroEnvio(null);
    const invalido = primeiroPassoInvalido(passos, r.modo, r.valores, ctx);
    if (invalido) {
      setTentou((t) => ({ ...t, [invalido.passo.id]: true }));
      r.setPasso(invalido.passo.id);
      toast.error(`Revise a etapa “${invalido.passo.titulo}” antes de publicar.`);
      return;
    }
    const corpo = montarCorpo(passos, r.modo, r.valores);
    try {
      const criado = await create.mutateAsync(corpo);
      r.concluir();
      toast.success(
        criado.geracao
          ? `Agente ${corpo.nome ?? criado.key} criado. A IA está escrevendo o rascunho.`
          : `Agente ${corpo.nome ?? criado.key} criado como rascunho.`,
      );
      navigate(`/agentes/${encodeURIComponent(criado.key)}`);
    } catch (err) {
      const e = lifecycleError(err);
      setErroEnvio(e.hint ? `${e.message} ${e.hint}` : e.message);
    }
  }

  const steps: JourneyStep[] = passos.map((p) => {
    const grupos = gruposDoPasso(p, r.modo);
    const visiveis = camposVisiveis(p, r.modo);
    const cabecalho = <CabecalhoPasso passo={p} modo={r.modo} areas={areas} />;
    const corpo =
      p.id === PASSO_RESUMO ? (
        <div className="flex flex-col gap-4">
          {cabecalho}
          <Resumo passos={passos} r={r} irPara={r.setPasso} />
          {r.modo === "gerar" && <NotaCusto limite={Number(r.valores["plataforma.limite_usd"] ?? limite) || limite} />}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {cabecalho}
          {visiveis.length === 0 && !p.nota && (
            <p className="text-sm text-muted-foreground">Nada a responder nesta etapa no modo escolhido.</p>
          )}
          {grupos.length === 1 && campos(p, grupos[0].campos)}
          {p === passos[passos.length - 1] && r.modo === "gerar" && <NotaCusto limite={limite} />}
          {p === passos[passos.length - 1] && create.isPending && (
            <p role="status" className="text-sm text-muted-foreground" data-testid="novo-agente-publicando">
              Criando o agente…
            </p>
          )}
          {p === passos[passos.length - 1] && erroEnvio && (
            <p role="alert" className="text-sm text-destructive" data-testid="novo-agente-erro-envio">
              {erroEnvio}
            </p>
          )}
        </div>
      );
    return {
      id: p.id,
      title: p.titulo,
      category: CATEGORIA_TITULO[p.categoria] ?? p.categoria,
      description: p.descricao,
      content: corpo,
      subtabs:
        grupos.length > 1
          ? grupos.map((g) => ({ id: g.grupo, title: GRUPO_TITULO[g.grupo] ?? g.grupo, content: campos(p, g.campos) }))
          : undefined,
      optional: visiveis.length > 0 && !visiveis.some(obrigatorio),
      validate: () => {
        setTentou((t) => ({ ...t, [p.id]: true }));
        const erros = Object.values(errosDe(p));
        return erros.length === 0 ? true : erros[0];
      },
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-lg font-semibold text-primary transition-all duration-300">
            {nome ? nome.charAt(0).toUpperCase() : <Bot className="h-5 w-5" />}
          </div>
          <div className="min-w-0">
            <p className="truncate text-base font-semibold text-foreground" data-testid="novo-agente-preview-nome">
              {nome || "Novo agente"}
            </p>
            <p className="truncate font-mono text-xs text-muted-foreground">{chave || "chave-do-agente"}</p>
          </div>
        </div>
        <div className="flex flex-col items-start gap-1 sm:items-end">
          <span className="text-xs text-muted-foreground" data-testid="novo-agente-respostas">
            <span className="font-semibold tabular-nums text-foreground">{feitas}</span> de {total} respostas
          </span>
          <UnsavedChangesNotice dirty={r.dirty} className="text-xs text-warning" data-testid="novo-agente-nao-salvo">
            {r.guardado
              ? `Rascunho não publicado · guardado só neste navegador${r.salvoEm ? ` às ${salvoEmHora(r.salvoEm)}` : ""}`
              : "Rascunho não publicado · este navegador não guardou a cópia — não recarregue a página"}
          </UnsavedChangesNotice>
        </div>
      </div>

      {r.restaurado && r.dirty && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm" data-testid="novo-agente-restaurado">
          <span className="text-muted-foreground">Continuamos de onde você parou.</span>
          <Button size="sm" variant="ghost" onClick={r.descartar} data-testid="novo-agente-descartar">
            Descartar rascunho
          </Button>
        </div>
      )}

      <SeletorModo modo={r.modo} onChange={r.setModo} limite={limite} />

      <JourneyWizard
        steps={steps}
        currentStepId={passoAtual}
        onStepChange={(sid) => r.setPasso(sid)}
        onComplete={() => void publicar()}
        labels={{ finish: create.isPending ? "Publicando…" : "Publicar" }}
      />
    </div>
  );
}

export default function NovoAgente() {
  const { data, showSkeleton, isError, error, refetch } = useAgenteModelo();
  // Stable identity: the draft hook seeds defaults from it (a fresh array each render would re-seed forever).
  const passos = useMemo(
    () => (data?.assistente?.passos ? [...data.assistente.passos].sort((a, b) => a.ordem - b.ordem) : undefined),
    [data],
  );

  if (showSkeleton) return <StudioLoading rows={6} testId="novo-agente-skeleton" />;
  // D31: only platform admins create definitions. A member (no `assistente`) or a non-member (403) sees the
  // standard not-found, never a "forbidden" that would confirm the surface exists.
  if (isError && !data) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) return <NotFound />;
    return <StudioError error={error} onRetry={refetch} />;
  }
  if (!data || data.tier !== "plataforma" || !passos || passos.length === 0) return <NotFound />;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to="/agentes" className="text-muted-foreground hover:text-foreground" aria-label="Voltar para Agentes">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-foreground">Novo agente</h1>
          <p className="text-sm text-muted-foreground">Uma jornada curta: quem é, o que sabe, como atua — e publicar.</p>
        </div>
      </div>
      <Assistente passos={passos} areas={data.areas} />
    </div>
  );
}
