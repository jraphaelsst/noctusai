/**
 * IgOverview / IgPublicacoes — Instagram subtabs backed by the Instagram
 * Business Login insights API (provider "instagram"), via the shared
 * `InstagramProfileView` / `InstagramPostGrid`.
 *
 * Overview fallback: an org with NO Instagram-Login account but a Meta
 * (Facebook Login) connection keeps the legacy `IgVisaoGeral` — that path
 * stays reachable instead of being silently removed.
 */
import { lazy, Suspense } from "react";
import { Instagram, Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { InstagramPostGrid } from "@/components/instagram/InstagramPostGrid";
import { InstagramProfileView } from "@/components/instagram/InstagramProfileView";
import { useActiveInstagramAccount } from "@/hooks/useInstagramInsights";
import { useActiveMetaAccountId } from "@/hooks/useMeta";

const LegacyIgVisaoGeral = lazy(() => import("@/pages/meta/IgVisaoGeral"));

function Loading() {
  return (
    <div className="flex items-center justify-center py-16" data-testid="ig-accounts-loading">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

function NoInstagramAccount() {
  return (
    <Card>
      <CardContent
        className="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted-foreground"
        data-testid="ig-no-instagram-account"
      >
        <Instagram className="h-6 w-6" />
        Nenhuma conta do Instagram conectada. Conecte uma em Conexões (“Conectar Instagram”) para ver os
        insights.
      </CardContent>
    </Card>
  );
}

export function IgOverview() {
  const { accountId, isPending } = useActiveInstagramAccount();
  const metaAccountId = useActiveMetaAccountId();
  if (isPending) return <Loading />;
  if (accountId) return <InstagramProfileView accountId={accountId} showPosts={false} />;
  if (metaAccountId) {
    return (
      <Suspense fallback={<Loading />}>
        <LegacyIgVisaoGeral />
      </Suspense>
    );
  }
  return <NoInstagramAccount />;
}

export function IgPublicacoes() {
  const { accountId, isPending } = useActiveInstagramAccount();
  if (isPending) return <Loading />;
  if (!accountId) return <NoInstagramAccount />;
  return <InstagramPostGrid accountId={accountId} />;
}

export default IgOverview;
