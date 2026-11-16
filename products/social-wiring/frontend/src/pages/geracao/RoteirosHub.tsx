/**
 * Roteiros (`/media-creation/chat/*`) — the ONE CoreStudio entry for everything about headlines and
 * roteiros. The seed `SectionTabsPage` owns the URL <-> tab sync; each section is an existing page,
 * rendered embedded (no second h1) and gated by the status_pagina key it was reached through before.
 *
 * Old URLs (`/media-creation/headlines/*`, `/roteiros`, `/headlines-roteiros`) redirect here — see
 * `redirectsRoteiros.tsx`.
 */
import { lazy, Suspense } from "react";
import { SectionTabsPage, type SectionTab } from "@noctusai/lib/components";

import { EmbeddedPagina } from "@/components/geracao/PaginaCabecalho";
import { usePaginaVisivel } from "@/hooks/geracao/usePaginaVisivel";

import Chat from "./Chat";
import { ROTEIROS_BASE } from "./redirectsRoteiros";

const HeadlinesGerar = lazy(() => import("./HeadlinesGerar"));
const HeadlinesFavoritas = lazy(() => import("./HeadlinesFavoritas"));
const HeadlinesSugeridas = lazy(() => import("./HeadlinesSugeridas"));
const Roteiros = lazy(() => import("./Roteiros"));
const HeadlinesRoteiros = lazy(() => import("./HeadlinesRoteiros"));

const secao = (node: React.ReactNode) => () => (
  <EmbeddedPagina>
    <Suspense fallback={null}>{node}</Suspense>
  </EmbeddedPagina>
);

export default function RoteirosHub() {
  const visivel = usePaginaVisivel();
  const sections: SectionTab[] = [
    { key: "roteiro", label: "Roteiro", visible: visivel("media-creation-chat"), render: secao(<Chat />) },
    { key: "gerar-headlines", label: "Gerar Headlines", visible: visivel("media-creation-headlines-gerar"), render: secao(<HeadlinesGerar />) },
    { key: "favoritas", label: "Headlines Favoritas", visible: visivel("media-creation-headlines-favoritas"), render: secao(<HeadlinesFavoritas />) },
    { key: "sugeridas", label: "Headlines sugeridas", visible: visivel("media-creation-headlines-sugeridas"), render: secao(<HeadlinesSugeridas />) },
    { key: "meus-roteiros", label: "Meus Roteiros", visible: visivel("media-creation-roteiros"), render: secao(<Roteiros />) },
    { key: "headlines-e-roteiros", label: "Headlines e Roteiros", visible: visivel("media-creation-headlines-roteiros"), render: secao(<HeadlinesRoteiros />) },
  ];
  return (
    <div className="p-6">
      <SectionTabsPage
        basePath={ROTEIROS_BASE}
        title="Roteiros"
        description="Converse com a IA, gere headlines e acompanhe seus roteiros."
        sections={sections}
      />
    </div>
  );
}
