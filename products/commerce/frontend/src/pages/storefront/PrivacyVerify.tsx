/**
 * `/privacidade/verificar?token=` — confirms the buyer's privacy request from
 * the e-mailed link (CONTRACT-DELTAS A1). States: missing token, confirming,
 * confirmed (with the request kind), invalid / expired link, transport error.
 */
import { Link, useSearchParams } from "react-router-dom";
import { Button, FormError, Skeleton } from "@noctusai/lib/design-system";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { usePrivacyVerify } from "@/hooks/usePrivacyVerify";
import { describeError, usePageT } from "@/lib/i18n";

function VerifyBody({ token }: { token: string | null }) {
  const { t } = usePageT();
  const verify = usePrivacyVerify(token);

  if (!token) return <FormError message={t("store.privacy_no_token")} />;
  if (verify.showSkeleton) {
    return (
      <div className="space-y-2" data-testid="privacy-verify-loading">
        <p role="status" className="text-sm">
          {t("store.privacy_verifying")}
        </p>
        <Skeleton height={24} width="60%" announce={false} />
      </div>
    );
  }
  if (verify.isError || !verify.data) {
    return (
      <div className="space-y-3">
        <FormError message={describeError(verify.error, t)} />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => verify.refetch()}>
            {t("common.retry")}
          </Button>
          <Link to="/privacidade" className="inline-flex items-center text-sm underline">
            {t("store.privacy_title")}
          </Link>
        </div>
      </div>
    );
  }
  return (
    <p role="status" className="rounded-md border border-green-500/40 bg-green-500/10 p-3 text-sm" data-testid="privacy-verified">
      {t("store.privacy_verified", { kind: t(`privacy_kind.${verify.data.kind}`) })}
    </p>
  );
}

function VerifyPage({ token }: { token: string | null }) {
  const { t } = usePageT();
  return (
    <div className="mx-auto max-w-md space-y-3">
      <h1 className="text-lg font-semibold">{t("store.privacy_verify_title")}</h1>
      <VerifyBody token={token} />
    </div>
  );
}

export default function PrivacyVerify() {
  const [params] = useSearchParams();
  const token = params.get("token");
  return <StorefrontFrame>{() => <VerifyPage token={token} />}</StorefrontFrame>;
}
