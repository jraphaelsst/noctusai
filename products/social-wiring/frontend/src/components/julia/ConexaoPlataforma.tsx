/**
 * Julia › the platform connection (read-only). The grant that lets the WhatsApp talk to Julia is minted and rotated
 * by NoctusAI (julia-line CONTRACT §D): SW users see whether it works, never edit it. The token is shown MASKED
 * (first 4 + last 4) and the full value never reaches the browser.
 *
 * Used by the Agente page (inside `AgentsLinkCard`) and by Configurações (the "agents" row of the api-keys list),
 * so both say the same thing. `ConexaoPlataformaBody` renders a given `conexao`; `ConexaoPlataformaDoAgente` reads it.
 */
import { AlertCircle, CheckCircle2, CircleAlert, Loader2, Plug } from "lucide-react";
import { toast } from "sonner";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  mensagemErroJulia,
  useJuliaAgente,
  useVerificarConexaoPlataforma,
  type ConexaoPlataforma,
  type StatusConexaoPlataforma,
} from "@/hooks/useJuliaAgente";

type VarianteBadge = "default" | "secondary" | "destructive" | "outline";

const STATUS: Record<StatusConexaoPlataforma, { rotulo: string; variante: VarianteBadge }> = {
  ativa: { rotulo: "Conectada", variante: "default" },
  nao_configurada: { rotulo: "Não configurada", variante: "secondary" },
  com_falha: { rotulo: "Com falha", variante: "destructive" },
  revogada: { rotulo: "Revogada", variante: "destructive" },
  expirada: { rotulo: "Expirada", variante: "destructive" },
};

/** What the user should do, per status. Never points anywhere outside this product. */
export function ajudaConexao(c: ConexaoPlataforma): string {
  switch (c.status) {
    case "ativa":
      return "Tudo certo: o WhatsApp consegue falar com a Julia.";
    case "nao_configurada":
      return "A Julia ainda não foi conectada pela plataforma. Peça ao suporte NoctusAI para conectá-la; você não precisa colar nenhum token.";
    case "com_falha":
      return c.motivo === "agents_indisponivel"
        ? "Não foi possível falar com a Julia agora. Isso costuma passar sozinho: use “Testar conexão” em alguns minutos. Se continuar, avise o suporte NoctusAI."
        : "A plataforma recusou o token desta conexão. Peça ao suporte NoctusAI para reconectar.";
    case "revogada":
      return "Esta conexão foi revogada. Peça ao suporte NoctusAI para reconectar.";
    case "expirada":
      return "Esta conexão expirou. Peça ao suporte NoctusAI para renová-la.";
  }
}

export function formatarDataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo", dateStyle: "short", timeStyle: "short" });
}

function Linha({ rotulo, valor, testid }: { rotulo: string; valor: string; testid: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd data-testid={testid}>{valor}</dd>
    </div>
  );
}

export function ConexaoPlataformaBody({ conexao, canTest }: { conexao: ConexaoPlataforma; canTest: boolean }) {
  const verificar = useVerificarConexaoPlataforma();
  const [erro, setErro] = useState<string | null>(null);
  const info = STATUS[conexao.status] ?? STATUS.nao_configurada;
  const ok = conexao.status === "ativa";

  function testar() {
    setErro(null);
    verificar.mutate(undefined, {
      onSuccess: (r) => (r.status === "ativa" ? toast.success("Conexão funcionando") : toast.error("A conexão não está funcionando")),
      onError: (e) => setErro(mensagemErroJulia(e, "Não foi possível testar a conexão agora.")),
    });
  }

  return (
    <div className="space-y-3" data-testid="conexao-plataforma" data-status={conexao.status}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={info.variante} className="gap-1" data-testid="conexao-status">
          {ok ? <CheckCircle2 className="h-3 w-3" /> : <CircleAlert className="h-3 w-3" />}
          {info.rotulo}
        </Badge>
        {/* Display only: no input, no copy affordance, no way to change it from here. */}
        <code className="select-none rounded bg-muted px-2 py-1 font-mono text-xs" data-testid="conexao-token">
          {conexao.token_mascarado ?? "Sem token"}
        </code>
      </div>

      <p
        role={ok || conexao.status === "nao_configurada" ? undefined : "alert"}
        className={`flex items-start gap-2 text-sm ${ok || conexao.status === "nao_configurada" ? "text-muted-foreground" : "text-destructive"}`}
        data-testid="conexao-ajuda"
      >
        {!ok && conexao.status !== "nao_configurada" && <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
        <span>{ajudaConexao(conexao)}</span>
      </p>

      {conexao.status !== "nao_configurada" && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
          <Linha rotulo="Conectada em" valor={formatarDataHora(conexao.conectada_em)} testid="conexao-conectada-em" />
          <Linha rotulo="Última verificação" valor={formatarDataHora(conexao.verificada_em)} testid="conexao-verificada-em" />
          <Linha rotulo="Última falha" valor={formatarDataHora(conexao.ultima_falha_em)} testid="conexao-falha-em" />
          <Linha rotulo="Expira em" valor={conexao.expires_at ? formatarDataHora(conexao.expires_at) : "Não expira"} testid="conexao-expira" />
        </dl>
      )}

      {erro && (
        <p role="alert" className="text-sm text-destructive" data-testid="conexao-erro">
          {erro}
        </p>
      )}

      {canTest ? (
        <Button variant="outline" size="sm" onClick={testar} disabled={verificar.isPending} data-testid="conexao-testar">
          {verificar.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plug className="mr-1 h-4 w-4" />}
          {verificar.isPending ? "Testando…" : "Testar conexão"}
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground">Somente owner ou admin da organização pode testar a conexão.</p>
      )}
    </div>
  );
}

/** Reads the connection itself (Configurações): skeleton -> error -> data. Never `isLoading`. */
export function ConexaoPlataformaDoAgente({ canTest }: { canTest: boolean }) {
  const q = useJuliaAgente();
  if (q.data) return <ConexaoPlataformaBody conexao={q.data.conexao_plataforma} canTest={canTest} />;
  if (q.isPending) return <div className="h-16 animate-pulse rounded-md bg-muted" data-testid="conexao-skeleton" />;
  return (
    <div role="alert" className="space-y-2 text-sm text-destructive" data-testid="conexao-leitura-erro">
      <p>Não foi possível consultar o estado da conexão.</p>
      <Button variant="outline" size="sm" onClick={() => void q.refetch()}>
        Tentar de novo
      </Button>
    </div>
  );
}
