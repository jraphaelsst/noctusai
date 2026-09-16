/**
 * Edição de Fotos — Regras de aprendizado (`/edicao-fotos/regras`,
 * `status_pagina` row `edicao-fotos-regras`, migration 128). The per-agency
 * learning loop (contract §7): the AI proposes "don't do this" rules from
 * rejection comments, an agency admin or platform admin decides them, and
 * only the platform admin may override an already-decided rule.
 *
 * Who: `capacidades.pode_aprovar_regras` (agency admin ∨ platform admin —
 * a corretor never sees this page, same as `/curadores`, `/referencias`).
 *
 * - "Propor agora" runs the AI proposer NOW instead of waiting for the
 *   rejection-settling debounce.
 * - A manual rule is created directly APROVADA — writing it down IS the
 *   approval.
 * - "Arquivar" (an already-approved rule) reuses the SAME decide-authority
 *   as a proposal's reject: only a PLATFORM ADMIN may flip a rule that is
 *   already decided — the FE hides that action for an agency admin rather
 *   than let it predictably 403.
 * - The effective-guide panel shows the CURRENT composed text (company
 *   guide + this org's approved rules) + its version history.
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` /
 * `isRefreshing` come pre-computed off the seed hooks — never `.isLoading`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  History,
  Lock,
  Pencil,
  PlusCircle,
  RefreshCw,
  ScrollText,
  Sparkles,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@noctusai/lib/api";

import {
  fotosPermissions,
  useAprovarRegra,
  useCapacidades,
  useConfiguracoesPlataforma,
  useCriarRegra,
  useEditarRegra,
  useGuiaEfetivo,
  useProporRegrasAgora,
  useRegras,
  useRejeitarRegra,
  type Capacidades,
  type RegraOrg,
  type RegraStatus,
} from "@/hooks/useEdicaoFotos";

const TEXTO_MAX = 2000;

const STATUS_ROTULO: Record<RegraStatus, string> = {
  proposta: "Proposta",
  aprovada: "Aprovada",
  rejeitada: "Arquivada",
};

const STATUS_BADGE_VARIANT: Record<RegraStatus, "default" | "secondary" | "outline"> = {
  proposta: "outline",
  aprovada: "default",
  rejeitada: "secondary",
};

function descricaoErro(err: unknown): string | undefined {
  if (err instanceof ApiError) {
    if (err.code === "regra_duplicada") return "Já existe uma regra equivalente para esta organização.";
    if (err.code === "regra_arquivada") return "Esta regra está arquivada — o texto não pode mais ser editado.";
    if (err.code === "decisao_regra_proibida")
      return "Apenas o administrador da plataforma pode sobrepor uma decisão já tomada.";
  }
  return err instanceof Error ? err.message : undefined;
}

function formatarData(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("pt-BR") : "—";
}

export default function Regras() {
  const { capacidades, showSkeleton } = useCapacidades();
  if (showSkeleton) return <ListaSkeleton />;
  if (!fotosPermissions.podeAprovarRegras(capacidades)) return <AcessoRestrito />;
  return <RegrasView capacidades={capacidades} />;
}

function RegrasView({ capacidades }: { capacidades: Capacidades | null | undefined }) {
  const ehAdminPlataforma = fotosPermissions.dashboardScope(capacidades) === "platform";
  const [statusFiltro, setStatusFiltro] = useState<RegraStatus | "todas">("todas");
  const { regras, total, showSkeleton, isRefreshing, error, refetch } = useRegras({
    status: statusFiltro === "todas" ? undefined : statusFiltro,
  });
  const proporAgora = useProporRegrasAgora();

  async function handleProporAgora() {
    try {
      await proporAgora.mutateAsync();
      toast.success("Proposta de regras enfileirada — novas propostas aparecem aqui quando prontas.");
    } catch (err) {
      toast.error("Não foi possível enfileirar a proposta.", { description: descricaoErro(err) });
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Regras de aprendizado</h1>
          <p className="text-sm text-muted-foreground">
            A IA propõe regras "não faça" a partir dos comentários de rejeição; aprove, rejeite ou
            escreva uma regra manualmente.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="regras-atualizando">
              <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <Button variant="outline" onClick={handleProporAgora} disabled={proporAgora.isPending}>
            <Sparkles className="mr-2 h-4 w-4" />
            {proporAgora.isPending ? "Enfileirando…" : "Propor agora"}
          </Button>
        </div>
      </div>

      <NovaRegraForm />

      <div className="flex items-center gap-2">
        <Label htmlFor="regras-status-filtro" className="text-sm text-muted-foreground">
          Status
        </Label>
        <Select value={statusFiltro} onValueChange={(v) => setStatusFiltro(v as RegraStatus | "todas")}>
          <SelectTrigger id="regras-status-filtro" className="w-44" data-testid="regras-status-filtro">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas ({total})</SelectItem>
            <SelectItem value="proposta">Propostas</SelectItem>
            <SelectItem value="aprovada">Aprovadas</SelectItem>
            <SelectItem value="rejeitada">Arquivadas</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <ListaSkeleton />
      ) : regras.length === 0 ? (
        <Card data-testid="regras-vazio">
          <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
            <ScrollText className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Nenhuma regra {statusFiltro === "todas" ? "" : "neste status "}ainda.</p>
            <p className="text-sm text-muted-foreground">
              Escreva uma acima ou clique em "Propor agora" para a IA sugerir a partir das rejeições.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="regras-lista">
          {regras.map((regra) => (
            <RegraCard key={regra.id} regra={regra} podeSobrepor={ehAdminPlataforma} />
          ))}
        </div>
      )}

      <GuiaEfetivoSection />

      {ehAdminPlataforma && <ConfiguracoesProponente />}
    </div>
  );
}

function NovaRegraForm() {
  const criar = useCriarRegra();
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState("");

  async function handleSalvar(e: FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    try {
      await criar.mutateAsync({ texto });
      toast.success("Regra criada e aprovada.");
      setTexto("");
      setAberto(false);
    } catch (err) {
      toast.error("Não foi possível criar a regra.", { description: descricaoErro(err) });
    }
  }

  if (!aberto) {
    return (
      <Button variant="secondary" onClick={() => setAberto(true)}>
        <PlusCircle className="mr-2 h-4 w-4" /> Escrever regra manualmente
      </Button>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <form className="space-y-3" onSubmit={handleSalvar} data-testid="nova-regra-form">
          <Label htmlFor="regra-texto">Texto da regra (o que NÃO fazer)</Label>
          <Textarea
            id="regra-texto"
            rows={3}
            maxLength={TEXTO_MAX}
            placeholder="Não escurecer o céu artificialmente"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Uma regra escrita manualmente já entra aprovada — escrevê-la É a aprovação.
          </p>
          <div className="flex gap-2">
            <Button type="submit" disabled={!texto.trim() || criar.isPending}>
              {criar.isPending ? "Salvando…" : "Salvar regra"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setAberto(false)} disabled={criar.isPending}>
              Cancelar
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function RegraCard({ regra, podeSobrepor }: { regra: RegraOrg; podeSobrepor: boolean }) {
  const aprovar = useAprovarRegra();
  const rejeitar = useRejeitarRegra();
  const editar = useEditarRegra();
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(regra.texto);

  async function handleAprovar() {
    try {
      await aprovar.mutateAsync(regra.id);
      toast.success("Regra aprovada.");
    } catch (err) {
      toast.error("Não foi possível aprovar a regra.", { description: descricaoErro(err) });
    }
  }

  async function handleRejeitarOuArquivar() {
    try {
      await rejeitar.mutateAsync(regra.id);
      toast.success(regra.status === "proposta" ? "Regra rejeitada." : "Regra arquivada.");
    } catch (err) {
      toast.error("Não foi possível concluir a ação.", { description: descricaoErro(err) });
    }
  }

  async function handleSalvarEdicao(e: FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    try {
      await editar.mutateAsync({ regraId: regra.id, texto });
      toast.success("Regra atualizada.");
      setEditando(false);
    } catch (err) {
      toast.error("Não foi possível editar a regra.", { description: descricaoErro(err) });
    }
  }

  const podeArquivarOuFlip = regra.status === "proposta" || podeSobrepor;

  return (
    <Card data-testid={`regra-${regra.id}`}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={STATUS_BADGE_VARIANT[regra.status]}>{STATUS_ROTULO[regra.status]}</Badge>
          {regra.override_platform_admin && (
            <span className="text-xs text-muted-foreground">sobreposta pelo admin da plataforma</span>
          )}
          <span className="ml-auto text-xs text-muted-foreground">Criada em {formatarData(regra.criado_em)}</span>
        </div>

        {editando ? (
          <form className="space-y-2" onSubmit={handleSalvarEdicao} data-testid={`regra-${regra.id}-editar-form`}>
            <Textarea
              rows={2}
              maxLength={TEXTO_MAX}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
            />
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={!texto.trim() || editar.isPending}>
                {editar.isPending ? "Salvando…" : "Salvar"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setTexto(regra.texto);
                  setEditando(false);
                }}
                disabled={editar.isPending}
              >
                Cancelar
              </Button>
            </div>
          </form>
        ) : (
          <p className="text-sm">{regra.texto}</p>
        )}

        {regra.decidido_em && (
          <p className="text-xs text-muted-foreground">Decidida em {formatarData(regra.decidido_em)}</p>
        )}

        {!editando && (
          <div className="flex flex-wrap gap-2">
            {regra.status === "proposta" && (
              <>
                <Button size="sm" onClick={handleAprovar} disabled={aprovar.isPending}>
                  <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                  {aprovar.isPending ? "Aprovando…" : "Aprovar"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleRejeitarOuArquivar}
                  disabled={rejeitar.isPending}
                >
                  <X className="mr-1 h-3.5 w-3.5" />
                  {rejeitar.isPending ? "Rejeitando…" : "Rejeitar"}
                </Button>
              </>
            )}
            {regra.status === "aprovada" && (
              <>
                <Button size="sm" variant="ghost" onClick={() => setEditando(true)}>
                  <Pencil className="mr-1 h-3.5 w-3.5" /> Editar
                </Button>
                {podeArquivarOuFlip && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleRejeitarOuArquivar}
                    disabled={rejeitar.isPending}
                  >
                    {rejeitar.isPending ? "Arquivando…" : "Arquivar"}
                  </Button>
                )}
              </>
            )}
            {regra.status === "rejeitada" && podeSobrepor && (
              <Button size="sm" variant="outline" onClick={handleAprovar} disabled={aprovar.isPending}>
                {aprovar.isPending ? "Reativando…" : "Reativar"}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GuiaEfetivoSection() {
  const [aberto, setAberto] = useState(false);
  const { atual, historico, total, showSkeleton, error } = useGuiaEfetivo({ page: 1, pageSize: 10 });

  return (
    <Card data-testid="guia-efetivo-secao">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-muted-foreground" />
            <span className="font-semibold">Guia efetivo (guia da empresa + regras aprovadas)</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setAberto(!aberto)}>
            <History className="mr-1 h-3.5 w-3.5" />
            {aberto ? "Ocultar histórico" : `Ver histórico (${total})`}
          </Button>
        </div>

        {error ? (
          <p className="text-sm text-destructive">Não foi possível carregar o guia efetivo.</p>
        ) : showSkeleton ? (
          <Skeleton className="h-24 w-full" />
        ) : atual === null ? (
          <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <p className="text-sm">
              Nenhum guia de estilo ativo ainda — ative uma versão em "Guias de Estilo" para ver o guia efetivo.
            </p>
          </div>
        ) : (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm" data-testid="guia-efetivo-texto">
            {atual.texto}
          </pre>
        )}

        {aberto && (
          <div className="space-y-2 border-t pt-3" data-testid="guia-efetivo-historico">
            {historico.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sem histórico ainda.</p>
            ) : (
              historico.map((g) => (
                <div key={g.id} className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{formatarData(g.criado_em)}</span>
                  <span className="font-mono">{g.sha256.slice(0, 12)}…</span>
                </div>
              ))
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ConfiguracoesProponente() {
  const { configuracoes, showSkeleton } = useConfiguracoesPlataforma();

  return (
    <Card data-testid="regras-config-proponente">
      <CardContent className="space-y-2 p-4">
        <p className="text-sm font-semibold">Configurações do proponente de regras</p>
        {showSkeleton ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Debounce: {configuracoes?.rule_proposal_debounce_seconds ?? "—"} s · Máx. rejeições por
              chamada: {configuracoes?.max_rejections_per_proposal ?? "—"}
            </p>
            <p className="text-xs text-muted-foreground">
              🔴 Somente leitura nesta versão — são parâmetros do motor (não uma coluna de
              configurações da plataforma); torná-los editáveis exige uma migração.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="regras-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da organização e da plataforma.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function ListaSkeleton() {
  return (
    <div className="space-y-3" data-testid="regras-loading">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-24 w-full" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar as regras.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
