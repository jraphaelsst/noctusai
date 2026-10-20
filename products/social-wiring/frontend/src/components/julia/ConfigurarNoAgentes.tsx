/** The ONE link from SW to where Julia is configured: "Configurar a Julia no app de agentes". */
import { ExternalLink } from "lucide-react";

import { urlConfigurarJulia } from "@/hooks/useJuliaRoteamento";

export function ConfigurarNoAgentes({ agentsUrl }: { agentsUrl: string | null | undefined }) {
  const href = urlConfigurarJulia(agentsUrl);
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-sm text-primary underline"
      data-testid="configurar-julia-link"
    >
      Configurar a Julia no app de agentes <ExternalLink className="h-3.5 w-3.5" />
    </a>
  ) : (
    <p className="text-xs text-muted-foreground" data-testid="configurar-julia-indisponivel">
      O endereço do app de agentes não está disponível neste ambiente.
    </p>
  );
}
