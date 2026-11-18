/**
 * "Conexão com o Social Wiring" — platform-admin status card of the onboarding area (owner 2026-11-18).
 *
 * The onboarding interviewer writes a client's settings into social-wiring through a service credential that the
 * server creates and rotates BY ITSELF: nobody makes, copies or pastes it, and nothing on this card can set or show it.
 * What the owner sees is whether the channel works: the credential state (provisionado / ausente / expirado / erro),
 * its scope and expiry, the last successful call, the last error (when + why, in pt-BR) and a "Testar conexão" button
 * that provisions the credential if it is due and makes a harmless read-only call to social-wiring.
 *
 * Loading is a skeleton, a failed read is an error with retry (never a blank card), a failed test is shown with its
 * reason (never swallowed), and "ausente" says what will happen instead of asking for anything.
 */
import { useState } from "react";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CheckCircle2, Link2, Loader2, XCircle } from "lucide-react";
import { Badge, Button, Card } from "@noctusai/lib/design-system";
import { StudioError, StudioLoading } from "@/components/studio/StudioStates";
import { useSwCanal, useTestarSwCanal } from "@/hooks/studio/useSwCanal";
import { errorMessage } from "@/lib/errors";
import type { SwCanalEstado, SwCanalEvento, SwCanalTeste } from "@/api/studio/types-onboarding";

const ESTADO: Record<SwCanalEstado, { rotulo: string; variant: "default" | "destructive" | "muted" | "outline"; texto: string }> = {
  provisionado: { rotulo: "Provisionado", variant: "default", texto: "A credencial existe e está dentro do prazo." },
  ausente: {
    rotulo: "Ausente",
    variant: "muted",
    texto: "Ainda não foi criada. Ela é criada sozinha no primeiro uso, ou agora, ao testar a conexão.",
  },
  expirado: { rotulo: "Expirado", variant: "destructive", texto: "O prazo acabou. Ela é renovada sozinha no próximo uso, ou ao testar." },
  erro: { rotulo: "Erro", variant: "destructive", texto: "Há um problema com a credencial; veja o motivo abaixo." },
};

function quando(valor: string | null | undefined): string {
  return valor ? format(new Date(valor), "dd/MM/yyyy HH:mm", { locale: ptBR }) : "—";
}

function Evento({ rotulo, evento, testId }: { rotulo: string; evento: SwCanalEvento | null; testId: string }) {
  return (
    <div data-testid={testId}>
      <dt className="text-xs text-muted-foreground">{rotulo}</dt>
      <dd className="text-sm">
        {evento ? (
          <>
            {quando(evento.em)}
            {evento.motivo ? <span className="block text-muted-foreground">{evento.motivo}</span> : null}
          </>
        ) : (
          "Nenhum até agora"
        )}
      </dd>
    </div>
  );
}

export function SwCanalCard() {
  const canal = useSwCanal();
  const testar = useTestarSwCanal();
  const [resultado, setResultado] = useState<SwCanalTeste | null>(null);
  const [falhaDoTeste, setFalhaDoTeste] = useState<unknown>(null);

  async function aoTestar() {
    setResultado(null);
    setFalhaDoTeste(null);
    try {
      setResultado(await testar.mutateAsync());
    } catch (e) {
      setFalhaDoTeste(e);
    }
  }

  const s = canal.data;
  return (
    <Card className="space-y-4 p-4" data-testid="sw-canal-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold">Conexão com o Social Wiring</h3>
          {s && (
            <Badge variant={ESTADO[s.estado].variant} data-testid="sw-canal-estado">
              {ESTADO[s.estado].rotulo}
            </Badge>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={aoTestar} disabled={testar.isPending} data-testid="sw-canal-testar">
          {testar.isPending ? (
            <>
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" aria-hidden />
              Testando…
            </>
          ) : (
            "Testar conexão"
          )}
        </Button>
      </div>

      {canal.showSkeleton && <StudioLoading rows={2} testId="sw-canal-skeleton" />}
      {canal.isError && !s && (
        <StudioError error={canal.error} onRetry={canal.refetch} mensagem="Não foi possível ler o estado da conexão." />
      )}

      {s && (
        <>
          <p className="text-sm text-muted-foreground" data-testid="sw-canal-descricao">
            {ESTADO[s.estado].texto}
          </p>
          {s.estado === "erro" && s.motivo && (
            <p className="text-sm text-destructive" role="alert" data-testid="sw-canal-motivo">
              {s.motivo}
            </p>
          )}
          <dl className="grid gap-3 sm:grid-cols-2">
            <div data-testid="sw-canal-escopo">
              <dt className="text-xs text-muted-foreground">Permissão (escopo)</dt>
              <dd className="font-mono text-sm">{s.escopo}</dd>
            </div>
            <div data-testid="sw-canal-expira">
              <dt className="text-xs text-muted-foreground">Validade</dt>
              <dd className="text-sm">
                {s.expira_em ? `${quando(s.expira_em)}${s.dias_restantes != null ? ` (${s.dias_restantes} dia(s))` : ""}` : "—"}
              </dd>
            </div>
            <Evento rotulo="Última chamada com sucesso" evento={s.ultima_chamada_ok} testId="sw-canal-ultima-ok" />
            <Evento rotulo="Último erro" evento={s.ultimo_erro} testId="sw-canal-ultimo-erro" />
          </dl>
        </>
      )}

      {resultado && (
        <p
          className={`flex items-start gap-2 text-sm ${resultado.ok ? "text-foreground" : "text-destructive"}`}
          role={resultado.ok ? "status" : "alert"}
          data-testid="sw-canal-resultado"
        >
          {resultado.ok ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
          ) : (
            <XCircle className="mt-0.5 h-4 w-4" aria-hidden />
          )}
          <span>{resultado.ok ? "Conexão funcionando: o Social Wiring aceitou a credencial." : `Falhou: ${resultado.motivo}`}</span>
        </p>
      )}
      {falhaDoTeste != null && (
        <p className="text-sm text-destructive" role="alert" data-testid="sw-canal-teste-erro">
          Não foi possível testar: {errorMessage(falhaDoTeste)}
        </p>
      )}
    </Card>
  );
}

export default SwCanalCard;
