/**
 * Conexões WhatsApp — `/whatsapp/conexoes`, admin-only.
 *
 * Community consumes the SAME mechanism social-wiring uses for WAHA
 * connection-line management: `createWhatsAppConnectionsHooks` +
 * `<WhatsAppConnectionsPage/>` (`@noctusai/lib/components`) against
 * `/api/whatsapp/connections*`, mounted on the community backend as a
 * parallel slice.
 *
 * 🔴 User decision (2026-09-17): WhatsApp will NOT be connected through
 * this page now — it ships the REAL page (real list/create/detail wired
 * to the real endpoints), with an honest `banner` + `emptyState` saying
 * pairing is future work, rather than a stub or a hidden route. This is
 * distinct from the existing `/whatsapp` group-sync session (contract
 * community-m3-contract.md §4, `useSessaoWhatsApp`) — that session
 * already works today; THIS page is the new, separate, not-yet-paired
 * multi-line connection admin surface. Linked from `/whatsapp`'s own
 * session banner, not added to the main nav (an admin-only detail
 * surface, same seam as `/imoveis/:codigo` next to `imoveis` in
 * social-wiring — reachable, no `status_pagina` row needed since it's
 * not in `NAV_GROUPS`).
 *
 * Full-page admin gate mirrors `Configuracoes.tsx`/`Equipe.tsx`/
 * `WhatsApp.tsx`'s exact `isAdmin` expression.
 */
import { useAuthStore } from "@noctusai/seed/infra";
import { resolveSSOContext } from "@noctusai/lib";
import { createWhatsAppConnectionsHooks, WhatsAppConnectionsPage } from "@noctusai/lib/components";
import { api } from "@/lib/api";
import { Card } from "@/components/FormControls";

const waHooks = createWhatsAppConnectionsHooks(api);

const FUTURE_WORK_NOTICE =
  "Integração futura — o WhatsApp ainda não está conectado a este produto. A conexão será feita numa próxima etapa.";

function FutureWorkBanner() {
  return (
    <div
      className="mb-4 rounded-lg border border-amber-400/40 bg-amber-400/10 p-4 text-sm text-foreground"
      data-testid="wa-conexoes-future-work-banner"
    >
      {FUTURE_WORK_NOTICE}
    </div>
  );
}

export default function Conexoes() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Conexões WhatsApp</h1>
        </div>
        <Card data-testid="conexoes-acesso-restrito">
          <p className="text-sm text-muted-foreground">
            Esta página é restrita a administradores da comunidade.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="conexoes-page">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Conexões WhatsApp</h1>
        <p className="text-sm text-muted-foreground">
          Linhas de conexão WhatsApp (WAHA) desta comunidade.
        </p>
      </div>
      <WhatsAppConnectionsPage
        hooks={waHooks}
        banner={<FutureWorkBanner />}
        emptyState={
          <p className="text-sm text-muted-foreground" data-testid="wa-conexoes-empty-state">
            {FUTURE_WORK_NOTICE}
          </p>
        }
      />
    </div>
  );
}
