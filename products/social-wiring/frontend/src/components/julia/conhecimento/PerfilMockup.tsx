/** Phone mockup of the WhatsApp business profile (Julia › Conhecimento › Perfil). */
import { AlertCircle } from "lucide-react";

export const BANNER_PERFIL = "Aplicado quando a API oficial estiver ativa";

export function PerfilMockup({ dados }: { dados: Record<string, unknown> }) {
  const s = (k: string) => (typeof dados[k] === "string" ? (dados[k] as string) : "");
  const nome = s("nome_exibicao") || "Julia";
  return (
    <div className="space-y-2" data-testid="perfil-mockup">
      <div className="mx-auto w-64 rounded-[2rem] border-4 border-foreground/80 bg-background p-3 shadow">
        <div className="flex flex-col items-center gap-1 border-b pb-3 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted text-xl font-semibold">
            {nome.slice(0, 1).toUpperCase()}
          </div>
          <p className="font-semibold">{nome}</p>
          <p className="text-xs text-muted-foreground">{s("sobre") || "Disponível 24h"}</p>
        </div>
        <dl className="space-y-2 pt-3 text-xs">
          <div><dt className="font-medium">Descrição</dt><dd className="whitespace-pre-wrap text-muted-foreground">{s("descricao") || "—"}</dd></div>
          <div><dt className="font-medium">Endereço</dt><dd className="text-muted-foreground">{s("endereco") || "—"}</dd></div>
          <div><dt className="font-medium">E-mail</dt><dd className="text-muted-foreground">{s("email") || "—"}</dd></div>
          <div><dt className="font-medium">Site</dt><dd className="text-muted-foreground">{s("site") || "—"}</dd></div>
        </dl>
      </div>
      <p className="flex items-start gap-1.5 rounded-md bg-amber-50 p-2 text-xs text-amber-900" data-testid="perfil-banner">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {BANNER_PERFIL}
      </p>
    </div>
  );
}
