/**
 * Integrações cards (Slice F) over a mocked `api`, real hooks:
 *   SMTP   — origem badge, password omitted on save keeps it, "Testar envio"
 *   Gmail  — GCP-pending notice, "Conectar" asks for the OAuth start URL
 *   Leads  — webhook URL shown for copy, non-admins get a disabled form
 *   Page   — `?gmail=erro&motivo=` becomes a pt-BR toast and is cleared
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

const { api, user, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
  user: { current: { id: "u1", user_metadata: { org_role: "owner" } as Record<string, unknown> } },
  toast: { success: vi.fn(), error: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api, useAuthStore: () => ({ user: user.current }) }));
vi.mock("sonner", () => ({ toast }));

import { GmailCard } from "../GmailCard";
import { MetaLeadsCard, WhatsappLeadsCard } from "../LeadSourceCards";
import { SmtpCard } from "../SmtpCard";
import Integracoes from "@/pages/Integracoes";

const SMTP_ORG = {
  configurado: true, origem: "org", host: "smtp.agencia.com", port: 587, username: "envio@agencia.com",
  security: "starttls", from_email: "envio@agencia.com", from_name: "Agência",
};
const GMAIL_SEM_GCP = {
  conectado: false, email: null, watch_ativo: false, expira_em: null, configuracao_gcp_ok: false, ultimo_erro: null,
};
const WHATSAPP = {
  configurado: true, base_url: "https://waha.agencia.com", session: "default", api_key_configurada: true,
  webhook_url: "https://igig.noctusai.com/api/webhooks/waha/org.tok", webhook_url_erro: null,
  hmac_configurado: true, cofre_configurado: true, conectado_em: null, ultimo_erro: null,
};
const META = {
  configurado: false, page_id: null, verify_token_configurado: false, page_access_token_configurado: false,
  app_secret_configurado: true, app_secret_origem: "plataforma", webhook_url: "https://igig.noctusai.com/api/webhooks/meta/leadgen",
  webhook_url_erro: null, cofre_configurado: true, conectado_em: null, ultimo_erro: null,
};

let lastLocation = "";
function LocationProbe() {
  const loc = useLocation();
  lastLocation = `${loc.pathname}${loc.search}`;
  return null;
}

function renderWith(ui: ReactNode, url = "/integracoes") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        {ui}
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  user.current = { id: "u1", user_metadata: { org_role: "owner" } };
  api.get.mockImplementation(async (path: string) => {
    if (path === "/api/integracoes/email/smtp") return { data: SMTP_ORG };
    if (path === "/api/integracoes/email/gmail") return { data: GMAIL_SEM_GCP };
    if (path === "/api/integracoes/email/gmail/oauth/start") return { data: { url: "https://accounts.google.com/o/oauth2" } };
    if (path === "/api/integracoes/leads/whatsapp") return { data: WHATSAPP };
    if (path === "/api/integracoes/leads/meta") return { data: META };
    if (path === "/api/integracoes") return [];
    throw new Error(`GET inesperado ${path}`);
  });
  api.put.mockImplementation(async (_p: string, body: Record<string, unknown>) => ({ data: { ...SMTP_ORG, ...body } }));
  api.post.mockResolvedValue({ data: { message_id: "<m1@agencia>" } });
});
afterEach(cleanup);

describe("SmtpCard", () => {
  it("shows the origem badge and keeps the stored password when the field is left empty", async () => {
    renderWith(<SmtpCard />);
    const card = await screen.findByTestId("smtp-card");
    expect(await within(card).findByText("configurado")).toBeInTheDocument();
    const host = await within(card).findByDisplayValue("smtp.agencia.com");
    fireEvent.change(host, { target: { value: "smtp2.agencia.com" } });
    fireEvent.click(within(card).getByRole("button", { name: "Salvar SMTP" }));
    await waitFor(() => expect(api.put).toHaveBeenCalledTimes(1));
    const [path, body] = api.put.mock.calls[0] as [string, Record<string, unknown>];
    expect(path).toBe("/api/integracoes/email/smtp");
    expect(body.host).toBe("smtp2.agencia.com");
    expect(body.password).toBeUndefined();
  });

  it("the platform fallback is named, never hidden", async () => {
    api.get.mockImplementation(async (path: string) => {
      if (path === "/api/integracoes/email/smtp") {
        return { data: { ...SMTP_ORG, origem: "plataforma", from_email: "no-reply@noctusai.com" } };
      }
      throw new Error(path);
    });
    renderWith(<SmtpCard />);
    expect(await screen.findByText("usando SMTP da plataforma")).toBeInTheDocument();
    expect(screen.getByText(/no-reply@noctusai.com/)).toBeInTheDocument();
  });

  it("Testar envio posts the recipient", async () => {
    renderWith(<SmtpCard />);
    const para = await screen.findByLabelText("E-mail de teste");
    fireEvent.change(para, { target: { value: "eu@agencia.com" } });
    fireEvent.click(screen.getByRole("button", { name: /Testar envio/ }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith("/api/integracoes/email/smtp/testar", { para: "eu@agencia.com" }),
    );
  });
});

describe("GmailCard", () => {
  it("warns loudly when the platform GCP setup is pending", async () => {
    renderWith(<GmailCard />);
    expect(await screen.findByTestId("gmail-gcp-pendente")).toHaveTextContent("Configuração GCP pendente");
  });

  it("Conectar asks the server for the Google consent URL", async () => {
    // The navigation to Google itself is the browser's job (jsdom cannot
    // navigate and `location.assign` is non-configurable there) — this
    // asserts the card asks the server for the URL instead of building one.
    renderWith(<GmailCard />);
    fireEvent.click(await screen.findByTestId("gmail-conectar"));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith("/api/integracoes/email/gmail/oauth/start"));
  });
});

describe("Lead source cards", () => {
  it("shows the WAHA webhook URL for copy and saves without resending the stored API key", async () => {
    renderWith(<WhatsappLeadsCard />);
    const card = await screen.findByTestId("whatsapp-leads-card");
    expect(await within(card).findByText(WHATSAPP.webhook_url)).toBeInTheDocument();
    fireEvent.change(within(card).getByDisplayValue("default"), { target: { value: "vendas" } });
    fireEvent.click(within(card).getByRole("button", { name: "Salvar WhatsApp" }));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/api/integracoes/leads/whatsapp", {
        base_url: "https://waha.agencia.com",
        session: "vendas",
      }),
    );
  });

  it("non-admins see the status but cannot edit", async () => {
    user.current = { id: "u2", user_metadata: { org_role: "member" } };
    renderWith(<MetaLeadsCard />);
    const card = await screen.findByTestId("meta-leads-card");
    expect(await within(card).findByText(/Somente administradores/)).toBeInTheDocument();
    expect(within(card).getByPlaceholderText("1234567890")).toBeDisabled();
    expect(within(card).queryByRole("button", { name: "Salvar Meta" })).not.toBeInTheDocument();
  });
});

describe("Integrações page — Gmail OAuth return", () => {
  it("turns ?gmail=erro&motivo= into a pt-BR toast and clears the params", async () => {
    renderWith(<Integracoes />, "/integracoes?gmail=erro&motivo=state_invalido");
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("a autorização expirou")));
    await waitFor(() => expect(lastLocation).toBe("/integracoes"));
  });

  it("?gmail=ok says it connected", async () => {
    renderWith(<Integracoes />, "/integracoes?gmail=ok");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Gmail conectado."));
  });
});
