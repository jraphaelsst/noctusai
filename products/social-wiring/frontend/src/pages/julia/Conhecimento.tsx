/**
 * Julia › Conhecimento (`/julia/conhecimento`) — MOVED to the agents app (julia-v2 Q1: org knowledge lives there).
 * Kept as a read-only notice so old bookmarks work; the stored sections are not deleted.
 */
import { MovidoParaAgentes } from "@/components/julia/MovidoParaAgentes";
import { JULIA_PAGES } from "@/nav/julia";

export default function JuliaConhecimento() {
  return (
    <MovidoParaAgentes
      pagina={JULIA_PAGES.conhecimento.name}
      explicacao="O conhecimento da sua empresa que a Julia usa nas conversas agora é cadastrado no app de agentes."
    />
  );
}
