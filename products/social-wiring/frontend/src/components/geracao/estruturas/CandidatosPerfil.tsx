/**
 * Ambiguity of a typed profile name (422 `perfil_ambiguo` + `candidatos`; or `perfil_nao_encontrado_na_biblioteca` +
 * `sugestoes`): a form cannot ask conversationally, so it renders the candidates as buttons. Picking one re-submits
 * with `referencia: {tipo: "perfil", perfil_ids: [id]}` (the caller's `onEscolher`).
 */
import { Button } from "@/components/ui/button";
import type { PerfilCandidato } from "@/types/estruturas";

interface Props {
  candidatos: PerfilCandidato[];
  /** `ambiguo` = several matched; `sugestao` = none matched, these are the closest. */
  tipo?: "ambiguo" | "sugestao";
  onEscolher: (c: PerfilCandidato) => void;
  disabled?: boolean;
}

export function CandidatosPerfil({ candidatos, tipo = "ambiguo", onEscolher, disabled }: Props) {
  if (candidatos.length === 0) return null;
  return (
    <div role="alert" className="space-y-2 rounded-md border border-warning/40 bg-warning-light p-3 text-sm" data-testid="candidatos-perfil">
      <p>
        {tipo === "ambiguo"
          ? "Mais de um perfil combina com o que você escreveu. Qual deles?"
          : "Não encontramos esse perfil na biblioteca. Quis dizer:"}
      </p>
      <div className="flex flex-wrap gap-2">
        {candidatos.map((c) => (
          <Button key={c.perfil_id} type="button" size="sm" variant="outline" disabled={disabled} onClick={() => onEscolher(c)}>
            @{c.handle}
            {c.nome ? ` · ${c.nome}` : ""}
          </Button>
        ))}
      </div>
    </div>
  );
}
