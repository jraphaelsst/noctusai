/** Julia › Agente cards (b)+(c): per-connection Julia switch and handoff target. */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  mensagemErroJulia,
  useAtualizarConexaoAgente,
  type JuliaAgente,
  type JuliaConexaoAgente,
} from "@/hooks/useJuliaAgente";
import { useTeamMembers } from "@/hooks/useTeam";

const SEM_NUMEROS =
  "Cadastre ao menos um número autorizado nesta conexão (Configurações) para poder ligar a Julia.";

function ConexaoRow({
  conexao,
  isAdmin,
  admins,
  membrosErro,
}: {
  conexao: JuliaConexaoAgente;
  isAdmin: boolean;
  admins: { id: string; nome: string }[];
  membrosErro: boolean;
}) {
  const atualizar = useAtualizarConexaoAgente();
  const [erro, setErro] = useState<string | null>(null);
  const semNumeros = conexao.authorized_numbers_count === 0;
  // Turning OFF must stay possible even if the list was emptied after switching on.
  const bloqueadoLigar = semNumeros && !conexao.agente_leads_ativo;
  const alvo = conexao.agente_handoff_notificar_user_id;
  const alvoForaDaLista = !!alvo && !admins.some((a) => a.id === alvo);

  function enviar(body: { agente_leads_ativo: boolean; agente_handoff_notificar_user_id?: string | null }, ok: string) {
    setErro(null);
    atualizar.mutate(
      { connectionId: conexao.connection_id, body },
      {
        onSuccess: () => toast.success(ok),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar a alteração.")),
      },
    );
  }

  const switchId = `julia-${conexao.connection_id}`;
  return (
    <li className="space-y-3 rounded-md border p-4" data-testid={`julia-conexao-${conexao.connection_id}`}>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={switchId} className="text-sm font-medium">
          Julia atende leads neste número
          <span className="ml-2 font-normal text-muted-foreground">({conexao.label})</span>
        </label>
        <div className="flex items-center gap-2">
          {atualizar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          <Switch
            id={switchId}
            checked={conexao.agente_leads_ativo}
            disabled={!isAdmin || atualizar.isPending || bloqueadoLigar}
            onCheckedChange={(v) =>
              enviar(
                { agente_leads_ativo: v },
                v ? "Julia ligada neste número" : "Julia desligada neste número",
              )
            }
          />
        </div>
      </div>

      {bloqueadoLigar && (
        <p className="text-xs text-amber-700" data-testid="motivo-desabilitado">
          {SEM_NUMEROS}
        </p>
      )}
      {!isAdmin && (
        <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>
      )}
      {erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="conexao-erro">
          {erro}
        </p>
      )}

      <div className="space-y-1">
        <label htmlFor={`${switchId}-handoff`} className="text-xs text-muted-foreground">
          Quando um lead pedir atendimento humano, avisar
        </label>
        <select
          id={`${switchId}-handoff`}
          className="flex h-9 w-full max-w-xs rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
          value={alvo ?? ""}
          disabled={!isAdmin || atualizar.isPending}
          onChange={(e) =>
            enviar(
              {
                agente_leads_ativo: conexao.agente_leads_ativo,
                agente_handoff_notificar_user_id: e.target.value || null,
              },
              "Destinatário do aviso atualizado",
            )
          }
        >
          <option value="">Dono da conexão</option>
          {alvoForaDaLista && <option value={alvo!}>Usuário configurado (fora da lista)</option>}
          {admins.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nome}
            </option>
          ))}
        </select>
        {membrosErro && (
          <p className="text-xs text-muted-foreground" data-testid="membros-erro">
            Não foi possível listar os membros; só "Dono da conexão" está disponível.
          </p>
        )}
      </div>
    </li>
  );
}

export function JuliaConexoesCard({ data, isAdmin }: { data: JuliaAgente; isAdmin: boolean }) {
  const team = useTeamMembers();
  // Only owner/admin of the org can receive a handoff (server re-checks: 422 destinatario_invalido).
  const admins = (team.data ?? [])
    .filter((m) => m.org_role === "owner" || m.org_role === "admin")
    .map((m) => ({ id: m.id, nome: m.nome || m.email }));

  return (
    <Card data-testid="julia-conexoes-card">
      <CardHeader>
        <CardTitle className="text-base">Julia nos números do WhatsApp</CardTitle>
        <CardDescription>
          Números da lista de autorizados continuam no One Chat. Conversas NOVAS de qualquer outra pessoa são atendidas
          pela Julia. Conversas que já existiam quando você liga o interruptor nunca são respondidas por ela.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {data.conexoes.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="sem-conexoes">
            Nenhuma conexão WhatsApp. Adicione uma em{" "}
            <a href="/conexoes" className="text-primary underline">
              Conexões
            </a>
            .
          </p>
        ) : (
          <ul className="space-y-3">
            {data.conexoes.map((c) => (
              <ConexaoRow
                key={c.connection_id}
                conexao={c}
                isAdmin={isAdmin}
                admins={admins}
                membrosErro={team.isError}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
