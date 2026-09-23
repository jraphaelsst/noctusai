/**
 * Minimal, unauthenticated HTTP client for the public `/api/website/*`
 * endpoints (contract §3). Deliberately NOT `@noctusai/lib/api`'s
 * `createApiClient` — that factory targets authenticated product APIs
 * (token storage, refresh, dead-session redirect), none of which applies to
 * anonymous public traffic. Same-origin: the website is served by core.
 */
export interface LeadPayload {
  source: "waitlist" | "brief" | "contact";
  name: string;
  email?: string;
  phone?: string;
  company?: string;
  profile?: "smb" | "enterprise" | "developer" | "solo";
  product_interest?: string[];
  message?: string;
  locale: "pt-BR" | "en";
  consent_marketing: boolean;
  consent_text_version: string;
  utm?: Record<string, string>;
  landing_path?: string;
  referrer?: string;
  turnstile_token?: string;
}

export interface LeadResponse {
  id: string;
  whatsapp_url: string | null;
}

export interface PlanRow {
  id: string;
  slug: string;
  nome: string;
  descricao: string | null;
  price_monthly: number;
  price_yearly: number;
  max_users: number | null;
  max_products: number | null;
  features: string[];
  is_custom: boolean;
}

function baseUrl(): string {
  return typeof window !== "undefined" ? window.location.origin : "";
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : `http_${res.status}`;
  } catch {
    return `http_${res.status}`;
  }
}

export async function submitLead(payload: LeadPayload): Promise<LeadResponse> {
  const res = await fetch(`${baseUrl()}/api/website/leads`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const body = await res.json();
  return body.data as LeadResponse;
}

/** Fire-and-forget: never throws, never blocks the caller. */
export function postEvent(event: string, props?: Record<string, unknown>): void {
  if (typeof window === "undefined") return;
  const anonId = window.localStorage.getItem("nx.anon_id") ?? undefined;
  const payload = JSON.stringify({
    event,
    anon_id: anonId,
    session_id: window.sessionStorage.getItem("nx.session_id") ?? undefined,
    path: window.location.pathname,
    props: props ?? {},
  });
  fetch(`${baseUrl()}/api/website/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    keepalive: true,
  }).catch(() => {
    // Best-effort telemetry: a failed event must never surface to the user.
  });
}

export async function fetchPlans(): Promise<PlanRow[]> {
  const res = await fetch(`${baseUrl()}/api/website/plans`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = await res.json();
  return (body.data ?? []) as PlanRow[];
}
