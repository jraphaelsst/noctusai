/**
 * Public landing: the approved sections render from the seed organs, the hero
 * sample is labelled, no placeholder metric ships, and the lead goes to core
 * with the product interest.
 */
import "@testing-library/jest-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Landing from "./Landing";

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } });
  vi.stubGlobal("matchMedia", vi.fn().mockImplementation((q: string) => ({
    matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(),
  })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("Landing", () => {
  it("renders the sections with the sample label and no placeholder numbers", () => {
    render(<Landing />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Do primeiro “oi” no WhatsApp ao contrato, num lugar só.");
    expect(screen.getByText("Social Wiring · para imobiliárias")).toBeInTheDocument();
    expect(screen.getByText("Amostra")).toBeInTheDocument();
    expect(screen.queryByText("[nº]")).not.toBeInTheDocument();
    for (const h of [
      "Tudo o que a imobiliária usa no dia a dia",
      "Uma atendente que não deixa lead esperando",
      "Do cadastro ao primeiro lead atendido",
      "Quer ver o Social Wiring na sua imobiliária?",
      "Já usa o Social Wiring?",
    ]) {
      expect(screen.getByRole("heading", { name: h })).toBeInTheDocument();
    }
  });

  it("points Entrar to the product login and legal links to the seed consent routes", () => {
    render(<Landing />);
    const entrar = screen.getAllByRole("link", { name: /Entrar/ });
    expect(entrar.length).toBeGreaterThan(0);
    expect(entrar.every((a) => a.getAttribute("href") === "/login")).toBe(true);
    for (const a of screen.getAllByRole("link", { name: "Política de Privacidade" })) expect(a).toHaveAttribute("href", "/consent/privacy-policy");
    expect(screen.getByRole("link", { name: "Termos de Uso" })).toHaveAttribute("href", "/consent/terms-of-use");
    expect(screen.getByRole("link", { name: "Central de Privacidade" })).toHaveAttribute("href", "/consent");
  });

  it("sends the lead to core with product_interest social-wiring", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<Landing />);
    await user.type(screen.getByLabelText(/^Nome/), "Ana");
    await user.type(screen.getByLabelText(/^WhatsApp/), "11912345678");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: /Enviar mensagem/ }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/website\/leads$/);
    expect(JSON.parse(init.body)).toMatchObject({
      source: "contact", name: "Ana", phone: "11912345678", product_interest: ["social-wiring"], consent_marketing: true,
    });
  });
});
