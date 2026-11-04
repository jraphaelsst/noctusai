/**
 * Julia › Agente card: "Conexão com a plataforma" — READ-ONLY status of the grant that lets the WhatsApp talk to
 * Julia (masked token, status, times, "Testar conexão"), plus which version of Julia is live. Nothing is pasted or
 * configured here: the platform manages the connection and Julia's core (julia-line CONTRACT §0 / §D).
 */
import { AlertCircle } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { JuliaAgente } from "@/hooks/useJuliaAgente";
import { ConexaoPlataformaBody } from "./ConexaoPlataforma";

export function AgentsLinkCard({ data, isAdmin }: { data: JuliaAgente; isAdmin: boolean }) {
  const st = data.status_agente;
  return (
    <Card data-testid="agents-link-card" id="conexao-plataforma">
      <CardHeader>
        <CardTitle className="text-base">Conexão com a plataforma</CardTitle>
        <CardDescription>
          A conexão que deixa o WhatsApp falar com a Julia é gerenciada pela NoctusAI. Aqui você só acompanha se está funcionando.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConexaoPlataformaBody conexao={data.conexao_plataforma} canTest={isAdmin} />

        {st && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 border-t pt-3 text-sm sm:grid-cols-4" data-testid="agent-status">
            <div>
              <dt className="text-xs text-muted-foreground">Agente</dt>
              <dd>{st.nome} {st.ativo ? "(ativo)" : "(inativo)"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Versão ativa</dt>
              <dd>{st.versao_ativa ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Modelo</dt>
              <dd>{[st.provider, st.model].filter(Boolean).join(" / ") || "—"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Chave do LLM</dt>
              <dd>{st.llm_configurado ? "Configurada" : "Ausente"}</dd>
            </div>
          </dl>
        )}

        {data.erro && (
          <p role="alert" className="flex items-start gap-2 text-sm text-destructive" data-testid="link-erro">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{data.erro}</span>
          </p>
        )}
      </CardContent>
    </Card>
  );
}
