import { useCallback } from "react";
import { LeadCaptureForm, type LeadFormValues, type LeadInterest } from "@noctusai/lib/marketing";
import { useLocale } from "../lib/i18n";
import { useWebsiteSettings } from "../lib/settings";
import { submitLead, type LeadPayload } from "../lib/api";
import { whatsappUrl } from "../lib/whatsapp";
import { CONSENT_TEXT_VERSION } from "../lib/consent";
import { EXTERNAL } from "../lib/routes";
import { useTrackEvent } from "../hooks/useTrackEvent";

/** Seed `LeadCaptureForm` values -> the `POST /api/website/leads` body (contract §3). */
export function toLeadPayload(
  values: LeadFormValues,
  source: LeadPayload["source"],
  locale: LeadPayload["locale"],
): LeadPayload {
  const projectType: Record<string, string> = {
    diagnostico: "Quero um diagnóstico",
    prototipo: "Quero ver um protótipo",
    producao: "Já sei o que construir",
    outro: "Outro",
  };
  const parts = [values.tipo ? `Fase do projeto: ${projectType[values.tipo] ?? values.tipo}` : null, values.mensagem].filter(Boolean);
  return {
    source,
    name: values.nome,
    phone: values.whatsapp,
    email: values.email,
    company: values.empresa,
    product_interest: values.product_interest,
    message: parts.length > 0 ? parts.join("\n\n") : undefined,
    locale,
    consent_marketing: values.consentimento,
    consent_text_version: CONSENT_TEXT_VERSION,
    landing_path: typeof window !== "undefined" ? window.location.pathname : undefined,
    referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
    turnstile_token: values.turnstileToken,
  };
}

export interface SiteLeadFormProps {
  /** Lead `source` stored in the CRM. A set `interest` makes it a waitlist lead. */
  source: "brief" | "contact" | "waitlist";
  interest?: LeadInterest | null;
  onInterestClear?: () => void;
  id?: string;
  eyebrow?: string;
  title: string;
  heading: string;
  description?: string;
}

/**
 * The site's lead form = the seed `LeadCaptureForm` organ + this adapter (endpoint, consent
 * version, analytics). The organ owns fields / validation / states; the site owns the wire.
 */
export function SiteLeadForm({ source, interest = null, onInterestClear, ...copy }: SiteLeadFormProps) {
  const locale = useLocale();
  const settings = useWebsiteSettings();
  const track = useTrackEvent();
  const wa = whatsappUrl(settings, locale);

  const onSubmit = useCallback(
    async (values: LeadFormValues) => {
      const waitlist = !!interest && !!values.product_interest;
      await submitLead(toLeadPayload(values, waitlist ? "waitlist" : source, locale));
      track(waitlist || source === "waitlist" ? "waitlist_submit" : "brief_submit");
    },
    [interest, source, locale, track],
  );

  return (
    <LeadCaptureForm
      variant={interest ? "waitlist" : "brief"}
      interest={interest}
      onInterestClear={onInterestClear}
      onSubmit={onSubmit}
      privacyHref={EXTERNAL.privacyPolicy}
      successAction={wa ? { label: "Continuar no WhatsApp", href: wa } : undefined}
      {...copy}
    />
  );
}
