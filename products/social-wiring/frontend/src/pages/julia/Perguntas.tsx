/**
 * Julia › Perguntas (`/julia/perguntas`) — MOVED to the agents app (julia-v2 Q6: one qualification standard there).
 * Kept as a read-only notice so old bookmarks work; the stored selection is not deleted.
 */
import { MovidoParaAgentes } from "@/components/julia/MovidoParaAgentes";
import { JULIA_PAGES } from "@/nav/julia";

export default function JuliaPerguntas() {
  return (
    <MovidoParaAgentes
      pagina={JULIA_PAGES.perguntas.name}
      explicacao="As perguntas e a qualificação do lead agora fazem parte do padrão de qualificação da Julia, configurado no app de agentes."
    />
  );
}
