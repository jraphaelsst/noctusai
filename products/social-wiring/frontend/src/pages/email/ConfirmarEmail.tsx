/**
 * Email Marketing · Confirmar e-mail — PUBLIC double opt-in confirmation page.
 *
 *   GET  /api/email-marketing/confirm/{token}  → { email, valid }
 *   POST /api/email-marketing/confirm/{token}  → { ok, already?, message? }
 *
 * Route: /confirmar-email/:token — mounted via `publicRoutes` (no auth, no
 * Layout, no `status_pagina` gate). The backend sends the link in the
 * confirmation e-mail (`${FRONTEND_BASE_URL}/confirmar-email/<token>`, valid
 * 7 days); the recipient is NOT logged in.
 *
 * Data hooks live in `@/hooks/useEmailMarketing` (useEmConfirmEmailInfo /
 * useEmConfirmEmail) — never inline in a page.
 */
import { useParams } from "react-router-dom";
import { AlertCircle, CheckCircle, Loader2, MailCheck } from "lucide-react";

import { useEmConfirmEmail, useEmConfirmEmailInfo } from "@/hooks/useEmailMarketing";

export default function ConfirmarEmail() {
  const { token } = useParams<{ token: string }>();

  const info = useEmConfirmEmailInfo(token);
  const confirm = useEmConfirmEmail(token);

  const showSkeleton = info.isPending && !info.data && !!token;
  const invalid = !token || (info.isError && !info.data);

  return (
    <div
      className="min-h-screen bg-background flex items-center justify-center px-4"
      data-testid="confirmar-email-page"
    >
      <div className="w-full max-w-md space-y-6 text-center">
        {showSkeleton && (
          <div className="space-y-3" data-testid="confirmar-email-loading">
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Verificando link de confirmação…</p>
          </div>
        )}

        {!showSkeleton && invalid && (
          <div className="space-y-4" data-testid="confirmar-email-invalid">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h1 className="text-2xl font-bold text-foreground">Link inválido ou expirado</h1>
            <p className="text-sm text-muted-foreground">
              Não foi possível validar este link de confirmação. Ele vale por 7 dias — use
              o link mais recente recebido por e-mail ou peça um novo envio.
            </p>
          </div>
        )}

        {!showSkeleton && !invalid && confirm.isSuccess && (
          <div className="space-y-4" data-testid="confirmar-email-success">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <h1 className="text-2xl font-bold text-foreground">
              {confirm.data?.already ? "E-mail já confirmado" : "E-mail confirmado"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {info.data?.email ? `${info.data.email} está confirmado` : "Seu e-mail está confirmado"}{" "}
              para receber nossos e-mails. Você pode se descadastrar a qualquer momento pelo
              link no rodapé das mensagens.
            </p>
          </div>
        )}

        {!showSkeleton && !invalid && !confirm.isSuccess && (
          <>
            <div className="space-y-2">
              <MailCheck className="mx-auto h-12 w-12 text-primary" />
              <h1 className="text-2xl font-bold text-foreground">Confirme seu e-mail</h1>
              <p className="text-sm text-muted-foreground" data-testid="confirmar-email-address">
                {info.data?.email}
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6 space-y-4">
              <p className="text-sm text-foreground">
                Ao confirmar, você passa a receber nossos e-mails neste endereço.
              </p>

              {confirm.isError && (
                <p role="alert" className="text-sm text-destructive" data-testid="confirmar-email-error">
                  Não foi possível confirmar seu e-mail. Tente novamente.
                </p>
              )}

              <button
                type="button"
                onClick={() => confirm.mutate()}
                disabled={confirm.isPending}
                data-testid="confirmar-email-confirm"
                className="inline-flex w-full items-center justify-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
              >
                {confirm.isPending ? "Confirmando…" : "Confirmar e-mail"}
              </button>
            </div>

            <p className="text-xs text-muted-foreground">
              Se você não fez este cadastro, ignore esta página — nada será enviado.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
