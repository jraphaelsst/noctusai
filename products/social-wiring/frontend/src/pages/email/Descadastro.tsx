/**
 * Email Marketing · Descadastro — PUBLIC one-click unsubscribe page.
 *
 *   GET  /api/email-marketing/unsubscribe/{token}  → { email, valid }
 *   POST /api/email-marketing/unsubscribe/{token}  → { ok, message }
 *
 * Route: /descadastro/:token — mounted via `publicRoutes` (no auth, no Layout,
 * no `status_pagina` gate). The backend builds the links in the e-mails
 * (`${FRONTEND_BASE_URL}/descadastro/<token>`); the recipient is NOT logged in.
 *
 * accept-with-rationale: direct `api` calls on a public, token-authenticated,
 * single-purpose endpoint — no shared cache state with the authenticated app
 * (same Pattern D as the retired `mailing` Unsubscribe page).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { AlertCircle, CheckCircle, Loader2, MailX } from "lucide-react";

import { api } from "@/lib/api";

const BASE = "/api/email-marketing/unsubscribe";

interface TokenInfo {
  email: string;
  valid: boolean;
}

export default function Descadastro() {
  const { token } = useParams<{ token: string }>();

  const info = useQuery({
    queryKey: ["sw", "email-marketing", "unsubscribe", token ?? "_none"],
    enabled: !!token,
    retry: false,
    queryFn: () =>
      api.get<TokenInfo>(`${BASE}/${encodeURIComponent(token!)}`),
  });

  const confirm = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; message?: string }>(
        `${BASE}/${encodeURIComponent(token!)}`,
      ),
  });

  const showSkeleton = info.isPending && !info.data && !!token;
  const invalid = !token || (info.isError && !info.data);

  return (
    <div
      className="min-h-screen bg-background flex items-center justify-center px-4"
      data-testid="descadastro-page"
    >
      <div className="w-full max-w-md space-y-6 text-center">
        {showSkeleton && (
          <div className="space-y-3" data-testid="descadastro-loading">
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">
              Verificando link de descadastro…
            </p>
          </div>
        )}

        {!showSkeleton && invalid && (
          <div className="space-y-4" data-testid="descadastro-invalid">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h1 className="text-2xl font-bold text-foreground">
              Link inválido ou expirado
            </h1>
            <p className="text-sm text-muted-foreground">
              Não foi possível validar este link de descadastro. Use o link mais
              recente recebido por e-mail ou entre em contato conosco.
            </p>
          </div>
        )}

        {!showSkeleton && !invalid && confirm.isSuccess && (
          <div className="space-y-4" data-testid="descadastro-success">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <h1 className="text-2xl font-bold text-foreground">
              Descadastro confirmado
            </h1>
            <p className="text-sm text-muted-foreground">
              {info.data?.email ? `${info.data.email} foi removido` : "Você foi removido"}{" "}
              da nossa lista de e-mails de marketing. Se mudar de ideia, entre em
              contato conosco.
            </p>
          </div>
        )}

        {!showSkeleton && !invalid && !confirm.isSuccess && (
          <>
            <div className="space-y-2">
              <MailX className="mx-auto h-12 w-12 text-muted-foreground" />
              <h1 className="text-2xl font-bold text-foreground">Descadastro</h1>
              <p
                className="text-sm text-muted-foreground"
                data-testid="descadastro-email"
              >
                {info.data?.email}
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6 space-y-4">
              <p className="text-sm text-foreground">
                Ao confirmar, você deixará de receber nossos e-mails de
                marketing. E-mails transacionais importantes ainda poderão ser
                enviados.
              </p>

              {confirm.isError && (
                <p
                  role="alert"
                  className="text-sm text-destructive"
                  data-testid="descadastro-error"
                >
                  Não foi possível concluir o descadastro. Tente novamente.
                </p>
              )}

              <div className="space-y-3">
                <button
                  type="button"
                  onClick={() => confirm.mutate()}
                  disabled={confirm.isPending}
                  data-testid="descadastro-confirm"
                  className="inline-flex w-full items-center justify-center rounded-md bg-destructive px-6 py-2.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-60"
                >
                  {confirm.isPending ? "Processando…" : "Confirmar descadastro"}
                </button>
                <a
                  href="/"
                  className="inline-flex w-full items-center justify-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
                >
                  Cancelar — quero continuar recebendo
                </a>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Se você não solicitou este descadastro, pode ignorar esta página.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
