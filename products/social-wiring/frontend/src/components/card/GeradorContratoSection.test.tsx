/**
 * GeradorContratoSection — the "Gerar contrato" readiness + action panel.
 *
 * Presentational: every assertion here drives the component with plain
 * props, no query client. Coverage: the pronto/faltam badges, `faltando`
 * grouped by `onde` with pt-BR headers, `bloqueios`/`avisos` rendered
 * distinctly, the button disabled until `pronto`, a 400 `details` surfaced,
 * and the post-`201` `avisos`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import GeradorContratoSection, { type FaltandoComDestino } from "./GeradorContratoSection";
import { ContratoGeracaoError, type ContratoGeracaoStatus } from "@/hooks/useContratos";

// `faltando` widened to `FaltandoComDestino`: the runtime payload carries
// `destino` on every item (`derivacao.py:100-193`) even though `useContratos`'
// own `GeracaoFaltando` doesn't declare it yet (out of scope for this slice).
type StatusOver = Omit<Partial<ContratoGeracaoStatus>, "faltando"> & {
  faltando?: FaltandoComDestino[];
};

function status(over: StatusOver = {}): ContratoGeracaoStatus {
  return {
    contrato_id: "c1",
    pronto: true,
    modelo_derivado: "compra_venda",
    modelo_confere: true,
    modelo_automatico: false,
    processo_legado: false,
    switches: {},
    faltando: [],
    bloqueios: [],
    avisos: [],
    ...over,
  } as ContratoGeracaoStatus;
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    status: status(),
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    onRetry: vi.fn(),
    assinaturaData: "2026-09-14",
    onAssinaturaDataChange: vi.fn(),
    gerando: false,
    onGerar: vi.fn(),
    erroGeracao: null,
    avisosGerados: null,
    ...over,
  };
}

// 🔴 `screen`, NOT the render result's bound queries: `{...view, ...rtl}`
// lets the module namespace's UNBOUND `getByTestId(container, id)` (2-3
// args) win over the render result's BOUND one-arg version, same footgun
// `ContratosPanel.test.tsx` sidesteps by only ever calling `screen.<query>`.
//
// Wrapped in `MemoryRouter`: `FaltandoLinha` renders a real `<Link>` for a
// routable `destino`, same requirement as `ImovelContratoCard.test.tsx`.
async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const { MemoryRouter } = await import("react-router-dom");
  const props = baseProps(over);
  rtl.render(
    <MemoryRouter>
      <GeradorContratoSection {...(props as unknown as Parameters<typeof GeradorContratoSection>[0])} />
    </MemoryRouter>,
  );
  return { ...rtl, props };
}

/** A `destino` shaped exactly like `Destinos.para` (`derivacao.py:100-193`). */
function destino(over: Record<string, unknown> = {}) {
  return {
    tela: "certidoes",
    rota: "/certidoes",
    ancora: null,
    ids: {},
    ...over,
  };
}

