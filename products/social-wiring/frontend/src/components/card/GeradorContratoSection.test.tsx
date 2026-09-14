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

import GeradorContratoSection from "./GeradorContratoSection";
import { ContratoGeracaoError, type ContratoGeracaoStatus } from "@/hooks/useContratos";

function status(over: Partial<ContratoGeracaoStatus> = {}): ContratoGeracaoStatus {
  return {
    contrato_id: "c1",
    pronto: true,
    modelo_derivado: "compra_venda",
    modelo_confere: true,
    switches: {},
    faltando: [],
    bloqueios: [],
    avisos: [],
    ...over,
  };
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
async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const props = baseProps(over);
  rtl.render(
    <GeradorContratoSection {...(props as unknown as Parameters<typeof GeradorContratoSection>[0])} />,
  );
  return { ...rtl, props };
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
          { campo: "cpf", rotulo: "CPF do comprador", onde: "partes", parte_id: "p1" },
          { campo: "rg", rotulo: "RG do comprador", onde: "partes", parte_id: "p1" },
          { campo: "matricula", rotulo: "Matrícula transcrita", onde: "matricula", parte_id: null },
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
