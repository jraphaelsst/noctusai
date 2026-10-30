/**
 * Julia › Agente — the line list: "esta linha atende leads com a Julia" (on/off) and who is told when a lead goes to
 * a human (default: the org owner). Routing only — no behaviour, prompt or rule lives in SW.
 */
import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { mensagemErroJulia } from "@/hooks/useJuliaAgente";
import { useAtualizarLinha, type LinhaRoteamento, type LinhaUpdate, type Roteamento } from "@/hooks/useJuliaRoteamento";
import { useTeamMembers } from "@/hooks/useTeam";

const SEM_NUMEROS =
  "Cadastre ao menos um número autorizado nesta linha (Configurações) para poder ligar a Julia.";

function LinhaRow({
  linha,
  isAdmin,
  admins,
  membrosErro,
}: {
  linha: LinhaRoteamento;
  isAdmin: boolean;
  admins: { id: string; nome: string }[];
  membrosErro: boolean;
}) {
  const atualizar = useAtualizarLinha();
  const [erro, setErro] = useState<string | null>(null);
  // Turning OFF must stay possible even if the list was emptied after switching on.
  const bloqueadoLigar = linha.numeros_autorizados === 0 && !linha.alimenta;
  const alvo = linha.destino_handoff_user_id;
  const alvoForaDaLista = !!alvo && !admins.some((a) => a.id === alvo);

  function enviar(body: LinhaUpdate, ok: string) {
    setErro(null);
    atualizar.mutate(
      { connectionId: linha.connection_id, body },
      {
        onSuccess: () => toast.success(ok),
        onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível salvar a alteração.")),
      },
    );
  }

  const switchId = `julia-${linha.connection_id}`;
  return (
    <li className="space-y-3 rounded-md border p-4" data-testid={`julia-linha-${linha.connection_id}`}>
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={switchId} className="text-sm font-medium">
          Esta linha atende leads com a Julia
          <span className="ml-2 font-normal text-muted-foreground">({linha.label})</span>
        </label>
        <div className="flex items-center gap-2">
          {atualizar.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          <Switch
            id={switchId}
            checked={linha.alimenta}
            disabled={!isAdmin || atualizar.isPending || bloqueadoLigar}
            onCheckedChange={(v) =>
              enviar({ alimenta: v }, v ? "Esta linha agora atende leads com a Julia" : "Esta linha não atende mais leads com a Julia")
            }
          />
        </div>
      </div>

      {bloqueadoLigar && (
        <p className="text-xs text-warning-foreground" data-testid="motivo-desabilitado">
          {SEM_NUMEROS}
        </p>
      )}
      {!isAdmin && (
        <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode alterar.</p>
      )}
      {erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="linha-erro">
          {erro}
        </p>
      )}

      <div className="space-y-1">
        <label htmlFor={`${switchId}-handoff`} className="text-xs text-muted-foreground">
          Quando a Julia passar um lead para atendimento humano, avisar
        </label>
        <select
          id={`${switchId}-handoff`}
          className="flex h-9 w-full max-w-xs rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
          value={alvo ?? ""}
          disabled={!isAdmin || atualizar.isPending}
          onChange={(e) =>
            enviar(
              { alimenta: linha.alimenta, destino_handoff_user_id: e.target.value || null },
              "Destinatário do aviso atualizado",
            )
          }
        >
          <option value="">Dono da organização (padrão)</option>
          {alvoForaDaLista && <option value={alvo!}>Usuário configurado (fora da lista)</option>}
          {admins.map((a) => (
            <option key={a.id} value={a.id}>
              {a.nome}
            </option>
          ))}
        </select>
        {membrosErro && (
          <p className="text-xs text-muted-foreground" data-testid="membros-erro">
            Não foi possível listar os membros; só o dono da organização está disponível.
          </p>
        )}
      </div>
    </li>
  );
}

export function RoteamentoCard({ data, isAdmin }: { data: Roteamento; isAdmin: boolean }) {
  const team = useTeamMembers();
  // Only owner/admin of the org can receive a handoff (server re-checks: 422 destinatario_invalido).
  const admins = (team.data ?? [])
    .filter((m) => m.org_role === "owner" || m.org_role === "admin")
    .map((m) => ({ id: m.id, nome: m.nome || m.email }));

  return (
    <Card data-testid="julia-roteamento-card">
      <CardHeader>
        <CardTitle className="text-base">Linhas de WhatsApp</CardTitle>
        <CardDescription>
          Escolha quais números do WhatsApp da sua organização alimentam a Julia. Números da lista de autorizados
          continuam no One Chat. Conversas NOVAS de qualquer outra pessoa são atendidas pela Julia; conversas que já
          existiam quando você liga a linha nunca são respondidas por ela.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {data.linhas.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="sem-linhas">
            Nenhuma linha de WhatsApp. Adicione uma em{" "}
            <a href="/conexoes" className="text-primary underline">
              Conexões
            </a>
            .
          </p>
        ) : (
          <ul className="space-y-3">
            {data.linhas.map((l) => (
              <LinhaRow key={l.connection_id} linha={l} isAdmin={isAdmin} admins={admins} membrosErro={team.isError} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
