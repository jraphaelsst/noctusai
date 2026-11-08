/**
 * Lead wire for a landing served from a NON-core origin (a product's own site): `LeadCaptureForm` values ->
 * core's public `POST /api/website/leads` (core is the CRM). The URL is `env.CORE_API_URL`, never
 * `window.location.origin`; the endpoint is public (no auth) and CORS-allowed for product origins.
 *
 * Core's own site keeps its same-origin wire (`products/core/.../lib/api.ts`); every other product uses this
 * adapter instead of a per-product copy (absorbed from agents' `landingLead.ts`).
 */
import { env } from "../env";
import type { LeadFormValues } from "./LeadCaptureForm";

/** Same consent-text version core's own site stamps on its leads. Bump together with core's `CONSENT_TEXT_VERSION`. */
export const LANDING_CONSENT_TEXT_VERSION = "2026-09-23.v1";

const PROJECT_TYPE: Record<string, string> = {
  diagnostico: "Quero um diagnóstico",
  prototipo: "Quero ver um protótipo",
  producao: "Já sei o que construir",
  outro: "Outro",
};

export interface CoreLeadPayload {
  source: "contact" | "brief" | "waitlist";
  name: string;
  email?: string;
  phone: string;
  company?: string;
  product_interest?: string[];
  message?: string;
  locale: "pt-BR" | "en";
  consent_marketing: boolean;
  consent_text_version: string;
  landing_path?: string;
  referrer?: string;
  turnstile_token?: string;
}

export interface CoreLeadOptions {
  /** Used when the form values carry none (the `product` variant sets it through the form's `productInterest`). */
  productInterest?: string;
  /** CRM lead `source`. Default "contact". */
  source?: CoreLeadPayload["source"];
  locale?: CoreLeadPayload["locale"];
  consentTextVersion?: string;
}

export function toCoreLeadPayload(values: LeadFormValues, opts: CoreLeadOptions = {}): CoreLeadPayload {
  const interest = values.product_interest ?? (opts.productInterest ? [opts.productInterest] : undefined);
  const parts = [values.tipo ? `Fase do projeto: ${PROJECT_TYPE[values.tipo] ?? values.tipo}` : null, values.mensagem].filter(Boolean);
  return {
    source: opts.source ?? "contact",
    name: values.nome,
    phone: values.whatsapp,
    email: values.email,
    company: values.empresa,
    product_interest: interest,
    message: parts.length > 0 ? parts.join("\n\n") : undefined,
    locale: opts.locale ?? "pt-BR",
    consent_marketing: values.consentimento,
    consent_text_version: opts.consentTextVersion ?? LANDING_CONSENT_TEXT_VERSION,
    landing_path: typeof window !== "undefined" ? window.location.pathname : undefined,
    referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
    turnstile_token: values.turnstileToken,
  };
}

/** Rejects (so the organ shows its error notice and keeps the typed values) on any non-2xx. */
export async function submitCoreLead(values: LeadFormValues, opts: CoreLeadOptions = {}): Promise<void> {
  const res = await fetch(`${env.CORE_API_URL.replace(/\/+$/, "")}/api/website/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toCoreLeadPayload(values, opts)),
  });
  if (!res.ok) throw new Error(`lead_http_${res.status}`);
}

/** `onSubmit` for `LeadCaptureForm`, bound to options: `onSubmit={createCoreLeadSubmit({ productInterest: "agents" })}`. */
export function createCoreLeadSubmit(opts: CoreLeadOptions = {}): (values: LeadFormValues) => Promise<void> {
  return (values) => submitCoreLead(values, opts);
}
