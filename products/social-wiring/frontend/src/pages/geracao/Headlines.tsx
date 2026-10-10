/**
 * Gerar headlines — form + history (P7, `/media-creation/headlines?who=me|public|viral`,
 * `?lote=` opens a batch result). contract §7.7, page-map-v2 §17.
 * An unknown or absent `who` behaves as `viral` (CoreStudio). The progress block shows
 * the REAL `etapa` and counters of the running batch (3 s poll in the hook), never
 * rotating messages. The form is locked while a batch of the marca is running.
 */
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { FormMePublico } from "@/components/geracao/headlines/FormMePublico";
import { FormViral } from "@/components/geracao/headlines/FormViral";
import { HeadlinesGeradasModal } from "@/components/geracao/headlines/HeadlinesGeradasModal";
import { HistoricoLotes } from "@/components/geracao/headlines/HistoricoLotes";
import { ProgressoLote } from "@/components/geracao/headlines/lote";
import { emAndamento } from "@/components/geracao/labels";
import { MarcaSwitcher } from "@/components/pesquisa/MarcaSwitcher";
import { Button } from "@/components/ui/button";
import { useLotes } from "@/hooks/geracao/useHeadlines";
import { useMarcaPesquisa } from "@/hooks/useMarcaPesquisa";
import { useMarcas } from "@/hooks/useMarcas";
import type { HeadlineLote } from "@/types/geracao";

type Who = "me" | "public" | "viral";

const TITULOS: Record<Who, { titulo: string; descricao: string }> = {
  me: { titulo: "Gerar headlines sobre Mim", descricao: "Headlines com base nas suas convicções, hábitos e histórias de vida." },
  public: {
    titulo: "Gerar headlines sobre Meu publico",
    descricao: "Headlines com base em dores, desejos, crenças e demais características do seu público alvo.",
  },
  viral: {
    titulo: "Gerar headlines sobre Assuntos virais",
    descricao: "Headlines com assuntos em alta que conectam com o seu público-alvo.",
  },
};

export function resolverWho(raw: string | null): Who {
  return raw === "me" || raw === "public" ? raw : "viral";
}

export default function Headlines() {
  const [params, setParams] = useSearchParams();
  const who = resolverWho(params.get("who"));
  const marcasQ = useMarcas();
  const marcas = marcasQ.data ?? [];
  const { marcaId, escolherMarca } = useMarcaPesquisa(marcas);

  // Same key as the history's first page, so this is one request, not two.
  const recentes = useLotes(marcaId);
  const ativo = recentes.data?.items.find((l) => emAndamento(l.status)) ?? null;

  const [verId, setVerId] = useState<string | null>(null);
  const [acompanhando, setAcompanhando] = useState<string | null>(null);

  // `?lote=` auto-opens that batch's result once, then is consumed.
  const loteParam = params.get("lote");
  useEffect(() => {
    if (!loteParam) return;
    setVerId(loteParam);
    const next = new URLSearchParams(params);
    next.delete("lote");
    setParams(next, { replace: true });
  }, [loteParam]); // eslint-disable-line react-hooks/exhaustive-deps

  // The batch this page started: open its result when the REAL status turns terminal.
  const seguido = acompanhando ? recentes.data?.items.find((l) => l.id === acompanhando) : undefined;
  useEffect(() => {
    if (seguido && !emAndamento(seguido.status)) {
      setVerId(seguido.id);
      setAcompanhando(null);
    }
  }, [seguido?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  function criado(lote: HeadlineLote) {
    setAcompanhando(lote.id);
  }

  const { titulo, descricao } = TITULOS[who];

  return (
    <div className="space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{titulo}</h1>
          <p className="text-sm text-muted-foreground">{descricao}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <MarcaSwitcher marcas={marcas} marcaId={marcaId} onChange={escolherMarca} />
          <Button asChild variant="outline">
            <Link to="/media-creation/headlines/gerar">
              <ArrowLeft className="mr-1 h-4 w-4" /> Voltar
            </Link>
          </Button>
        </div>
      </header>

      {ativo ? (
        <ProgressoLote lote={ativo} />
      ) : null}

      <section className="rounded-lg border p-4">
        {who === "viral" ? (
          <FormViral marcaId={marcaId} bloqueado={!!ativo} onCriado={criado} />
        ) : (
          <FormMePublico key={who} who={who} marcaId={marcaId} bloqueado={!!ativo} onCriado={criado} />
        )}
      </section>

      <HistoricoLotes marcaId={marcaId} onVer={(l) => setVerId(l.id)} />

      <HeadlinesGeradasModal
        open={!!verId}
        onOpenChange={(o) => !o && setVerId(null)}
        loteId={verId}
        marcaId={marcaId}
        onReprocessado={(id) => setAcompanhando(id)}
      />
    </div>
  );
}
