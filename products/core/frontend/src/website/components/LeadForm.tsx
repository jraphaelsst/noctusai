import { useState, type FormEvent } from "react";
import { useLocale, useT } from "../lib/i18n";
import { submitLead, type LeadPayload } from "../lib/api";
import { TurnstileWidget } from "./TurnstileWidget";
import { CONSENT_TEXT_VERSION } from "../lib/consent";
import { useTrackEvent } from "../hooks/useTrackEvent";

export type LeadFormVariant = "waitlist" | "brief" | "contact";

const VARIANT_FIELDS: Record<LeadFormVariant, Array<"name" | "email" | "phone" | "company" | "profile" | "projectType" | "message">> = {
  waitlist: ["name", "email", "phone", "profile"],
  brief: ["name", "phone", "company", "projectType", "message"],
  contact: ["name", "email", "phone", "message"],
};

const PROJECT_TYPES = ["diagnostico", "prototipo", "producao", "outro"] as const;
const PROFILES = ["smb", "enterprise", "developer", "solo"] as const;

function turnstileSiteKey(): string {
  return (import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined) ?? "";
}

/**
 * Shared lead-capture form (waitlist / brief / contact — contract §3
 * `POST /api/website/leads`). One component, three variants: the three
 * pages differ only in WHICH fields show (07 §Subpage templates), not in
 * submit/consent/Turnstile/error handling, so this stays a single
 * implementation instead of three near-identical copies (DRY).
 */
export function LeadForm({
  variant,
  productInterest,
}: {
  variant: LeadFormVariant;
  productInterest?: string[];
}) {
  const t = useT();
  const locale = useLocale();
  const track = useTrackEvent();
  const fields = VARIANT_FIELDS[variant];

  const [values, setValues] = useState({ name: "", email: "", phone: "", company: "", profile: "", projectType: "", message: "" });
  const [consent, setConsent] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "submitting" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [whatsappUrl, setWhatsappUrl] = useState<string | null>(null);

  const siteKey = turnstileSiteKey();

  function setField<K extends keyof typeof values>(key: K, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!consent) {
      setErrorMessage(t("form.required"));
      return;
    }
    setStatus("submitting");
    setErrorMessage(null);
    try {
      const payload: LeadPayload = {
        source: variant,
        name: values.name,
        email: values.email || undefined,
        phone: values.phone || undefined,
        company: values.company || undefined,
        profile: (values.profile as LeadPayload["profile"]) || undefined,
        product_interest: productInterest,
        message: values.message || undefined,
        locale,
        consent_marketing: consent,
        consent_text_version: CONSENT_TEXT_VERSION,
        landing_path: typeof window !== "undefined" ? window.location.pathname : undefined,
        referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
        turnstile_token: turnstileToken ?? undefined,
      };
      const res = await submitLead(payload);
      setStatus("success");
      setWhatsappUrl(res.whatsapp_url);
      track(`${variant === "waitlist" ? "waitlist_submit" : variant === "brief" ? "brief_submit" : "waitlist_submit"}`);
    } catch (err) {
      setStatus("error");
      setErrorMessage((err as Error).message === "turnstile_failed" ? t("form.error") : t("form.error"));
    }
  }

  if (status === "success") {
    return (
      <div>
        <p className="nx-form-success">{t("form.success")}</p>
        {whatsappUrl && (
          <a href={whatsappUrl} target="_blank" rel="noopener noreferrer" className="nx-btn nx-btn-primary">
            {t("cta.continueWhatsapp")}
          </a>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {fields.includes("name") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-name`}>{t("form.name")}</label>
          <input id={`${variant}-name`} required value={values.name} onChange={(e) => setField("name", e.target.value)} autoComplete="name" />
        </div>
      )}
      {fields.includes("email") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-email`}>{t("form.email")}</label>
          <input id={`${variant}-email`} type="email" value={values.email} onChange={(e) => setField("email", e.target.value)} autoComplete="email" />
        </div>
      )}
      {fields.includes("phone") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-phone`}>{t("form.phone")}</label>
          <input
            id={`${variant}-phone`}
            type="tel"
            placeholder="+55"
            value={values.phone}
            onChange={(e) => setField("phone", e.target.value)}
            autoComplete="tel"
          />
        </div>
      )}
      {fields.includes("company") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-company`}>{t("form.company")}</label>
          <input id={`${variant}-company`} value={values.company} onChange={(e) => setField("company", e.target.value)} autoComplete="organization" />
        </div>
      )}
      {fields.includes("profile") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-profile`}>{t("form.profile")}</label>
          <select id={`${variant}-profile`} value={values.profile} onChange={(e) => setField("profile", e.target.value)}>
            <option value="">—</option>
            {PROFILES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}
      {fields.includes("projectType") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-project-type`}>{t("form.projectType")}</label>
          <select id={`${variant}-project-type`} value={values.projectType} onChange={(e) => setField("projectType", e.target.value)}>
            <option value="">—</option>
            {PROJECT_TYPES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}
      {fields.includes("message") && (
        <div className="nx-field">
          <label htmlFor={`${variant}-message`}>{t("form.message")}</label>
          <textarea id={`${variant}-message`} rows={4} value={values.message} onChange={(e) => setField("message", e.target.value)} />
        </div>
      )}

      <div className="nx-field">
        <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontWeight: 400 }}>
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
          <span>{t("form.consent")}</span>
        </label>
      </div>

      {siteKey && <TurnstileWidget siteKey={siteKey} onVerify={setTurnstileToken} onExpire={() => setTurnstileToken(null)} />}

      {errorMessage && <p className="nx-form-error">{errorMessage}</p>}

      <button type="submit" className="nx-btn nx-btn-primary" disabled={status === "submitting"}>
        {status === "submitting" ? t("form.submitting") : t("form.submit")}
      </button>
    </form>
  );
}
