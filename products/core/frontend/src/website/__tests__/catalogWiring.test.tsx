import "@testing-library/jest-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { LocaleProvider } from "../lib/i18n";
import { CatalogProvider, useCatalog } from "../lib/catalog";
import { parseCatalog, type CatalogRow } from "../lib/api";
import { toOrganProducts, toNavProducts } from "../lib/catalogView";
import { toLeadPayload } from "../components/SiteLeadForm";
import ProductsIndex from "../pages/ProductsIndex";

const row = (slug: string, nome: string, status: CatalogRow["status"], destaque: number | null = null): CatalogRow => ({
  slug, nome, status, destaque_no_site: destaque, icone: "Box", descricao_publica: `Texto de ${nome}.`,
});
const ROWS = [row("social-wiring", "Social Wiring", "disponivel"), row("agents", "Agentes", "disponivel"), row("orbity", "Orbity", "lista_de_espera")];

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } });
  vi.stubGlobal("matchMedia", vi.fn().mockImplementation((q: string) => ({
    matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(),
  })));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Probe() {
  const { products, isLoading, isError } = useCatalog();
  return <p data-testid="probe">{products ? `n=${products.length}` : isLoading ? "loading" : isError ? "error" : "?"}</p>;
}

describe("parseCatalog", () => {
  it("keeps valid rows, drops malformed ones, blanks empty descriptions", () => {
    const out = parseCatalog([{ slug: "a", nome: "A", status: "disponivel", descricao_publica: "  " }, { slug: 1 }, null, { slug: "b", nome: "B", status: "x" }]);
    expect(out).toEqual([{ slug: "a", nome: "A", status: "disponivel", descricao_publica: null, icone: null, destaque_no_site: null }]);
  });
  it("rejects a non-array", () => expect(parseCatalog({})).toBeNull());
});

describe("catalog -> organs", () => {
  it("gives Conhecer only to products that have a chapter page", () => {
    const p = toOrganProducts(ROWS, "pt-BR");
    expect(p.find((x) => x.slug === "social-wiring")?.url).toBe("/produtos/social-wiring");
    expect(p.find((x) => x.slug === "agents")?.url).toBeUndefined();
  });
  it("lists only disponível products in the nav", () => {
    expect(toNavProducts(ROWS, "pt-BR").map((n) => n.nome)).toEqual(["Social Wiring", "Agentes"]);
  });
});

describe("CatalogProvider states", () => {
  it("never shows data it does not have: loading first, then the fetched rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ROWS }));
    render(<CatalogProvider initial={null}><Probe /></CatalogProvider>);
    expect(screen.getByTestId("probe")).toHaveTextContent("loading");
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("n=3"));
  });
  it("keeps the snapshot when the refresh fails (an error never replaces data)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    render(<CatalogProvider initial={ROWS}><Probe /></CatalogProvider>);
    expect(screen.getByTestId("probe")).toHaveTextContent("n=3");
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByTestId("probe")).toHaveTextContent("n=3");
  });
  it("surfaces the error when there is nothing to show", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    render(<CatalogProvider initial={null}><Probe /></CatalogProvider>);
    await waitFor(() => expect(screen.getByTestId("probe")).toHaveTextContent("error"));
  });
});

describe("ProductsIndex", () => {
  it("renders the catalog grid with status labels and 'Avise-me' on waitlist rows", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ROWS }));
    render(
      <LocaleProvider locale="pt-BR"><CatalogProvider initial={ROWS}><ProductsIndex /></CatalogProvider></LocaleProvider>,
    );
    expect(screen.getByRole("heading", { name: "Produtos NoctusAI" })).toBeInTheDocument();
    expect(screen.getAllByText("Disponível").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Avise-me quando abrir: Orbity/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ver todos/ })).toBeNull(); // 3 <= 6 featured: nothing to expand
  });
});

describe("toLeadPayload", () => {
  it("maps the organ values onto the contract §3 body", () => {
    const body = toLeadPayload(
      { nome: "Ana", whatsapp: "11912345678", consentimento: true, tipo: "diagnostico", mensagem: "Oi", product_interest: ["orbity"] },
      "waitlist", "pt-BR",
    );
    expect(body).toMatchObject({ source: "waitlist", name: "Ana", phone: "11912345678", product_interest: ["orbity"], locale: "pt-BR", consent_marketing: true });
    expect(body.message).toContain("Quero um diagnóstico");
    expect(body.message).toContain("Oi");
  });
});
