/**
 * Lais › Perguntas essenciais (`/lais/perguntas`, status_pagina `lais_perguntas`).
 *
 * One query (`GET /api/lais/perguntas`) + one full-replace save. The local draft
 * lives in `edits` (chave → {ativa, qualificatoria}) over the server catalogue;
 * limits and locks are enforced in the UI for clarity but the server decides.
 * Loading = two signals off `data` (never `isLoading`).
 */
import { useMemo, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useIsOrgAdmin } from "@noctusai/lib/design-system";

import { Button } from "@/components/ui/button";
import { FaqQualificatoria } from "@/components/lais/perguntas/FaqQualificatoria";
import { PerguntaRow } from "@/components/lais/perguntas/PerguntaRow";
import {
  mensagemErroPerguntas,
  useLaisPerguntas,
  useSalvarPerguntas,
  type LaisPergunta,
} from "@/hooks/useLaisPerguntas";
import { LAIS_LABEL, LAIS_PAGES } from "@/nav/lais";

type Edit = { ativa: boolean; qualificatoria: boolean };

export default function LaisPerguntas() {
  const isAdmin = useIsOrgAdmin();
  const q = useLaisPerguntas();
  const salvar = useSalvarPerguntas();
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [categoria, setCategoria] = useState<string | null>(null);
  const [todas, setTodas] = useState(false);
  const showSkeleton = q.isPending && !q.data;
  const isRefreshing = q.isFetching && !!q.data;

  const catalogo = useMemo(() => q.data?.catalogo ?? [], [q.data]);
  const limites = q.data?.limites ?? { max_ativas: 8, max_qualificatorias: 5 };
  const estado = (p: LaisPergunta): Edit => edits[p.chave] ?? { ativa: p.ativa, qualificatoria: p.qualificatoria };

  const ativas = catalogo.filter((p) => estado(p).ativa);
  const qualificatorias = ativas.filter((p) => estado(p).qualificatoria);
  const categorias = useMemo(() => Array.from(new Set(catalogo.map((p) => p.categoria))), [catalogo]);
  const sujo = Object.keys(edits).length > 0;

  const visiveis = catalogo.filter(
    (p) => (categoria === null || p.categoria === categoria) && (todas || estado(p).ativa),
  );

  function set(p: LaisPergunta, patch: Partial<Edit>) {
    setEdits((prev) => ({ ...prev, [p.chave]: { ...estado(p), ...patch } }));
  }

  function guardar() {
    salvar.mutate(
      ativas.map((p) => ({ chave: p.chave, qualificatoria: estado(p).qualificatoria })),
      {
        onSuccess: () => {
          setEdits({});
          toast.success("A Julia irá mudar seu comportamento no atendimento, fazendo as perguntas adicionadas.");
        },
        onError: (e) => toast.error(mensagemErroPerguntas(e, "Não foi possível salvar as perguntas.")),
      },
    );
  }

  return (
    <div className="container max-w-4xl space-y-6 py-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">
            {LAIS_LABEL} · {LAIS_PAGES.perguntas.name}
          </h1>
          <p className="text-sm text-muted-foreground">
            Personalize o que a Julia deve perguntar a cada lead.
            {q.data && (
              <span data-testid="perguntas-contagem">
                {" "}
                Perguntas ativas ({ativas.length}/{limites.max_ativas}) · qualificatórias ({qualificatorias.length}/
                {limites.max_qualificatorias})
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isRefreshing && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" data-testid="perguntas-refreshing">
              <Loader2 className="h-3 w-3 animate-spin" /> Atualizando…
            </span>
          )}
          {isAdmin && (
            <Button onClick={guardar} disabled={!sujo || salvar.isPending} data-testid="perguntas-salvar">
              {salvar.isPending && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              Salvar
            </Button>
          )}
        </div>
      </header>

      {showSkeleton ? (
        <div className="space-y-3" data-testid="perguntas-skeleton">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      ) : q.data ? (
        <>
          <FaqQualificatoria />
          {!isAdmin && (
            <p className="text-xs text-muted-foreground" data-testid="perguntas-somente-leitura">
              Somente owners e admins podem alterar as perguntas.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filtrar por categoria">
            <Button
              size="sm"
              variant={categoria === null ? "default" : "outline"}
              onClick={() => setCategoria(null)}
              data-testid="categoria-todas"
            >
              Todas as categorias
            </Button>
            {categorias.map((c) => (
              <Button
                key={c}
                size="sm"
                variant={categoria === c ? "default" : "outline"}
                onClick={() => setCategoria(c)}
                data-testid={`categoria-${c}`}
              >
                {c}
              </Button>
            ))}
            <Button
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={() => setTodas((v) => !v)}
              data-testid="perguntas-mostrar-todas"
            >
              {todas ? "Mostrar só ativas" : "Mostrar todas"}
            </Button>
          </div>
          {visiveis.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted-foreground" data-testid="perguntas-vazio">
              {todas ? "Nenhuma pergunta nesta categoria." : "Nenhuma pergunta ativa. Use “Mostrar todas” para adicionar."}
            </p>
          ) : (
            <ul className="divide-y rounded-lg border px-4" data-testid="perguntas-lista">
              {visiveis.map((p) => (
                <PerguntaRow
                  key={p.chave}
                  pergunta={p}
                  ativa={estado(p).ativa}
                  qualificatoria={estado(p).qualificatoria}
                  limiteAtivas={ativas.length >= limites.max_ativas}
                  limiteQualif={qualificatorias.length >= limites.max_qualificatorias}
                  disabled={!isAdmin}
                  onToggle={(ativa) => set(p, ativa ? { ativa } : { ativa, qualificatoria: false })}
                  onQualificatoria={(qualificatoria) => set(p, { qualificatoria })}
                />
              ))}
            </ul>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center gap-3 py-16 text-muted-foreground" data-testid="perguntas-erro">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm">Não foi possível carregar as perguntas.</p>
          <Button variant="outline" size="sm" onClick={() => q.refetch()}>
            Tentar de novo
          </Button>
        </div>
      )}
    </div>
  );
}
