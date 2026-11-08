import { renderToString } from "react-dom/server";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: vi.fn() }));
import { toast } from "sonner";

import {
  CtaBand, Faq, FeatureGrid, Hero, LandingFooter, LandingNav, LeadCaptureForm, LEAD_MESSAGES,
  ProductCatalogGrid, selectFeaturedProducts, Steps,
} from "./index";
import type { CatalogProduct, LeadFormValues } from "./index";

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "IntersectionObserver",
    class { observe() {} unobserve() {} disconnect() {} takeRecords() { return []; } },
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const p = (slug: string, nome: string, status: CatalogProduct["status"], destaque: number | null = null, extra: Partial<CatalogProduct> = {}): CatalogProduct => ({
  slug, nome, status, destaque_no_site: destaque, icone: "Box",
  descricao_publica: `Texto de ${nome}.`, ...extra,
});

/** 9 products: 2 disponível, 1 em breve, 6 lista de espera. */
const CATALOG: CatalogProduct[] = [
  p("agents", "Agentes", "disponivel", 2, { url: "https://agents.example" }),
  p("sw", "Social Wiring", "disponivel", 1, { url: "https://sw.example" }),
  p("commerce", "Commerce", "em_breve", 3),
  p("erp", "ERP", "lista_de_espera"),
  p("igig", "IgIg", "lista_de_espera"),
  p("orbity", "Orbity", "lista_de_espera", null, { descricao_publica: null }),
  p("store", "Store", "lista_de_espera"),
  p("daily", "Daily Life", "lista_de_espera"),
  p("therapy", "Plataforma de Terapia", "lista_de_espera"),
];

const names = () => screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);

describe("selectFeaturedProducts", () => {
  it("orders featured by destaque_no_site and ignores the rest", () => {
    expect(selectFeaturedProducts(CATALOG).map((x) => x.slug)).toEqual(["sw", "agents", "commerce"]);
  });
  it("caps featured at 6", () => {
    const many = Array.from({ length: 9 }, (_, i) => p(`s${i}`, `P${i}`, "disponivel", 9 - i));
    const out = selectFeaturedProducts(many);
    expect(out).toHaveLength(6);
    expect(out[0].slug).toBe("s8");
  });
  it("falls back to the first 6 by status (disponível first) then alphabetical when none featured", () => {
    const none = CATALOG.map((x) => ({ ...x, destaque_no_site: null }));
    expect(selectFeaturedProducts(none).map((x) => x.nome)).toEqual([
      "Agentes", "Social Wiring", "Commerce", "Daily Life", "ERP", "IgIg",
    ]);
  });
});

