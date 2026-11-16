/**
 * The server could not tell which profile a name in the message means (`perfil_ambiguo`) or
 * did not find it (`perfil_nao_encontrado`): the candidates are chips; picking one sends the
 * same message again with that profile attached (Estruturas contract §6.5 / §8.3).
 */
import { Button } from "@/components/ui/button";
import type { PerfilPendente } from "@/hooks/geracao/useChat";

interface Props {
  pendente: PerfilPendente;
  desabilitado: boolean;
  onEscolher: (perfilId: string) => void;
  onDispensar: () => void;
}

export function PerfilPendenteChips({ pendente, desabilitado, onEscolher, onDispensar }: Props) {
  const ambiguo = pendente.modo === "perfil_ambiguo";
  return (
    <div role="group" aria-label="Escolha o perfil" className="space-y-2 rounded-md border border-warning/40 bg-warning-light p-3 text-sm">
      {pendente.grupos.map((g) => (
        <div key={g.trecho} className="space-y-1.5">
          <p>
            {ambiguo
              ? `Mais de um perfil combina com “${g.trecho}”. Escolha um:`
              : `Não encontramos “${g.trecho}” na biblioteca.${g.candidatos.length ? " Quis dizer:" : ""}`}
          </p>
          <div className="flex flex-wrap gap-2">
            {g.candidatos.map((c) => (
              <Button
                key={c.perfil_id}
                type="button"
                size="sm"
                variant="outline"
                disabled={desabilitado}
                onClick={() => onEscolher(c.perfil_id)}
              >
                @{c.handle}
                {c.nome ? ` — ${c.nome}` : ""}
              </Button>
            ))}
          </div>
        </div>
      ))}
      <Button type="button" size="sm" variant="ghost" onClick={onDispensar}>
        Ignorar
      </Button>
    </div>
  );
}
