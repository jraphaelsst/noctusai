/** Julia › Agente card: the link with the Agents product (token + link health). STATUS only; behaviour is configured in agents. */
import { useState } from "react";
import { toast } from "sonner";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mensagemErroJulia, useSalvarTokenAgents, type JuliaAgente } from "@/hooks/useJuliaAgente";

export function AgentsLinkCard({ data, isAdmin }: { data: JuliaAgente; isAdmin: boolean }) {
  const salvar = useSalvarTokenAgents();
  const [token, setToken] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const st = data.status_agente;

  function enviar() {
    const valor = token.trim();
    if (!valor) return;
    setErro(null);
    salvar.mutate(
      { token: valor },
      {
        onSuccess: () => {
          // Write-only: the secret leaves the page the moment it is stored.
          setToken("");
          toast.success("Token do Agents salvo");
        },
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar o token.")),
      },
    );
  }

  return (
    <Card data-testid="agents-link-card">
      <CardHeader>
        <CardTitle className="text-base">Conexão com o Agents</CardTitle>
        <CardDescription>A Julia roda no produto Agents; este token autoriza o WhatsApp a falar com ela.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2 text-sm" data-testid="token-status">
          {data.token_configurado ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-success" />
              <span>Token configurado</span>
            </>
          ) : (
            <>
              <AlertCircle className="h-4 w-4 text-warning-foreground" />
              <span>Token não configurado</span>
            </>
          )}
        </div>

        {st && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4" data-testid="agent-status">
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

        {isAdmin ? (
          <div className="space-y-2">
            <Label htmlFor="agents-token">{data.token_configurado ? "Substituir token" : "Colar token do canal"}</Label>
            <div className="flex gap-2">
              <Input
                id="agents-token"
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Cole aqui o token do canal (não é exibido depois)"
              />
              <Button onClick={enviar} disabled={salvar.isPending || token.trim().length < 8} data-testid="salvar-token">
                {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                Salvar token
              </Button>
            </div>
            {erro && (
              <p role="alert" className="text-sm text-destructive" data-testid="token-erro">
                {erro}
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar o token.</p>
        )}
      </CardContent>
    </Card>
  );
}
