/**
 * Configurações — `/configuracoes`, admin-only.
 *
 * Community consumes the SAME mechanism social-wiring uses for
 * operator-settable provider credentials: `createApiKeysHooks` +
 * `<ApiKeysPanel/>` (`@noctusai/lib/components`) against
 * `/api/settings/api-keys*`, mounted on the community backend as a
 * parallel slice (same router shape, keys `stripe_secret_key` /
 * `stripe_webhook_secret` / `asaas_api_key` / `asaas_webhook_token` /
 * `turnstile_secret_key` — labels/descriptions come from the API).
 *
 * `createApiKeysHooks`'s read side is intentionally ungated server-side
 * (any org member can read), so the FE admin gate below is the real
 * boundary here — same posture `ApiKeysPanel`'s own doc comment calls
 * out ("does NOT gate on role... do the same at the call site"). Full-page
 * gate (not just a subtree) since this page has nothing else on it yet;
 * `isAdmin` mirrors `Equipe.tsx`/`WhatsApp.tsx`'s exact expression.
 *
 * Nav entry ("Configurações") is visible to every authenticated member —
 * same convention as `social-wiring`'s own `/configuracoes` nav item
 * (status_pagina governs producao/desenvolvimento/desativado rollout
 * state, not per-user role; admin-only content is gated in-page, not by
 * hiding the nav item).
 */
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";
import { createApiKeysHooks, ApiKeysPanel } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { Card } from "@/components/FormControls";

const apiKeysHooks = createApiKeysHooks(api);

export default function Configuracoes() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Configurações</h1>
        </div>
        <Card data-testid="configuracoes-acesso-restrito">
          <p className="text-sm text-muted-foreground">
            Esta página é restrita a administradores da comunidade.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="configuracoes-page">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Configurações</h1>
        <p className="text-sm text-muted-foreground">
          Chaves de API usadas pelos gateways de pagamento (Stripe, Asaas) e
          pela proteção anti-spam (Turnstile) desta comunidade.
        </p>
      </div>
      <ApiKeysPanel hooks={apiKeysHooks} title="Chaves de API" />
    </div>
  );
}
