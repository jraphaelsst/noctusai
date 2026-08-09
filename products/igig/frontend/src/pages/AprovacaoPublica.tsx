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
 * Four states, all reachable:
 *   loading      — skeleton
 *   invalid      — unknown / expired / already-decided (indistinguishable by
 *                  design, so one message covers all three)
 *   decided      — the client already answered
 *   actionable   — show the content + [Aprovar Conteúdo] / [Solicitar Ajuste]
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Button, Skeleton } from "@noctusai/lib/design-system";
import { AlertCircle, CheckCircle2, MessageSquare } from "lucide-react";

import { useAprovacaoPublica, useDecidirAprovacao } from "@/hooks/useEsteira";

function Moldura({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl items-center justify-center p-6">
      <div className="w-full rounded-lg border border-border bg-card p-6">{children}</div>
    </main>
  );
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

  // Unknown, expired and already-spent all arrive here as the same 404 — the
  // backend deliberately does not distinguish them, so neither does this copy.
  if (error || !aprovacao) {
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
    return (
      <Moldura>
        <div className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-foreground" />
          <div>
            <h1 className="font-semibold text-foreground">Resposta registrada</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Obrigado! Sua agência já foi notificada.
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

      {/* The spec asks for the peça and the legenda side by side. The visual
          asset is not yet modelled (Módulo 4 follow-up), so the copy carries
          the review on its own rather than showing an empty frame. */}
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
    </Moldura>
  );
}