describe("ProductCatalogGrid", () => {
  it("shows only the featured products collapsed, with N in the toggle and no status filter", () => {
    render(<ProductCatalogGrid products={CATALOG} title="Produtos NoctusAI" />);
    expect(names()).toEqual(["Social Wiring", "Agentes", "Commerce"]);
    expect(screen.getByRole("button", { name: "Ver todos os produtos (9)" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("group", { name: "Filtrar produtos" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("3 de 9 produtos");
  });

  it("expands in place (status order, then name), reveals the filter, and collapses again", async () => {
    const user = userEvent.setup();
    render(<ProductCatalogGrid products={CATALOG} title="Produtos NoctusAI" />);
    await user.click(screen.getByRole("button", { name: "Ver todos os produtos (9)" }));
    expect(names()).toEqual([
      "Agentes", "Social Wiring", "Commerce", "Daily Life", "ERP", "IgIg", "Orbity", "Plataforma de Terapia", "Store",
    ]);
    const toggle = screen.getByRole("button", { name: "Mostrar só os destaques" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const filter = screen.getByRole("group", { name: "Filtrar produtos" });
    // buckets with zero rows are not offered
    expect(within(filter).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Todos (9)", "Disponíveis (2)", "Em breve (1)", "Lista de espera (6)",
    ]);
    await user.click(within(filter).getByRole("button", { name: /Em breve/ }));
    expect(names()).toEqual(["Commerce"]);
    expect(screen.getByRole("status")).toHaveTextContent("1 produto · filtro: Em breve");
    await user.click(toggle);
    expect(names()).toEqual(["Social Wiring", "Agentes", "Commerce"]);
    expect(screen.queryByRole("group", { name: "Filtrar produtos" })).toBeNull();
  });

  it("has no toggle when everything is already shown", () => {
    render(<ProductCatalogGrid products={CATALOG.slice(0, 3)} title="t" />);
    expect(screen.queryByRole("button", { name: /Ver todos/ })).toBeNull();
    expect(names()).toHaveLength(3);
  });

  it.each([
    ["disponivel", "Disponível", "bg-success-light"],
    ["em_breve", "Em breve", "bg-info-light"],
    ["lista_de_espera", "Lista de espera", "bg-warning-light"],
  ] as const)("renders the %s badge as %s with its token colour", (status, label, cls) => {
    render(<ProductCatalogGrid products={[p("x", "X", status, 1, { url: "https://x" })]} title="t" />);
    const badge = screen.getByText(label, { selector: "span" });
    expect(badge).toHaveClass(cls);
  });

  it("renders 'Conhecer' for disponível and the waitlist button for the others, calling onWaitlist(slug)", async () => {
    const user = userEvent.setup();
    const onWaitlist = vi.fn();
    render(<ProductCatalogGrid products={CATALOG.slice(0, 3)} title="t" onWaitlist={onWaitlist} />);
    expect(screen.getByRole("link", { name: "Conhecer o Agentes" })).toHaveAttribute("href", "https://agents.example");
    await user.click(screen.getByRole("button", { name: "Avise-me quando abrir: Commerce" }));
    expect(onWaitlist).toHaveBeenCalledWith("commerce");
  });

  it("shows 'Descrição não informada.' for a null description", async () => {
    const user = userEvent.setup();
    render(<ProductCatalogGrid products={CATALOG} title="t" />);
    await user.click(screen.getByRole("button", { name: /Ver todos/ }));
    expect(screen.getByText("Descrição não informada.")).toBeInTheDocument();
  });

  it("loading: busy region, skeletons, no toggle, announced count", () => {
    const { container } = render(<ProductCatalogGrid products={[]} isLoading title="t" />);
    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Carregando produtos…");
    expect(screen.queryByRole("button", { name: /Ver todos/ })).toBeNull();
  });

  it("empty: says what happens next and offers the form", () => {
    render(<ProductCatalogGrid products={[]} title="t" emptyAction={{ label: "Ir para o formulário", href: "#contato-form" }} />);
    expect(screen.getByRole("heading", { name: "Nenhum produto publicado no momento" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para o formulário" })).toHaveAttribute("href", "#contato-form");
  });

  it("error with stale data: alert above the published list, retry works", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ProductCatalogGrid products={CATALOG.slice(0, 3)} isError onRetry={onRetry} title="t" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível atualizar a lista agora.");
    expect(alert).toHaveTextContent("versão publicada");
    expect(names()).toHaveLength(3);
    await user.click(within(alert).getByRole("button", { name: "Tentar de novo" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("server-renders visible content (no opacity:0)", () => {
    const html = renderToString(<ProductCatalogGrid products={CATALOG} title="Produtos NoctusAI" />);
    expect(html).toContain("Social Wiring");
    expect(html).not.toMatch(/opacity:\s*0(?![.\d])/);
  });
});

describe("LeadCaptureForm", () => {
  const setup = (props: Partial<React.ComponentProps<typeof LeadCaptureForm>> = {}) => {
    const onSubmit = vi.fn<(v: LeadFormValues) => Promise<void>>().mockResolvedValue(undefined);
    const utils = render(
      <LeadCaptureForm variant="brief" title="Conte o que você precisa" heading="Conte sobre o seu projeto"
        onSubmit={onSubmit} turnstileSiteKey="" {...props} />,
    );
    return { onSubmit, ...utils };
  };
  const fill = async (user: ReturnType<typeof userEvent.setup>, o: { nome?: string; wa?: string; email?: string; consent?: boolean } = {}) => {
    if (o.nome !== undefined) await user.type(screen.getByLabelText("Nome *"), o.nome);
    if (o.wa !== undefined) await user.type(screen.getByLabelText("WhatsApp *"), o.wa);
    if (o.email !== undefined) await user.type(screen.getByLabelText("E-mail (opcional)"), o.email);
    if (o.consent) await user.click(screen.getByRole("checkbox"));
  };

  it("refuses an empty submit with the exact pt-BR messages, focuses the first invalid field and never calls onSubmit", async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(screen.getByText("Informe o seu nome.")).toBeInTheDocument();
    expect(screen.getByText("Informe o seu WhatsApp para podermos responder.")).toBeInTheDocument();
    expect(screen.getByText("Marque a autorização de contato para enviar.")).toBeInTheDocument();
    const nome = screen.getByLabelText("Nome *");
    expect(nome).toHaveAttribute("aria-invalid", "true");
    expect(nome).toHaveFocus();
    expect(nome.getAttribute("aria-describedby")).toContain("nome-err");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("validates WhatsApp shape and optional e-mail", async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    await fill(user, { nome: "Ana", wa: "123", email: "nope", consent: true });
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(screen.getByText(LEAD_MESSAGES.whatsappShape)).toBeInTheDocument();
    expect(screen.getByText("Confira o número: DDD + número, ex.: 11 91234-5678.")).toBeInTheDocument();
    expect(screen.getByText("Confira o e-mail (ex.: nome@empresa.com.br) ou deixe em branco.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("requires the contact consent even when everything else is valid", async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    await fill(user, { nome: "Ana", wa: "11 91234-5678" });
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(screen.getByText("Marque a autorização de contato para enviar.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits the digits-only values through onSubmit and shows the thanks state", async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    await fill(user, { nome: "Ana", wa: "(11) 91234-5678", consent: true });
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit.mock.calls[0][0]).toEqual({ nome: "Ana", whatsapp: "11912345678", consentimento: true });
    expect(await screen.findByText("Recebemos a sua mensagem.")).toBeInTheDocument();
  });

  it("keeps what was typed and shows an alert when onSubmit rejects", async () => {
    const user = userEvent.setup();
    const { onSubmit } = setup();
    onSubmit.mockRejectedValueOnce(new Error("boom"));
    await fill(user, { nome: "Ana", wa: "11912345678", consent: true });
    await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível enviar agora.");
    expect(screen.getByLabelText("Nome *")).toHaveValue("Ana");
  });

  describe("Turnstile", () => {
    it("absent site key: renders no widget and sends no token", async () => {
      const user = userEvent.setup();
      const { onSubmit } = setup({ turnstileSiteKey: "" });
      expect(screen.queryByTestId("turnstile-slot")).toBeNull();
      await fill(user, { nome: "Ana", wa: "11912345678", consent: true });
      await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
      expect(onSubmit.mock.calls[0][0]).not.toHaveProperty("turnstileToken");
    });

    it("falls back to VITE_TURNSTILE_SITE_KEY, unset in this env => no widget", () => {
      vi.stubEnv("VITE_TURNSTILE_SITE_KEY", "");
      render(<LeadCaptureForm variant="brief" title="t" heading="h" onSubmit={vi.fn()} />);
      expect(screen.queryByTestId("turnstile-slot")).toBeNull();
      vi.unstubAllEnvs();
    });

    it("site key set: renders the slot and blocks submit until a token exists", async () => {
      const user = userEvent.setup();
      const { onSubmit } = setup({ turnstileSiteKey: "0x4AAA-test" });
      expect(screen.getByTestId("turnstile-slot")).toBeInTheDocument();
      await fill(user, { nome: "Ana", wa: "11912345678", consent: true });
      await user.click(screen.getByRole("button", { name: "Enviar mensagem" }));
      expect(screen.getByText(LEAD_MESSAGES.turnstile)).toBeInTheDocument();
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("waitlist variant", () => {
    const interest = { slug: "commerce", nome: "Commerce" };

    it("shows the interest chip, hides the phase field and submits product_interest", async () => {
      const user = userEvent.setup();
      const { onSubmit } = setup({ variant: "waitlist", interest });
      expect(screen.getByText("Lista de espera")).toBeInTheDocument();
      expect(screen.getByText("Commerce", { selector: "b" })).toBeInTheDocument();
      expect(screen.queryByLabelText("Em que fase está o projeto?")).toBeNull();
      expect(screen.getByRole("heading", { name: "Entrar na lista de espera" })).toBeInTheDocument();
      await fill(user, { nome: "Ana", wa: "11912345678", consent: true });
      await user.click(screen.getByRole("button", { name: "Entrar na lista" }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
      expect(onSubmit.mock.calls[0][0].product_interest).toEqual(["commerce"]);
      expect(await screen.findByText("Pronto, você está na lista de espera do Commerce.")).toBeInTheDocument();
    });

    it("Remover clears the interest through the callback", async () => {
      const user = userEvent.setup();
      const onInterestClear = vi.fn();
      setup({ variant: "waitlist", interest, onInterestClear });
      await user.click(screen.getByRole("button", { name: /Remover/ }));
      expect(onInterestClear).toHaveBeenCalledOnce();
    });

    it("prefill after mount: focuses Nome and raises an undo toast whose action clears the interest", () => {
      const onInterestClear = vi.fn();
      const onSubmit = vi.fn();
      const { rerender } = render(
        <LeadCaptureForm variant="brief" title="t" heading="h" onSubmit={onSubmit} turnstileSiteKey="" onInterestClear={onInterestClear} />,
      );
      expect(toast).not.toHaveBeenCalled();
      rerender(
        <LeadCaptureForm variant="waitlist" interest={interest} title="t" heading="h" onSubmit={onSubmit} turnstileSiteKey="" onInterestClear={onInterestClear} />,
      );
      expect(screen.getByLabelText("Nome *")).toHaveFocus();
      expect(toast).toHaveBeenCalledTimes(1);
      const [msg, opts] = vi.mocked(toast).mock.calls[0] as [string, { action: { label: string; onClick: () => void } }];
      expect(msg).toBe("Commerce foi colocado no formulário.");
      expect(opts.action.label).toBe("Desfazer");
      opts.action.onClick();
      expect(onInterestClear).toHaveBeenCalledOnce();
    });

    it("does not toast for an interest present at first render", () => {
      setup({ variant: "waitlist", interest });
      expect(toast).not.toHaveBeenCalled();
    });
  });
});

describe("LandingNav keyboard", () => {
  const renderNav = () =>
    render(
      <LandingNav
        brand={{ label: "NoctusAI", href: "#top" }}
        links={[{ label: "Preços", href: "#precos" }]}
        products={[{ nome: "Agentes", href: "https://agents.example", descricao: "Agentes de IA", icone: "Bot" }]}
        allProductsHref="#produtos"
        primaryAction={{ label: "Criar conta grátis", href: "#criar-conta" }}
        loginAction={{ label: "Entrar", href: "/login" }}
      />,
    );

  it("products disclosure: button toggles aria-expanded and the hidden attribute, Escape closes and returns focus", async () => {
    const user = userEvent.setup();
    const { container } = renderNav();
    const btn = screen.getByRole("button", { name: "Produtos" });
    const panel = container.querySelector(`#${CSS.escape(btn.getAttribute("aria-controls")!)}`)!;
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(panel).toHaveAttribute("hidden");
    btn.focus();
    await user.keyboard("{Enter}");
    expect(btn).toHaveAttribute("aria-expanded", "true");
    expect(panel).not.toHaveAttribute("hidden");
    expect(within(panel as HTMLElement).getByRole("link", { name: /Agentes/ })).toHaveAttribute("href", "https://agents.example");
    await user.tab();
    expect(within(panel as HTMLElement).getByRole("link", { name: /Agentes/ })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(btn).toHaveAttribute("aria-expanded", "false");
    expect(panel).toHaveAttribute("hidden");
    expect(btn).toHaveFocus();
  });

  it("products disclosure closes on an outside click and on choosing a link", async () => {
    const user = userEvent.setup();
    renderNav();
    const btn = screen.getByRole("button", { name: "Produtos" });
    await user.click(btn);
    await user.click(document.body);
    expect(btn).toHaveAttribute("aria-expanded", "false");
    await user.click(btn);
    await user.click(screen.getByRole("link", { name: /Ver todos os produtos/ }));
    expect(btn).toHaveAttribute("aria-expanded", "false");
  });

  it("drawer: menu button flips label/aria-expanded, Escape closes and refocuses it, links close it", async () => {
    const user = userEvent.setup();
    const { container } = renderNav();
    const menu = screen.getByRole("button", { name: "Abrir menu" });
    const drawer = container.querySelector(`#${CSS.escape(menu.getAttribute("aria-controls")!)}`)!;
    expect(drawer).toHaveAttribute("hidden");
    await user.click(menu);
    expect(screen.getByRole("button", { name: "Fechar menu" })).toHaveAttribute("aria-expanded", "true");
    expect(drawer).not.toHaveAttribute("hidden");
    await user.keyboard("{Escape}");
    const reopened = screen.getByRole("button", { name: "Abrir menu" });
    expect(reopened).toHaveAttribute("aria-expanded", "false");
    expect(drawer).toHaveAttribute("hidden");
    expect(reopened).toHaveFocus();
    await user.click(reopened);
    await user.click(within(drawer as HTMLElement).getByRole("link", { name: "Preços" }));
    expect(drawer).toHaveAttribute("hidden");
  });

  it("has no breadcrumb", () => {
    renderNav();
    expect(screen.queryByRole("navigation", { name: /breadcrumb|trilha/i })).toBeNull();
  });
});

describe("remaining organs", () => {
  it("Hero: h1 with emphasis, actions, chips and an accessible media slot; no chips list when empty", () => {
    const { rerender } = render(
      <Hero title="IA que trabalha" titleEmphasis="pronta ou sob medida." lede="Lede." eyebrow="NoctusAI"
        actions={[{ label: "Criar conta grátis", href: "#c", variant: "primary" }, { label: "Ver os produtos", href: "#p" }]}
        chips={[{ label: "Agentes", href: "#p", icone: "Bot" }]} media={<svg />} mediaLabel="Ilustração" />,
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("IA que trabalha pronta ou sob medida.");
    expect(screen.getByRole("link", { name: "Criar conta grátis" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Produtos disponíveis" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ilustração" })).toBeInTheDocument();
    rerender(<Hero title="t" lede="l" actions={[]} chips={[]} />);
    expect(screen.queryByRole("list", { name: "Produtos disponíveis" })).toBeNull();
  });

  it("FeatureGrid and Steps render labelled sections; Steps is an ordered list numbered 01..", () => {
    render(
      <>
        <FeatureGrid title="Escolha por onde começar" items={[{ title: "Autônomos", description: "d", icon: "User", cta: { label: "Ver os preços", href: "#precos" } }]} />
        <Steps title="Um projeto" steps={[{ title: "Diagnóstico", description: "a" }, { title: "Protótipo", description: "b" }]} />
      </>,
    );
    expect(screen.getByRole("region", { name: "Escolha por onde começar" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ver os preços/ })).toHaveAttribute("href", "#precos");
    const steps = within(screen.getByRole("region", { name: "Um projeto" }));
    expect(steps.getAllByRole("listitem")).toHaveLength(2);
    expect(steps.getByText("01")).toBeInTheDocument();
  });

  it("CtaBand, Faq and LandingFooter", async () => {
    const user = userEvent.setup();
    const onCookies = vi.fn();
    render(
      <>
        <CtaBand title="Comece" actions={[{ label: "Criar conta grátis", href: "#c", variant: "primary" }]} />
        <Faq title="Perguntas frequentes" items={[{ question: "Quanto custa?", answer: "Depende." }]} />
        <LandingFooter brand={<a href="#top">NoctusAI</a>} copyright="© 2026 NoctusAI."
          columns={[{ heading: "Legal", links: [{ label: "Política de Privacidade", href: "/p" }, { label: "Preferências de cookies", onClick: onCookies }] }]} />
      </>,
    );
    expect(screen.getByRole("region", { name: "Comece" })).toBeInTheDocument();
    const q = screen.getByText("Quanto custa?");
    expect(q.closest("details")).not.toHaveAttribute("open");
    await user.click(q);
    expect(q.closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("navigation", { name: "Legal" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Preferências de cookies" }));
    expect(onCookies).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Política de Privacidade" })).toHaveAttribute("href", "/p");
  });
});
