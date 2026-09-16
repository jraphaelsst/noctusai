/**
 * Edição de Fotos — Guias de estilo (`/edicao-fotos/guias`, `status_pagina`
 * row `edicao-fotos-guias`, migration 128). The company style guide's version
 * history (contract §6).
 *
 * Who: platform admin ∨ photo curator (`capacidades.pode_ativar_guia`).
 *
 * - Every version is a DRAFT until someone here activates it; the active one
 *   is what new batches snapshot at submit (in-flight batches never change).
 * - "Restaurar" clones an old version as a NEW draft — versions are immutable.
 * - "Regenerar com IA" queues the builder from the reference pool; the draft
 *   appears once the worker runs it.
 * - "Escrever guia" creates a MANUAL draft — the R1 path that needs no AI
 *   (no guide active ⇒ batch submission answers 409 `guia_nao_ativo`).
 *
 * Loading-state contract (CLAUDE.md §1 / contract §9): `showSkeleton` /
 * `isRefreshing` come pre-computed off the seed hooks — never `.isLoading`.
 */
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, FileText, Lock, RefreshCw, RotateCcw, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@noctusai/lib/api";

import {
  fotosPermissions,
  useAtivarGuia,
  useCapacidades,
  useCriarGuia,
  useGuias,
  useRegenerarGuia,
  useRestaurarGuia,
  type GuiaEstiloVersao,
} from "@/hooks/useEdicaoFotos";

const PAGE_SIZE = 20;
const TEXTO_MAX = 20000;

const STATUS_ROTULO: Record<GuiaEstiloVersao["status"], string> = {
  rascunho: "Rascunho",
  ativa: "Ativa",
  substituida: "Substituída",
};

const ORIGEM_ROTULO: Record<GuiaEstiloVersao["origem"], string> = {
  ia: "Gerada por IA",
  manual: "Escrita manualmente",
  restaurada: "Restaurada",
};

function descricaoErro(err: unknown): string | undefined {
  if (err instanceof ApiError && err.code === "pool_vazio") {
    return "O pool de referências está vazio — envie pares antes de regenerar.";
  }
  return err instanceof Error ? err.message : undefined;
}

function formatarData(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("pt-BR") : "—";
}

export default function GuiasEstilo() {
  const { capacidades, showSkeleton } = useCapacidades();
  if (showSkeleton) return <ListaSkeleton />;
  if (!fotosPermissions.podeAtivarGuia(capacidades)) return <AcessoRestrito />;
  return <GuiasView />;
}

