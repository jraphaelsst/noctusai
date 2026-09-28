/**
 * AprovacaoPublica — the white-label approval portal (Módulo 4).
 *
 * Route: `/aprovar/:token` via the seed's `publicRoutes` seam — NO auth. The
 * agency's client has no noc account; the token is the credential.
 *
 * White-label means the page carries the CLIENT's name, not IgIg's branding,
 * and shows nothing about the agency's internals. The backend already enforces
 * that with a narrow projection; this page must not reintroduce it.
 *
 * States:
 *   loading         — skeleton
 *   rate-limited     — 429: distinct from "invalid" (achado 8) — try again shortly
 *   unreachable      — network failure / 5xx: distinct from "invalid" too
 *   bloqueado        — 423 `portal_bloqueado`: a valid link, an agency policy
 *                      (`IGIG_PORTAL_BLOQUEIO_DIAS`) currently refuses it —
 *                      distinct from "the link itself is bad"
 *   invalid          — unknown / expired / already-decided-and-later-pulled
 *                      (indistinguishable BY DESIGN, so one message covers them)
 *   decided          — the client already answered
 *   actionable       — show the content + [Aprovar Conteúdo] / [Solicitar Ajuste]
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "@noctusai/lib";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { AlertCircle, CheckCircle2, Lock, MessageSquare, WifiOff } from "lucide-react";

import { useAprovacaoPublica, useDecidirAprovacao } from "@/hooks/useEsteira";

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl items-center justify-center p-6">
      <div className="w-full rounded-lg border border-border bg-card p-6">{children}</div>
    </main>
  );
}

/**
 * Classify a load failure — achado 8. Before this, EVERY failure (rate
 * limit, a dropped connection, a 5xx) rendered the SAME "Link inválido ou
 * expirado", which told a client with a perfectly good link to go ask their
 * agency for a new one over a passing network hiccup.
 */
function estadoDoErro(erro: unknown): "rate-limited" | "unreachable" | "bloqueado" | "invalid" {
  if (erro instanceof ApiError) {
    if (erro.status === 429) return "rate-limited";
    if (erro.status === null || erro.status >= 500) return "unreachable";
    if (erro.status === 423) return "bloqueado";
  }
  return "invalid";
}

