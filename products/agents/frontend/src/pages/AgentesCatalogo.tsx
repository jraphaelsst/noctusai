/**
 * Catálogo de agentes — `/agentes/catalogo`.
 *
 * Cards lado a lado (nome, papel, runtime, descrição pública, capacidades).
 * Renderiza SOMENTE campos de exibição; `ferramentas` / `versao` aparecem
 * apenas quando o servidor os envia (tier de administrador da plataforma).
 */
import { useMemo, useState } from "react";
import { BookOpen, Bot, ShieldAlert } from "lucide-react";
import { Badge } from "@noctusai/lib/design-system";
import { useAgentesCatalogo, type AgenteCatalogo } from "@/hooks/useAgentesCatalogo";

const PAPEL_LABEL: Record<string, string> = {
  sdr: "SDR / leads",
  operador: "Operador",
  academia: "Academia",
};

const RUNTIME_LABEL: Record<string, string> = {
  internal: "Interno",
  external: "Externo",
};

function papelLabel(papel: string) {
  return PAPEL_LABEL[papel.toLowerCase()] ?? papel;
}

function CardSkeleton() {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      <div className="h-3 w-full animate-pulse rounded bg-muted" />
      <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
    </div>
  );
}

function AgenteCard({ agente }: { agente: AgenteCatalogo }) {
  const ferramentas = agente.ferramentas?.length ? agente.ferramentas : null;
  const temVersao = agente.versao !== undefined && agente.versao !== null && agente.versao !== "";
  return (
    <article
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
      data-testid={`catalogo-card-${agente.key}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Bot className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-foreground">{agente.nome}</h2>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge variant="default" data-testid={`catalogo-papel-${agente.key}`}>
              {papelLabel(agente.papel)}
            </Badge>
            <Badge variant="muted" data-testid={`catalogo-runtime-${agente.key}`}>
              {RUNTIME_LABEL[agente.runtime] ?? agente.runtime}
            </Badge>
          </div>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">{agente.descricao_publica}</p>

      <div>
        <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Capacidades</p>
        {agente.capacidades.length === 0 ? (
          <p className="text-xs text-muted-foreground">Nenhuma capacidade listada.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5" data-testid={`catalogo-capacidades-${agente.key}`}>
            {agente.capacidades.map((c) => (
              <li key={c} className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs text-foreground">
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>

      {ferramentas && (
        <div data-testid={`catalogo-ferramentas-${agente.key}`}>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">Ferramentas</p>
          <ul className="flex flex-wrap gap-1.5">
            {ferramentas.map((f) => (
              <li key={f} className="rounded bg-muted px-2 py-0.5 font-mono text-xs text-foreground">
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}

      {temVersao && (
        <p className="text-xs text-muted-foreground" data-testid={`catalogo-versao-${agente.key}`}>
          Versão: <span className="font-medium text-foreground">{String(agente.versao)}</span>
        </p>
      )}
    </article>
  );
}

export default function AgentesCatalogo() {
  const { data, showSkeleton, isRefreshing, isError } = useAgentesCatalogo();
  const [papel, setPapel] = useState<string>("todos");

  const papeis = useMemo(() => Array.from(new Set((data ?? []).map((a) => a.papel))), [data]);
  const visiveis = useMemo(
    () => (data ?? []).filter((a) => papel === "todos" || a.papel === papel),
    [data, papel],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <BookOpen className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Catálogo de agentes</h1>
          <p className="text-sm text-muted-foreground">
            Compare o que cada agente faz e quais são suas capacidades.
            {isRefreshing && <span className="ml-2 text-xs" data-testid="catalogo-refreshing">Atualizando…</span>}
          </p>
        </div>
      </div>

      {showSkeleton ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="catalogo-skeleton">
          <CardSkeleton />
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : isError && !data ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground" data-testid="catalogo-error">
          <ShieldAlert className="h-6 w-6" />
          <p className="text-sm">Erro ao carregar o catálogo de agentes.</p>
        </div>
      ) : !data || data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-8 text-muted-foreground" data-testid="catalogo-empty">
          <Bot className="h-6 w-6 opacity-30" />
          <p className="text-sm">Nenhum agente no catálogo.</p>
        </div>
      ) : (
        <>
          {papeis.length > 1 && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Filtrar por papel">
              {["todos", ...papeis].map((p) => (
                <button
                  key={p}
                  type="button"
                  aria-pressed={papel === p}
                  onClick={() => setPapel(p)}
                  data-testid={`catalogo-filtro-${p}`}
                  className={`rounded-full border px-3 py-1 text-xs font-medium ${
                    papel === p ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background text-foreground hover:bg-accent"
                  }`}
                >
                  {p === "todos" ? "Todos" : papelLabel(p)}
                </button>
              ))}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="catalogo-list">
            {visiveis.map((a) => (
              <AgenteCard key={a.key} agente={a} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
