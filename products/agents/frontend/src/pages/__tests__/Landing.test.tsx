/** Agents landing: the sections are there, "Entrar" goes to /login, legal links are the seed /consent/* routes,
 * and the lead form posts to core's public endpoint with product_interest=["agents"]. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Landing from "../Landing";
import { toAgentsLeadPayload } from "@/lib/landingLead";

function renderLanding() {
  return render(
    <MemoryRouter>
      <Landing />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "IntersectionObserver",
    class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } },
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("Agents Landing", () => {
  it("renders the hero, both grids, steps, form, CTA and footer", () => {
    renderLanding();
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Agentes de IA que atendem por você");
    expect(screen.getByRole("heading", { name: "Cada agente tem um trabalho claro" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Julia · qualificação de leads" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Bia · assistente da equipe" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Você decide quando e com quem cada agente fala" })).toBeTruthy();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThan(10);
    expect(screen.getByRole("heading", { name: "Do primeiro teste ao atendimento de verdade" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Quer um agente trabalhando na sua empresa?" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Já tem agentes na sua organização?" })).toBeTruthy();
  });

  it("labels the illustrative hero panel as sample data", () => {
    renderLanding();
    expect(screen.getByRole("img", { name: /Dados de amostra/ })).toBeTruthy();
    expect(screen.getByText("Amostra")).toBeTruthy();
  });

  it("sends Entrar to the product login and legal links to the seed consent routes", () => {
    renderLanding();
    const entrar = screen.getAllByRole("link", { name: /Entrar/ });
    expect(entrar.length).toBeGreaterThan(0);
    for (const a of entrar) expect(a.getAttribute("href")).toBe("/login");
    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Central de Privacidade" }).getAttribute("href")).toBe("/consent");
    expect(within(footer).getByRole("link", { name: "Política de Privacidade" }).getAttribute("href")).toBe("/consent/privacy-policy");
    expect(within(footer).getByRole("link", { name: "Termos de Uso" }).getAttribute("href")).toBe("/consent/terms-of-use");
  });

  it("posts the lead to core with product_interest agents", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    renderLanding();
    fireEvent.change(screen.getByLabelText("Nome *"), { target: { value: "Ana" } });
    fireEvent.change(screen.getByLabelText("WhatsApp *"), { target: { value: "11 91234-5678" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(await screen.findByText("Recebemos a sua mensagem.")).toBeTruthy();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toMatch(/\/api\/website\/leads$/);
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toMatchObject({ source: "contact", name: "Ana", phone: "11912345678", product_interest: ["agents"], consent_marketing: true });
  });

  it("maps the project phase into the message", () => {
    const p = toAgentsLeadPayload({ nome: "A", whatsapp: "11912345678", consentimento: true, tipo: "diagnostico", mensagem: "oi" });
    expect(p.message).toBe("Fase do projeto: Quero um diagnóstico\n\noi");
  });
});
