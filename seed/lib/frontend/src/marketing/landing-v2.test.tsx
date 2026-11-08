/**
 * Landing organs v2: every new prop is opt-in and the default render is unchanged.
 * (Defaults are covered by landing-organs.test.tsx; core's website tests run the same organs unchanged.)
 */
import { renderToString } from "react-dom/server";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: vi.fn() }));

import {
  CtaBand, FeatureGrid, Hero, LandingFooter, LandingIcon, LandingNav, LandingThemeProvider, LeadCaptureForm,
  ProductBrandScope, ThemeSwitch, THEME_INLINE_SCRIPT, createThemeInlineScript, createCoreLeadSubmit, productBrandCss,
  productBrandVars, submitCoreLead, toCoreLeadPayload, useLandingTheme,
} from "./index";
import type { LeadFormValues, ProductBrand } from "./index";
import { productUrl } from "../env";

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  window.localStorage.clear();
  document.documentElement.classList.remove("dark");
  document.documentElement.removeAttribute("data-theme");
});

const AGENTS: ProductBrand = { primary: "232 45% 42%", primaryLight: "230 80% 78%", primaryDark: "232 50% 28%" };
const SW: ProductBrand = { primary: "174 70% 26%", primaryLight: "170 55% 62%", primaryDark: "174 70% 18%" };

