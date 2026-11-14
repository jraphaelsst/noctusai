/**
 * Edição de Fotos — Revisão de Lote (`/edicao-fotos/lotes/:loteId/revisao`, `status_pagina` row
 * `edicao-fotos-revisao`, migration 128). The screen itself lives in `components/edicao-fotos/RevisaoLote.tsx`
 * (shared with ImobShotAI's funnel); this page only reads the route param.
 */
import { useParams } from "react-router-dom";

import { RevisaoLote } from "@/components/edicao-fotos/RevisaoLote";

export default function LoteRevisao() {
  const { loteId } = useParams<{ loteId: string }>();
  return <RevisaoLote loteId={loteId} />;
}