function GuiasView() {
  const [page, setPage] = useState(1);
  const { guias, total, versaoAtiva, showSkeleton, isRefreshing, error, refetch } = useGuias({
    page,
    pageSize: PAGE_SIZE,
  });
  const regenerar = useRegenerarGuia();
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

  async function handleRegenerar() {
    try {
      await regenerar.mutateAsync();
      toast.success("Regeneração enfileirada — o rascunho aparece aqui quando ficar pronto.");
    } catch (err) {
      toast.error("Não foi possível regenerar o guia.", { description: descricaoErro(err) });
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Edição de Fotos — Guias de estilo</h1>
          <p className="text-sm text-muted-foreground">
            Cada versão nasce como rascunho. Só a versão ativa é usada nos novos lotes.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="guias-atualizando">
              <RefreshCw className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          <Button variant="outline" onClick={handleRegenerar} disabled={regenerar.isPending}>
            <Sparkles className="mr-2 h-4 w-4" />
            {regenerar.isPending ? "Enfileirando…" : "Regenerar com IA"}
          </Button>
        </div>
      </div>

      {!showSkeleton && !error && versaoAtiva === null && (
        <Card className="border-amber-500/40 bg-amber-500/5" data-testid="sem-guia-ativo">
          <CardContent className="flex items-start gap-3 p-4">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <p className="text-sm">
              Nenhum guia ativo — os lotes não podem ser submetidos até uma versão ser ativada.
            </p>
          </CardContent>
        </Card>
      )}

      <NovoGuiaForm />

      {error ? (
        <ErrorState onRetry={() => refetch()} />
      ) : showSkeleton ? (
        <ListaSkeleton />
      ) : guias.length === 0 ? (
        <Card data-testid="guias-vazio">
          <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
            <FileText className="h-10 w-10 text-muted-foreground" />
            <p className="font-medium">Nenhuma versão do guia ainda.</p>
            <p className="text-sm text-muted-foreground">Escreva uma acima ou regenere a partir do pool.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3" data-testid="guias-lista">
          {guias.map((guia) => (
            <VersaoCard key={guia.id} guia={guia} />
          ))}
          {totalPaginas > 1 && (
            <div className="flex items-center justify-center gap-3">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Anterior
              </Button>
              <span className="text-sm text-muted-foreground">
                Página {page} de {totalPaginas}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPaginas}
                onClick={() => setPage(page + 1)}
              >
                Próxima
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function NovoGuiaForm() {
  const criar = useCriarGuia();
  const [aberto, setAberto] = useState(false);
  const [texto, setTexto] = useState("");

  async function handleSalvar(e: FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    try {
      const guia = await criar.mutateAsync({ texto });
      toast.success(`Rascunho v${guia.versao} criado — ative-o para usar nos lotes.`);
      setTexto("");
      setAberto(false);
    } catch (err) {
      toast.error("Não foi possível criar o rascunho.", { description: descricaoErro(err) });
    }
  }

  if (!aberto) {
    return (
      <Button variant="secondary" onClick={() => setAberto(true)}>
        <FileText className="mr-2 h-4 w-4" /> Escrever guia
      </Button>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <form className="space-y-3" onSubmit={handleSalvar} data-testid="novo-guia-form">
          <Label htmlFor="guia-texto">Texto do guia</Label>
          <Textarea
            id="guia-texto"
            rows={10}
            maxLength={TEXTO_MAX}
            placeholder={"- Luz natural, sem HDR exagerado\n- Céu azul limpo"}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={!texto.trim() || criar.isPending}>
              {criar.isPending ? "Salvando…" : "Salvar rascunho"}
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

function VersaoCard({ guia }: { guia: GuiaEstiloVersao }) {
  const ativar = useAtivarGuia();
  const restaurar = useRestaurarGuia();
  const [expandido, setExpandido] = useState(guia.status === "ativa");
  const ativa = guia.status === "ativa";

  async function handleAtivar() {
    try {
      await ativar.mutateAsync(guia.versao);
      toast.success(`Versão ${guia.versao} ativada.`);
    } catch (err) {
      toast.error("Não foi possível ativar a versão.", { description: descricaoErro(err) });
    }
  }

  async function handleRestaurar() {
    try {
      const nova = await restaurar.mutateAsync(guia.versao);
      toast.success(`Versão ${guia.versao} restaurada como rascunho v${nova.versao}.`);
    } catch (err) {
      toast.error("Não foi possível restaurar a versão.", { description: descricaoErro(err) });
    }
  }

  return (
    <Card className={ativa ? "border-emerald-500/50" : undefined} data-testid={`guia-v${guia.versao}`}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">Versão {guia.versao}</span>
          <Badge variant={ativa ? "default" : "outline"}>{STATUS_ROTULO[guia.status]}</Badge>
          <Badge variant="secondary">{ORIGEM_ROTULO[guia.origem]}</Badge>
          {guia.gerado_de_versao !== null && (
            <span className="text-xs text-muted-foreground">a partir da v{guia.gerado_de_versao}</span>
          )}
          <span className="ml-auto text-xs text-muted-foreground">Criada em {formatarData(guia.criado_em)}</span>
        </div>
        {ativa && (
          <p className="flex items-center gap-1 text-xs text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> Ativada em {formatarData(guia.ativado_em)}
          </p>
        )}
        {expandido ? (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">{guia.texto}</pre>
        ) : (
          <p className="line-clamp-2 text-sm text-muted-foreground">{guia.texto}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" size="sm" onClick={() => setExpandido(!expandido)}>
            {expandido ? "Recolher" : "Ver texto"}
          </Button>
          {guia.status === "rascunho" && (
            <Button size="sm" onClick={handleAtivar} disabled={ativar.isPending}>
              {ativar.isPending ? "Ativando…" : "Ativar"}
            </Button>
          )}
          {guia.status === "substituida" && (
            <Button variant="outline" size="sm" onClick={handleRestaurar} disabled={restaurar.isPending}>
              <RotateCcw className="mr-1 h-3.5 w-3.5" />
              {restaurar.isPending ? "Restaurando…" : "Restaurar"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function AcessoRestrito() {
  return (
    <div className="mx-auto max-w-2xl p-6">
      <Card data-testid="guias-restrito">
        <CardContent className="flex flex-col items-center gap-2 py-16 text-center">
          <Lock className="h-10 w-10 text-muted-foreground" />
          <p className="font-medium">Restrito a administradores da plataforma e curadores de fotos.</p>
        </CardContent>
      </Card>
    </div>
  );
}

function ListaSkeleton() {
  return (
    <div className="space-y-3" data-testid="guias-loading">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-28 w-full" />
      ))}
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <p className="font-medium">Não foi possível carregar os guias de estilo.</p>
        <Button variant="outline" onClick={onRetry}>
          Tentar novamente
        </Button>
      </CardContent>
    </Card>
  );
}
