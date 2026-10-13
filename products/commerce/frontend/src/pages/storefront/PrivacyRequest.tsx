/**
 * `/privacidade` — a buyer asks for access / correction / deletion /
 * portability / consent withdrawal (CONTRACT §4 `POST /api/storefront/privacy-requests`,
 * always 202 — no enumeration). The e-mailed link lands on
 * `/privacidade/verificar`.
 *
 * NOC-REMEDIATE[commerce-privacy-request-form-organ]: the organ ships the hook
 * (`usePrivacyRequest`) but no component; lift this form into the organ as
 * `PrivacyRequestForm` (CONTRACT-DELTAS D2).
 */
import * as React from "react";
import { PRIVACY_REQUEST_KINDS, type PrivacyRequestKind } from "@noctusai/lib";
import { Button, Field, FormError, Input, Select, Textarea } from "@noctusai/lib/design-system";

import { StorefrontFrame } from "@/components/StorefrontFrame";
import { storefrontCommerce } from "@/lib/commerce";
import { describeError, usePageT } from "@/lib/i18n";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function RequestForm() {
  const { t } = usePageT();
  const send = storefrontCommerce.usePrivacyRequest();
  const [email, setEmail] = React.useState("");
  const [kind, setKind] = React.useState<PrivacyRequestKind>("access");
  const [details, setDetails] = React.useState("");
  const [emailErr, setEmailErr] = React.useState<string | null>(null);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!EMAIL_RE.test(email.trim())) {
      setEmailErr(t("common.invalid_email"));
      return;
    }
    setEmailErr(null);
    try {
      await send.mutateAsync({ email: email.trim().toLowerCase(), kind, ...(details.trim() ? { details: details.trim() } : {}) });
    } catch {
      // Rendered below from `send.error` — not swallowed.
    }
  }

  if (send.isSuccess) {
    return (
      <p role="status" className="mx-auto max-w-md rounded-md border p-3 text-sm">
        {t("store.privacy_sent")}
      </p>
    );
  }
  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-3" noValidate>
      <h1 className="text-lg font-semibold">{t("store.privacy_title")}</h1>
      <p className="text-sm text-muted-foreground">{t("store.privacy_intro")}</p>
      <Field label={t("checkout.email")} required error={emailErr}>
        <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label={t("store.privacy_kind")} required>
        <Select value={kind} onChange={(e) => setKind(e.target.value as PrivacyRequestKind)}>
          {PRIVACY_REQUEST_KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`privacy_kind.${k}`)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("store.privacy_details")}>
        <Textarea rows={3} value={details} onChange={(e) => setDetails(e.target.value)} maxLength={2000} />
      </Field>
      <FormError message={send.isError ? describeError(send.error, t) : null} />
      <Button type="submit" disabled={send.isPending}>
        {send.isPending ? t("common.loading") : t("store.privacy_send")}
      </Button>
    </form>
  );
}

export default function PrivacyRequest() {
  return <StorefrontFrame>{() => <RequestForm />}</StorefrontFrame>;
}