export default function AprovacaoPublica() {
  const { token } = useParams<{ token: string }>();
  const { aprovacao, loading, error } = useAprovacaoPublica(token);
  const decidir = useDecidirAprovacao(token);
  const [observacao, setObservacao] = useState("");

  if (loading) {
    return (
      <Moldura>
        <Skeleton className="mb-4 h-8 w-2/3" />
        <Skeleton className="mb-2 h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </Moldura>
    );
  }

  if (error || !aprovacao) {
    const estado = estadoDoErro(error);
    if (estado === "rate-limited") {
      return (
        <Moldura>
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div>
              <h1 className="font-semibold text-foreground">Muitas tentativas</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Aguarde um minuto e tente novamente.
              </p>
            </div>
          </div>
        </Moldura>
      );
    }
    if (estado === "unreachable") {
      return (
        <Moldura>
          <div className="flex items-start gap-3">
            <WifiOff className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div>
              <h1 className="font-semibold text-foreground">Não foi possível carregar</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Verifique sua conexão e tente novamente.
              </p>
            </div>
          </div>
        </Moldura>
      );
    }
    if (estado === "bloqueado") {
      return (
        <Moldura>
          <div className="flex items-start gap-3">
            <Lock className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div>
              <h1 className="font-semibold text-foreground">Portal temporariamente indisponível</h1>
              <p className="mt-1 text-sm text-muted-foreground">Contate a agência.</p>
            </div>
          </div>
        </Moldura>
      );
    }
    // Unknown, expired and already-spent all arrive here as the same 404 —
    // the backend deliberately does not distinguish them, so neither does
    // this copy.
    return (
      <Moldura>
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
          <div>
            <h1 className="font-semibold text-foreground">Link inválido ou expirado</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Peça um novo link de aprovação à sua agência.
            </p>
          </div>
        </div>
      </Moldura>
    );
  }

  if (aprovacao.ja_decidida || decidir.isSuccess) {
    // "Sua agência já foi notificada" is a promise the backend cannot always
    // keep (achado 8) — `notificado` is `undefined` when this page loads
    // straight into an already-decided link (no `decidir` response exists
    // yet), so this only ever claims success when the CURRENT session's own
    // decision is known to have landed.
    const notificado = decidir.data?.notificado === true;
    return (
      <Moldura>
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-foreground" />
          <div>
            <h1 className="font-semibold text-foreground">Resposta registrada</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {notificado ? "Obrigado! Sua agência já foi notificada." : "Obrigado pela resposta."}
            </p>
          </div>
        </div>
      </Moldura>
    );
  }

  return (
    <Moldura>
      {aprovacao.cliente_nome && (
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {aprovacao.cliente_nome}
        </p>
      )}
      <h1 className="mt-1 text-xl font-semibold text-foreground">{aprovacao.titulo}</h1>
      {aprovacao.formato && (
        <p className="mt-1 text-sm text-muted-foreground">{aprovacao.formato}</p>
      )}

      {/* The spec's "peça em paralelo com o texto da legenda". When the pauta
          has no asset the section is omitted entirely rather than rendering an
          empty frame — copy-only is still a reviewable piece. */}
      {aprovacao.pecas.length > 0 && (
        <section className="mt-4 space-y-2">
          {aprovacao.pecas.map((peca, i) =>
            !peca.url ? (
              <p key={i} className="text-sm text-muted-foreground">
                A peça não pôde ser carregada. Revise pela legenda ou peça um novo link.
              </p>
            ) : peca.mime_type?.startsWith("video/") ? (
              <video
                key={i}
                src={peca.url}
                controls
                className="w-full rounded-md border border-border"
              />
            ) : (
              <img
                key={i}
                src={peca.url}
                alt={`Peça ${i + 1} — ${aprovacao.titulo}`}
                className="w-full rounded-md border border-border"
              />
            ),
          )}
        </section>
      )}

      {aprovacao.copy_texto && (
        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Legenda
          </h2>
          <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">
            {aprovacao.copy_texto}
          </p>
        </section>
      )}

      {aprovacao.direcao_video && (
        <section className="mt-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Direção de vídeo
          </h2>
          <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">
            {aprovacao.direcao_video}
          </p>
        </section>
      )}

      {/* The agency may have pulled the piece back out of approval after the
          link went out — the server then refuses a decision (409
          `fora_de_aprovacao`). Show the content read-only instead of offering
          buttons that can only fail. */}
      {!aprovacao.aguardando_aprovacao ? (
        <p className="mt-6 rounded-md border border-border bg-muted p-3 text-sm text-muted-foreground">
          Este conteúdo não está mais aguardando a sua aprovação. Se precisar,
          fale com a sua agência.
        </p>
      ) : (
      <>
      <section className="mt-6">
        <label htmlFor="observacao" className="text-xs text-muted-foreground">
          Observações (opcional para aprovar, recomendado ao pedir ajuste)
        </label>
        <textarea
          id="observacao"
          value={observacao}
          onChange={(e) => setObservacao(e.target.value)}
          rows={3}
          maxLength={2000}
          className="mt-1 w-full rounded-md border border-border bg-background p-2 text-sm text-foreground"
          placeholder="O que você gostaria de ajustar?"
        />
      </section>

      {decidir.isError && (
        <p className="mt-3 text-sm text-destructive">
          Não foi possível registrar sua resposta. Tente novamente.
        </p>
      )}

      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          disabled={decidir.isPending}
          onClick={() => decidir.mutate({ decisao: "aprovado", observacao })}
        >
          <CheckCircle2 className="mr-2 h-4 w-4" />
          Aprovar conteúdo
        </Button>
        <Button
          variant="outline"
          disabled={decidir.isPending}
          onClick={() => decidir.mutate({ decisao: "ajuste", observacao })}
        >
          <MessageSquare className="mr-2 h-4 w-4" />
          Solicitar ajuste
        </Button>
      </div>
      </>
      )}
    </Moldura>
  );
}