describe("GeradorContratoSection", () => {
  it("shows the skeleton while the readiness check is loading", async () => {
    const { screen } = await render({ status: undefined, showSkeleton: true });
    expect(screen.getByTestId("gerador-contrato-skeleton")).toBeTruthy();
  });

  it("shows an error with a retry when the readiness check fails", async () => {
    const onRetry = vi.fn();
    const { screen, fireEvent } = await render({ status: undefined, isError: true, onRetry });
    expect(screen.getByTestId("gerador-contrato-erro")).toBeTruthy();
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("🔴 'Pronto para gerar' badge, and the Gerar button is enabled", async () => {
    const { screen } = await render({ status: status({ pronto: true }) });
    expect(screen.getByTestId("gerador-contrato-pronto")).toBeTruthy();
    expect(screen.queryByTestId("gerador-contrato-faltam")).toBeNull();
    const btn = screen.getByTestId("gerador-contrato-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("🔴 'Faltam dados' badge, and the Gerar button is disabled", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          { campo: "cpf", rotulo: "CPF do comprador", onde: "partes", parte_id: "p1" },
        ],
      }),
    });
    expect(screen.getByTestId("gerador-contrato-faltam")).toBeTruthy();
    expect(screen.queryByTestId("gerador-contrato-pronto")).toBeNull();
    const btn = screen.getByTestId("gerador-contrato-btn") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("🔴 groups `faltando` by `onde` with pt-BR headers", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "cpf",
            rotulo: "CPF do comprador",
            onde: "partes",
            parte_id: "p1",
            destino: destino({ tela: "card_partes", rota: "/clientes", ancora: "geral" }),
          },
          {
            campo: "rg",
            rotulo: "RG do comprador",
            onde: "partes",
            parte_id: "p1",
            destino: destino({ tela: "card_partes", rota: "/clientes", ancora: "geral" }),
          },
          {
            campo: "matricula",
            rotulo: "Matrícula transcrita",
            onde: "matricula",
            parte_id: null,
            destino: destino({ tela: "matriculas", rota: "/matriculas" }),
          },
        ],
      }),
    });
    const bloco = screen.getByTestId("gerador-contrato-faltando");
    expect(bloco.textContent).toContain("Partes envolvidas");
    expect(bloco.textContent).toContain("CPF do comprador");
    expect(bloco.textContent).toContain("RG do comprador");
    expect(bloco.textContent).toContain("Matrícula");
    expect(bloco.textContent).toContain("Matrícula transcrita");
    expect(screen.getAllByText("CPF do comprador")).toHaveLength(1);
  });

  it("🔴 a routable destino renders an actionable link pointing at its route", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "matricula",
            rotulo: "Matrícula transcrita",
            onde: "matricula",
            parte_id: null,
            destino: destino({ tela: "matriculas", rota: "/matriculas", ancora: null }),
          },
        ],
      }),
    });
    const link = screen.getByTestId(
      "gerador-contrato-faltando-link-matricula-",
    ) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas");
    expect(
      screen.queryByTestId("gerador-contrato-faltando-guidance-matricula-"),
    ).toBeNull();
  });

  it("🔴 a routable destino with an anchor names the settings tab as a caption, never a query param", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "razao_social",
            rotulo: "Razão social da imobiliária",
            onde: "imobiliaria",
            parte_id: null,
            destino: destino({
              tela: "configuracoes",
              rota: "/configuracoes",
              ancora: "imobiliaria",
            }),
          },
        ],
      }),
    });
    const link = screen.getByTestId(
      "gerador-contrato-faltando-link-razao_social-",
    ) as HTMLAnchorElement;
    // The route itself, no fabricated `?tab=`/`#` the Settings page doesn't
    // read yet — the tab name is a plain-text caption next to the link.
    expect(link.getAttribute("href")).toBe("/configuracoes");
    expect(link.getAttribute("href")).not.toContain("?");
    expect(link.getAttribute("href")).not.toContain("#");
    expect(screen.getByTestId("gerador-contrato-faltando").textContent).toContain(
      "(aba Imobiliária)",
    );
  });

  it("🔴 a card-scoped destino renders guidance naming the subpage, never a fabricated deep link", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "cpf",
            rotulo: "CPF do comprador",
            onde: "partes",
            parte_id: "p1",
            destino: destino({
              tela: "card_partes",
              rota: "/clientes",
              ancora: "geral",
              ids: { cliente_id: "cli1", parte_id: "p1" },
            }),
          },
        ],
      }),
    });
    const guidance = screen.getByTestId("gerador-contrato-faltando-guidance-cpf-p1");
    expect(guidance.textContent).toContain("CPF do comprador");
    expect(guidance.textContent).toContain("Geral");
    // No `<a>`/`<Link>` at all for a card destino — `/clientes` alone is not
    // a deep link into the card's `geral` subpage, so nothing renders as one.
    expect(guidance.querySelector("a")).toBeNull();
    expect(
      screen.queryByTestId("gerador-contrato-faltando-link-cpf-p1"),
    ).toBeNull();
  });

  it("🔴 inside the card, a card-scoped 'Resolver' jumps to the subpage + control (onIrPara)", async () => {
    const onIrPara = vi.fn();
    const alvo = destino({
      tela: "card_negociacao",
      rota: "/clientes",
      ancora: "negociacao",
      alvo: "termos-itens-integrantes-resposta",
      ids: { cliente_id: "cli1" },
    });
    const { screen, fireEvent } = await render({
      onIrPara,
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "negociacao.itens_integrantes",
            rotulo: "Itens integrantes (relacione-os, ou confirme que não há nenhum)",
            onde: "negociacao",
            parte_id: null,
            destino: alvo,
          },
        ],
      }),
    });
    const botao = screen.getByTestId(
      "gerador-contrato-faltando-ir-negociacao.itens_integrantes-",
    );
    // A button, not a fabricated link — the card owns its subpage in state.
    expect(botao.tagName).toBe("BUTTON");
    fireEvent.click(botao);
    expect(onIrPara).toHaveBeenCalledWith(alvo);
  });

  it("🔴 a routable destino naming an `alvo` links to the route + #alvo (foro → imóvel documents)", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "negociacao.foro_comarca",
            rotulo: "Comarca do cartório da matrícula",
            onde: "matricula",
            parte_id: null,
            destino: destino({
              tela: "imovel",
              rota: "/imoveis/IM-1",
              ancora: null,
              alvo: "imovel-documentos",
              ids: { imovel_codigo: "IM-1" },
            }),
          },
        ],
      }),
    });
    const link = screen.getByTestId(
      "gerador-contrato-faltando-link-negociacao.foro_comarca-",
    ) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/imoveis/IM-1#imovel-documentos");
  });

  it("🔴 a `faltando` item's `sugestoes` render as 'Envie X em Y' hints, with a routable destino as a link", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "matricula",
            rotulo: "Matrícula transcrita",
            onde: "matricula",
            parte_id: null,
            sugestoes: [
              {
                tipo_documento: "Matrícula",
                rotulo: "Extrator de matrículas",
                destino: destino({ tela: "matriculas", rota: "/matriculas" }),
              },
            ],
          },
        ],
      }),
    });
    const sugestoes = screen.getByTestId("gerador-contrato-faltando-sugestoes-matricula-");
    expect(sugestoes.textContent).toContain("Envie Matrícula");
    const link = screen.getByTestId(
      "gerador-contrato-faltando-sugestao-link-matricula--0",
    ) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas");
  });

  // 🔴 Prod crash (2026-09-25): `sugestoes[].destino` is `derivacao.py`'s
  // rich `Destinos.para` OBJECT (`Avaliacao.falta` injects the faltando's
  // own `destino` into every suggestion verbatim), never the narrower
  // plain-string shape `ProvenienciaFontePossivel.destino` uses. Rendering
  // it through `cardSubpages.resolverDestino` (which assumed a string and
  // called `.startsWith` on it) unmounted the whole app the first time a
  // suggestion carried one. These tests pin the fix.
  it("🔴 a sugestão with a card-scoped RICH destino object renders guidance, never a fabricated link, and never crashes (2026-09-25)", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "certidao",
            rotulo: "Certidão de casamento",
            onde: "certidoes",
            parte_id: "p1",
            sugestoes: [
              {
                tipo_documento: "Certidão de casamento",
                rotulo: "Certidão",
                destino: destino({ tela: "card_contratos", rota: "/clientes", ancora: "contratos" }),
              },
            ],
          },
        ],
      }),
    });
    const sugestoes = screen.getByTestId("gerador-contrato-faltando-sugestoes-certidao-p1");
    expect(sugestoes.querySelector("a")).toBeNull();
    expect(sugestoes.textContent).toContain("Contratos");
  });

  it("🔴 a sugestão with a routable RICH destino object renders and links correctly (2026-09-25 crash)", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "matricula",
            rotulo: "Matrícula transcrita",
            onde: "matricula",
            parte_id: null,
            sugestoes: [
              {
                tipo_documento: "Matrícula",
                rotulo: "Extrator de matrículas",
                destino: destino({ tela: "matriculas", rota: "/matriculas", ancora: null }),
              },
            ],
          },
        ],
      }),
    });
    const link = screen.getByTestId(
      "gerador-contrato-faltando-sugestao-link-matricula--0",
    ) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/matriculas");
  });

  it("🔴 inside the card, a card-scoped sugestão's 'Resolver' jumps the subpage via onIrPara (2026-09-25)", async () => {
    const onIrPara = vi.fn();
    const alvoSugestao = destino({ tela: "card_contratos", rota: "/clientes", ancora: "contratos" });
    const { screen, fireEvent } = await render({
      onIrPara,
      status: status({
        pronto: false,
        faltando: [
          {
            campo: "certidao",
            rotulo: "Certidão de casamento",
            onde: "certidoes",
            parte_id: "p1",
            sugestoes: [
              { tipo_documento: "Certidão de casamento", rotulo: "Certidão", destino: alvoSugestao },
            ],
          },
        ],
      }),
    });
    const botao = screen.getByTestId("gerador-contrato-faltando-sugestao-ir-certidao-p1-0");
    expect(botao.tagName).toBe("BUTTON");
    fireEvent.click(botao);
    expect(onIrPara).toHaveBeenCalledWith(alvoSugestao);
  });

  it("omits the sugestões block entirely when the item carries none", async () => {
    const { screen } = await render({
      status: status({
        pronto: false,
        faltando: [{ campo: "cpf", rotulo: "CPF do comprador", onde: "partes", parte_id: "p1" }],
      }),
    });
    expect(screen.queryByTestId("gerador-contrato-faltando-sugestoes-cpf-p1")).toBeNull();
  });

  it("🔴 `bloqueios` render as errors, distinct from `avisos` as warnings", async () => {
    const { screen } = await render({
      status: status({
        bloqueios: [{ codigo: "sem_testemunha", mensagem: "Falta uma testemunha." }],
        avisos: [{ codigo: "prazo_padrao", mensagem: "Usando prazo padrão do escritório." }],
      }),
    });
    expect(screen.getByTestId("gerador-contrato-bloqueios").textContent).toContain(
      "Falta uma testemunha.",
    );
    expect(screen.getByTestId("gerador-contrato-avisos").textContent).toContain(
      "Usando prazo padrão do escritório.",
    );
  });

  it("flags when the derived model disagrees with the contract's own model", async () => {
    const { screen } = await render({
      status: status({ modelo_derivado: "compra_venda_a_vista", modelo_confere: false }),
    });
    expect(screen.getByTestId("gerador-contrato-modelo-diverge").textContent).toContain(
      "Compra e venda à vista",
    );
  });

  it("a generated contract says its model will follow the data instead of warning", async () => {
    const { screen } = await render({
      status: status({
        modelo_derivado: "compra_venda",
        modelo_confere: false,
        modelo_automatico: true,
      }),
    });
    expect(screen.queryByTestId("gerador-contrato-modelo-diverge")).toBeNull();
    expect(screen.getByTestId("gerador-contrato-modelo-atualiza").textContent).toContain(
      "Compra e venda",
    );
  });

  it("does not flag when the derived model matches", async () => {
    const { screen } = await render({ status: status({ modelo_confere: true }) });
    expect(screen.queryByTestId("gerador-contrato-modelo-diverge")).toBeNull();
  });

  it("clicking 'Gerar versão' fires onGerar when pronto", async () => {
    const onGerar = vi.fn();
    const { screen, fireEvent } = await render({ status: status({ pronto: true }), onGerar });
    fireEvent.click(screen.getByTestId("gerador-contrato-btn"));
    expect(onGerar).toHaveBeenCalledTimes(1);
  });

  it("🔴 a 400 CONTRATO_INCOMPLETO surfaces its details.faltando and details.bloqueios", async () => {
    const erro = new ContratoGeracaoError("CONTRATO_INCOMPLETO", "Contrato incompleto.", {
      faltando: [{ campo: "cpf", rotulo: "CPF do comprador", onde: "partes", parte_id: "p1" }],
      bloqueios: [{ codigo: "sem_testemunha", mensagem: "Falta uma testemunha." }],
    });
    const { screen } = await render({ erroGeracao: erro });
    const bloco = screen.getByTestId("gerador-contrato-erro-incompleto");
    expect(bloco.textContent).toContain("Contrato incompleto.");
    expect(bloco.textContent).toContain("CPF do comprador");
    expect(bloco.textContent).toContain("Falta uma testemunha.");
  });

  it("🔴 a 422 CONTRATO_LINT surfaces each finding from details.lint", async () => {
    const erro = new ContratoGeracaoError(
      "CONTRATO_LINT",
      "O texto gerado não passou na verificação final.",
      { lint: [{ codigo: "REFERENCIA_CLAUSULA", mensagem: "A Cláusula Sétima citada não existe." }] },
    );
    const { screen } = await render({ erroGeracao: erro });
    expect(screen.getByText("O texto gerado não passou na verificação final.")).toBeTruthy();
    expect(screen.getByText(/A Cláusula Sétima citada não existe\./)).toBeTruthy();
  });

  it("shows the avisos returned by a successful 201 generation", async () => {
    const { screen } = await render({
      avisosGerados: ["Cláusula de foro padrão aplicada."],
    });
    expect(screen.getByTestId("gerador-contrato-avisos-pos-geracao").textContent).toContain(
      "Cláusula de foro padrão aplicada.",
    );
  });

  it("the assinatura_data input reflects and edits the caller's draft", async () => {
    const onAssinaturaDataChange = vi.fn();
    const { screen, fireEvent } = await render({
      assinaturaData: "2026-09-14",
      onAssinaturaDataChange,
    });
    const input = screen.getByTestId("gerador-contrato-data") as HTMLInputElement;
    expect(input.value).toBe("2026-09-14");
    fireEvent.change(input, { target: { value: "2026-09-20" } });
    expect(onAssinaturaDataChange).toHaveBeenCalledWith("2026-09-20");
  });
});