describe("Hero v2", () => {
  const base = { title: "Agentes de IA que atendem por você,", titleEmphasis: "sob o seu controle", lede: "Lede.", actions: [{ label: "Falar", href: "#c", variant: "primary" as const }, { label: "Ver", href: "#v" }] };

  it("default: emphasis stays muted and the section is the plain band", () => {
    render(<Hero {...base} />);
    expect(screen.getByText("sob o seu controle")).toHaveClass("text-muted-foreground");
    expect(document.querySelector("section")).not.toHaveClass("bg-sidebar");
  });

  it("accentEmphasis colours the emphasis with the accent (primary-light on dark), not muted", () => {
    render(<Hero {...base} accentEmphasis />);
    const em = screen.getByText("sob o seu controle");
    expect(em).toHaveClass("text-primary", "dark:text-primary-light");
    expect(em).not.toHaveClass("text-muted-foreground");
  });

  it("inverse is a dark sidebar band with an aria-hidden glow and accent-light emphasis; outline CTA is re-toned", () => {
    render(<Hero {...base} variant="inverse" accentEmphasis eyebrow="Agentes NoctusAI" />);
    const section = document.querySelector("section")!;
    expect(section).toHaveClass("bg-sidebar", "text-sidebar-foreground");
    expect(section.querySelector("[data-hero-glow]")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("sob o seu controle")).toHaveClass("text-primary-light");
    expect(screen.getByRole("link", { name: "Ver" })).toHaveClass("border-sidebar-border", "text-sidebar-foreground");
    expect(screen.getByRole("link", { name: /Falar/ })).toHaveClass("bg-primary");
    expect(screen.getByRole("heading", { level: 1 })).toHaveClass("text-sidebar-foreground");
  });

  it("bareMedia renders the slot without the Card wrapper but keeps the accessible name", () => {
    const { rerender } = render(<Hero {...base} media={<i data-testid="m" />} mediaLabel="Painel" />);
    expect(screen.getByRole("img", { name: "Painel" })).toHaveClass("bg-card");
    rerender(<Hero {...base} media={<i data-testid="m" />} mediaLabel="Painel" bareMedia />);
    const img = screen.getByRole("img", { name: "Painel" });
    expect(img).not.toHaveClass("bg-card");
    expect(within(img).getByTestId("m")).toBeInTheDocument();
  });

  it("stats render as a definition list; empty stats render nothing", () => {
    const { rerender } = render(<Hero {...base} stats={[{ value: "24/7", label: "atendimento" }, { value: "2", label: "agentes" }]} />);
    const dl = document.querySelector("dl")!;
    expect(dl.querySelectorAll("dt")).toHaveLength(2);
    expect(within(dl).getByText("24/7").tagName).toBe("DD");
    rerender(<Hero {...base} stats={[]} />);
    expect(document.querySelector("dl")).toBeNull();
  });

  it.each(["reveal", "staggered"] as const)("entrance=%s never prerenders content hidden", (entrance) => {
    const html = renderToString(<Hero {...base} entrance={entrance} media={<i />} stats={[{ value: "1", label: "x" }]} chips={[{ label: "Julia", href: "#" }]} />);
    expect(html).not.toMatch(/opacity:\s*0[;"]/);
    expect(html).toContain("sob o seu controle");
  });
});

describe("FeatureGrid v2", () => {
  const items = [
    { title: "Julia", description: "Qualifica leads.", tag: "WhatsApp", bullets: ["Nota fixa", "Consulta imóveis"], icon: "MessageCircle", link: { label: "Atende pelo Social Wiring", href: "https://sw.example", brand: SW } },
    { title: "Bia", description: "Assistente.", tag: "Web" },
  ];

  it("columns=2 and cardVariant=large", () => {
    render(<FeatureGrid title="Agentes" items={items} columns={2} cardVariant="large" />);
    expect(document.querySelector("ul")).toHaveClass("lg:grid-cols-2");
    expect(screen.getByRole("heading", { level: 3, name: "Julia" })).toHaveClass("text-xl");
  });

  it("default columns/variant are unchanged (3 columns, compact)", () => {
    render(<FeatureGrid title="t" items={[{ title: "a", description: "b" }]} />);
    expect(document.querySelector("ul")).toHaveClass("lg:grid-cols-3");
    expect(screen.getByRole("heading", { level: 3 })).toHaveClass("text-base");
  });

  it("renders the tag chip and a check list", () => {
    render(<FeatureGrid title="t" items={items} />);
    expect(screen.getByText("WhatsApp")).toBeInTheDocument();
    const bullets = screen.getByText("Nota fixa").closest("ul")!;
    expect(within(bullets).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Nota fixa", "Consulta imóveis"]);
    expect(bullets.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("link is an inline anchor (not a button), stretched over the card, carrying the other product's accent", () => {
    render(<FeatureGrid title="t" items={items} accent />);
    const a = screen.getByRole("link", { name: "Atende pelo Social Wiring" });
    expect(a).toHaveAttribute("href", "https://sw.example");
    expect(a.className).toContain("after:absolute");
    expect(a).toHaveClass("text-primary", "dark:text-primary-light");
    expect(a.style.getPropertyValue("--primary")).toBe(SW.primary);
    expect(a.style.getPropertyValue("--primary-light")).toBe(SW.primaryLight);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("link without brand sets no inline variables; cta wins over link", () => {
    render(<FeatureGrid title="t" items={[
      { title: "x", description: "d", link: { label: "L", href: "/l" } },
      { title: "y", description: "d", cta: { label: "C", href: "/c" }, link: { label: "ignored", href: "/i" } },
    ]} />);
    expect(screen.getByRole("link", { name: "L" })).not.toHaveAttribute("style");
    expect(screen.queryByRole("link", { name: "ignored" })).toBeNull();
    expect(screen.getByRole("link", { name: "C" })).toBeInTheDocument();
  });

  it("accent tints the eyebrow and icon chip; default stays neutral", () => {
    const { rerender } = render(<FeatureGrid title="t" eyebrow="Os agentes" items={items} />);
    expect(screen.getByText("Os agentes")).toHaveClass("text-muted-foreground");
    rerender(<FeatureGrid title="t" eyebrow="Os agentes" items={items} accent />);
    expect(screen.getByText("Os agentes")).toHaveClass("text-primary", "dark:text-primary-light");
  });

  it("revealItems keeps every card in the server HTML, visible", () => {
    const html = renderToString(<FeatureGrid title="t" items={items} revealItems />);
    expect(html).toContain("Julia");
    expect(html).toContain("Bia");
    expect(html).not.toMatch(/opacity:\s*0[;"]/);
  });

  it("registers the new icons (no fallback Box for any of them)", () => {
    const names = ["Power", "FlaskConical", "GitMerge", "Target", "Lock", "MessageCircle", "Kanban", "Building", "FileText", "Megaphone", "Wand", "Users", "Calendar", "Share2", "Bot"];
    const box = renderToString(<LandingIcon name="__unknown__" />);
    for (const n of names) expect(renderToString(<LandingIcon name={n} />), n).not.toBe(box);
  });
});

describe("LandingNav v2", () => {
  const props = { brand: { label: "Agentes", href: "#top" }, links: [{ label: "Controle", href: "#controle" }], loginAction: { label: "Entrar", href: "/login" }, primaryAction: { label: "Falar com a gente", href: "#contato" } };

  it("renders no Produtos disclosure (nor drawer entry) when products is not passed", () => {
    render(<LandingNav {...props} />);
    expect(screen.queryByRole("button", { name: /Produtos/ })).toBeNull();
    expect(screen.queryByRole("link", { name: "Produtos" })).toBeNull();
  });

  it("still renders it when products + allProductsHref are passed (core)", () => {
    render(<LandingNav {...props} products={[]} allProductsHref="/produtos" />);
    expect(screen.getByRole("button", { name: /Produtos/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("loginAlwaysVisible shows Entrar at every width; primaryActionDesktopOnly hides the CTA below lg", () => {
    const { rerender } = render(<LandingNav {...props} />);
    expect(screen.getAllByRole("link", { name: "Entrar", hidden: true })[0]).toHaveClass("hidden", "lg:inline-flex");
    rerender(<LandingNav {...props} loginAlwaysVisible primaryActionDesktopOnly />);
    const entrar = screen.getAllByRole("link", { name: "Entrar", hidden: true });
    expect(entrar).toHaveLength(1);
    expect(entrar[0].className).not.toContain("hidden");
    expect(screen.getByRole("link", { name: "Falar com a gente" })).toHaveClass("hidden", "lg:inline-flex");
  });

  it("the drawer holds the links and the theme control", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<LandingNav {...props} loginAlwaysVisible themeSwitch={{ value: "system", onChange }} />);
    await user.click(screen.getByRole("button", { name: "Abrir menu" }));
    const drawer = screen.getByRole("navigation", { name: "Principal (celular)" });
    expect(within(drawer).getByRole("link", { name: "Controle" })).toBeInTheDocument();
    const groups = screen.getAllByRole("group", { name: "Tema" });
    await user.click(within(groups[groups.length - 1]).getByRole("button", { name: "Tema escuro" }));
    expect(onChange).toHaveBeenCalledWith("dark");
  });
});

describe("ThemeSwitch + LandingThemeProvider (lifted from core)", () => {
  it("ThemeSwitch is a 3-state pressed group", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ThemeSwitch value="light" onChange={onChange} />);
    const group = screen.getByRole("group", { name: "Tema" });
    expect(within(group).getByRole("button", { name: "Tema claro" })).toHaveAttribute("aria-pressed", "true");
    expect(within(group).getByRole("button", { name: "Tema do sistema" })).toHaveAttribute("aria-pressed", "false");
    await user.click(within(group).getByRole("button", { name: "Tema escuro" }));
    expect(onChange).toHaveBeenCalledWith("dark");
  });

  function Probe() {
    const { choice, resolved, setChoice } = useLandingTheme();
    return (
      <div>
        <output>{choice}/{resolved}</output>
        <button onClick={() => setChoice("dark")}>dark</button>
        <button onClick={() => setChoice("light")}>light</button>
      </div>
    );
  }

  it("persists the choice and drives .dark + data-theme on <html>", async () => {
    const user = userEvent.setup();
    render(<LandingThemeProvider><Probe /></LandingThemeProvider>);
    await user.click(screen.getByRole("button", { name: "dark" }));
    expect(window.localStorage.getItem("nx.theme")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    await user.click(screen.getByRole("button", { name: "light" }));
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("restores a stored choice after mount (server and first paint start at system)", async () => {
    window.localStorage.setItem("nx.theme", "light");
    render(<LandingThemeProvider><Probe /></LandingThemeProvider>);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("light/light"));
  });

  it("is SSR-safe and the inline script uses the given key", () => {
    expect(() => renderToString(<LandingThemeProvider><Probe /></LandingThemeProvider>)).not.toThrow();
    expect(THEME_INLINE_SCRIPT).toContain('"nx.theme"');
    expect(createThemeInlineScript("agents.theme")).toContain('var k="agents.theme"');
  });
});

describe("LeadCaptureForm product variant", () => {
  const props = {
    variant: "product" as const, title: "Quer um agente?", heading: "Pedir contato", productInterest: "agents",
    submitLabel: "Pedir contato", messageHint: "Ex.: “Quero que alguém responda os leads.”", messagePlaceholder: "Escreva aqui",
    consentSubject: "os Agentes", successTitle: "Pedido recebido.", successBody: "Uma pessoa da equipe vai chamar você.", againLabel: "Enviar outro pedido",
    turnstileSiteKey: "",
  };

  it("has no phase select and no Empresa field", () => {
    render(<LandingForm />);
    expect(screen.queryByLabelText(/Em que fase/)).toBeNull();
    expect(screen.queryByLabelText(/Empresa/)).toBeNull();
    expect(screen.getByLabelText(/E-mail/)).toBeInTheDocument();
  });

  function LandingForm(extra: Partial<React.ComponentProps<typeof LeadCaptureForm>> = {}) {
    return <LeadCaptureForm onSubmit={vi.fn()} {...props} {...extra} />;
  }

  it("applies the pt-BR copy overrides and the product consent sentence", () => {
    render(<LandingForm />);
    expect(screen.getByRole("button", { name: "Pedir contato" })).toBeInTheDocument();
    expect(screen.getByText(/Quero que alguém responda/)).toBeInTheDocument();
    expect(screen.getByLabelText("O que você precisa?")).toHaveAttribute("placeholder", "Escreva aqui");
    const consent = screen.getByRole("checkbox").closest("label")!;
    expect(consent.textContent).toContain("Concordo em ser contatado pela NoctusAI sobre os Agentes, conforme a Política de Privacidade.");
  });

  it("brief defaults are untouched (this-subject sentence, phase + company)", () => {
    render(<LeadCaptureForm variant="brief" onSubmit={vi.fn()} title="t" heading="h" turnstileSiteKey="" />);
    expect(screen.getByLabelText(/Em que fase/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Empresa/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox").closest("label")!.textContent).toContain("sobre este assunto, conforme a");
    expect(screen.getByRole("button", { name: "Enviar mensagem" })).toBeInTheDocument();
  });

  it("submits product_interest, never tipo/empresa, then shows the custom success copy and reset label", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<LandingForm onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText(/Nome/), "Ana");
    await user.type(screen.getByLabelText(/WhatsApp/), "11 91234-5678");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Pedir contato" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const v: LeadFormValues = onSubmit.mock.calls[0][0];
    expect(v).toMatchObject({ nome: "Ana", whatsapp: "11912345678", consentimento: true, product_interest: ["agents"] });
    expect(v).not.toHaveProperty("tipo");
    expect(v).not.toHaveProperty("empresa");
    expect(await screen.findByText("Pedido recebido.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enviar outro pedido" })).toBeInTheDocument();
  });
});

describe("core lead adapter (non-core origin)", () => {
  const values: LeadFormValues = { nome: "Ana", whatsapp: "11912345678", consentimento: true, mensagem: "Oi", tipo: "diagnostico", turnstileToken: "tok" };

  it("maps values to core's contract body", () => {
    expect(toCoreLeadPayload(values, { productInterest: "agents" })).toMatchObject({
      source: "contact", name: "Ana", phone: "11912345678", product_interest: ["agents"], locale: "pt-BR",
      consent_marketing: true, consent_text_version: "2026-09-23.v1", turnstile_token: "tok",
      message: "Fase do projeto: Quero um diagnóstico\n\nOi",
    });
  });

  it("form-carried product_interest wins over the option", () => {
    expect(toCoreLeadPayload({ ...values, product_interest: ["sw"] }, { productInterest: "agents" }).product_interest).toEqual(["sw"]);
  });

  it("POSTs to env.CORE_API_URL/api/website/leads (not window.location.origin)", async () => {
    vi.stubEnv("VITE_CORE_API_URL", "https://core.example.com/");
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await createCoreLeadSubmit({ productInterest: "social-wiring" })(values);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://core.example.com/api/website/leads");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).product_interest).toEqual(["social-wiring"]);
  });

  it("rejects on a non-2xx so the organ keeps the typed values", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422 }));
    await expect(submitCoreLead(values)).rejects.toThrow("lead_http_422");
  });
});

describe("CtaBand + LandingFooter v2", () => {
  it("CtaBand inverse is a sidebar band; default is unchanged", () => {
    const actions = [{ label: "Entrar", href: "/e", variant: "primary" as const }, { label: "Falar", href: "/f" }];
    const { rerender } = render(<CtaBand title="t" actions={actions} />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveClass("text-foreground");
    rerender(<CtaBand title="t" description="d" actions={actions} variant="inverse" />);
    expect(screen.getByRole("heading", { level: 2 })).toHaveClass("text-sidebar-foreground");
    expect(screen.getByRole("link", { name: "Falar" })).toHaveClass("border-sidebar-border");
    expect(document.querySelector("section > div > div > div")).toHaveClass("bg-sidebar");
  });

  it("footer tagline accepts a node (a link)", () => {
    render(<LandingFooter brand={<b>Agentes</b>} tagline={<>Um produto <a href="https://noctusai.com">NoctusAI</a></>} columns={[]} copyright="c" />);
    expect(screen.getByRole("link", { name: "NoctusAI" })).toHaveAttribute("href", "https://noctusai.com");
  });
});

describe("productBrand (static per-product accent)", () => {
  it("emits the light set on the scope and the dark ring, from validated triplets only", () => {
    const css = productBrandCss(AGENTS);
    expect(css).toContain("[data-product-brand]{--primary:232 45% 42%;--primary-light:230 80% 78%;--primary-dark:232 50% 28%;--ring:232 45% 42%");
    expect(css).toContain(".dark [data-product-brand]{--ring:230 80% 78%");
  });

  it("drops an invalid brand instead of injecting it", () => {
    const bad = { ...AGENTS, primary: "red; } body { display:none" };
    expect(productBrandCss(bad)).toBe("");
    expect(productBrandVars(bad)).toEqual({});
  });

  it("ProductBrandScope wraps children in a layout-less scope element with the stylesheet", () => {
    render(<ProductBrandScope brand={SW}><p>conteúdo</p></ProductBrandScope>);
    const scope = screen.getByText("conteúdo").parentElement!;
    expect(scope).toHaveAttribute("data-product-brand");
    expect(scope).toHaveClass("contents");
    expect(scope.querySelector("style")!.textContent).toContain("--primary:174 70% 26%");
  });

  // WCAG 2.2 AA: contrast of the declared accents against the seed tokens (light bg 0 0% 97%, dark bg 0 0% 8%,
  // inverse band = sidebar 0 0% 10%). Text >= 4.5:1; the dark focus ring (primary-light) >= 3:1.
  const lum = ([h, s, l]: number[]) => {
    const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
    const f = (n: number) => { const k = (n + h / 30) % 12; return l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); };
    const lin = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return 0.2126 * lin(f(0)) + 0.7152 * lin(f(8)) + 0.0722 * lin(f(4));
  };
  const hsl = (t: string) => t.replace(/%/g, "").split(" ").map(Number);
  const ratio = (a: string, b: string) => { const [x, y] = [lum(hsl(a)), lum(hsl(b))].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

  it.each([["agents", AGENTS], ["social-wiring", SW]] as const)("%s accent meets AA on every surface it is used on", (_n, b) => {
    expect(ratio("0 0% 100%", b.primary)).toBeGreaterThanOrEqual(4.5);   // white label on primary fill
    expect(ratio(b.primary, "0 0% 97%")).toBeGreaterThanOrEqual(4.5);    // accent text, light background
    expect(ratio(b.primaryLight, "0 0% 8%")).toBeGreaterThanOrEqual(4.5); // accent text, dark background
    expect(ratio(b.primaryLight, "0 0% 10%")).toBeGreaterThanOrEqual(4.5); // accent text, inverse band
    expect(ratio(b.primaryLight, "0 0% 8%")).toBeGreaterThanOrEqual(3);   // dark focus ring
    expect(ratio("0 0% 100%", b.primaryDark)).toBeGreaterThanOrEqual(4.5); // hover fill
  });
});

describe("productUrl (cross-product public URL)", () => {
  it("falls back to the canonical prod URL", () => {
    expect(productUrl("social-wiring")).toBe("https://social-wiring.noctusai.com");
    expect(productUrl("agents", "/entrar")).toBe("https://agents.noctusai.com/entrar");
  });

  it("a per-product pin beats the pattern", () => {
    vi.stubEnv("VITE_PRODUCT_URL_PATTERN", "https://{slug}.example.com");
    vi.stubEnv("VITE_PRODUCT_URL_SOCIAL_WIRING", "https://social.noctusai.com/");
    expect(productUrl("social-wiring")).toBe("https://social.noctusai.com");
    expect(productUrl("agents")).toBe("https://agents.example.com");
  });

  it("the pattern supports {slug_underscored}", () => {
    vi.stubEnv("VITE_PRODUCT_URL_PATTERN", "https://app.example.com/{slug_underscored}/");
    expect(productUrl("social-wiring", "x")).toBe("https://app.example.com/social_wiring/x");
  });

  it("refuses a malformed slug", () => {
    expect(() => productUrl("../evil")).toThrow(/invalid product slug/);
    expect(() => productUrl("")).toThrow();
  });
});

void act;
