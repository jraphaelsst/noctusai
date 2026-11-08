/**
 * Lead wire for the Agents landing: seed `LeadCaptureForm` values -> core's public
 * `POST /api/website/leads` (core is the CRM; the landing is served from another origin,
 * so the URL is `env.CORE_API_URL`, never `window.location.origin`).
 */
import { env } from "@noctusai/lib";
import type { LeadFormValues } from "@noctusai/lib/marketing";

/** Same consent text version core's own site stamps on its leads (products/core website consent). */
export const LANDING_CONSENT_TEXT_VERSION = "2026-09-23.v1";

const PROJECT_TYPE: Record<string, string> = {
  diagnostico: "Quero um diagnóstico",
  prototipo: "Quero ver um protótipo",
  producao: "Já sei o que construir",
  outro: "Outro",
};

export interface AgentsLeadPayload {
  source: "contact";
  name: string;
  email?: string;
  phone: string;
  company?: string;
  product_interest: string[];
  message?: string;
  locale: "pt-BR";
  consent_marketing: boolean;
  consent_text_version: string;
  landing_path?: string;
  referrer?: string;
  turnstile_token?: string;
}

export function toAgentsLeadPayload(values: LeadFormValues): AgentsLeadPayload {
  const parts = [values.tipo ? `Fase do projeto: ${PROJECT_TYPE[values.tipo] ?? values.tipo}` : null, values.mensagem].filter(Boolean);
  return {
    source: "contact",
    name: values.nome,
    phone: values.whatsapp,
    email: values.email,
    company: values.empresa,
    product_interest: ["agents"],
    message: parts.length > 0 ? parts.join("\n\n") : undefined,
    locale: "pt-BR",
    consent_marketing: values.consentimento,
    consent_text_version: LANDING_CONSENT_TEXT_VERSION,
    landing_path: typeof window !== "undefined" ? window.location.pathname : undefined,
    referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
    turnstile_token: values.turnstileToken,
  };
}

/** Rejects (so the organ shows its error notice and keeps the typed values) on any non-2xx. */
export async function submitAgentsLead(values: LeadFormValues): Promise<void> {
  const res = await fetch(`${env.CORE_API_URL.replace(/\/+$/, "")}/api/website/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toAgentsLeadPayload(values)),
  });
  if (!res.ok) throw new Error(`lead_http_${res.status}`);
}
