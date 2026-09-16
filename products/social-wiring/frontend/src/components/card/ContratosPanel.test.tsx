/**
 * ContratosPanel — the card's legal-paperwork subpage.
 *
 * Assertions worth having: the empty state names both upload AND
 * auto-generation, a status change PATCHes `status` alone (never bundling
 * título/modelo), a delete always asks why, and a "Gerado automaticamente"
 * card never gets confused with an uploaded one.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// The real `Select` is a Radix popover (pointer-capture + portal) that jsdom
// does not model faithfully — the codebase's own convention (`Contatos.test.tsx`)
// is to mock the module rather than fight the popover. This variant renders
// every `SelectItem` inline (no open/close step) so a click reaches
// `onValueChange` directly.
vi.mock("@/components/ui/select", async () => {
  const React = await import("react");
  const Ctx = React.createContext<{ onValueChange?: (v: string) => void }>({});
  return {
    Select: ({ value, onValueChange, disabled, children }: any) =>
      React.createElement(
        Ctx.Provider,
        { value: { onValueChange } },
        React.createElement("div", { "data-disabled": disabled, "data-value": value }, children),
      ),
    SelectTrigger: ({ children, ...rest }: any) =>
      React.createElement("div", { role: "combobox", ...rest }, children),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => React.createElement("div", null, children),
    SelectItem: ({ value, children }: any) => {
      const ctx = React.useContext(Ctx);
      return React.createElement(
        "button",
        { type: "button", onClick: () => ctx.onValueChange?.(value) },
        children,
      );
    },
  };
});

import ContratosPanel from "./ContratosPanel";
import type { ContratoOut, VersaoOut } from "@/hooks/useContratos";

function versao(over: Partial<VersaoOut> = {}): VersaoOut {
  return {
    id: "v1",
    nome_original: "contrato.pdf",
    mime_type: "application/pdf",
    tamanho_bytes: 1024 * 1024,
    tipo_documento: "contrato",
    enviado_por: { id: "u1", nome: "Ana Corretora" },
    created_at: "2026-02-01T00:00:00+00:00",
    numero: 1,
    rotulo: null,
    origem: "upload",
    ...over,
  };
}

function contrato(over: Partial<ContratoOut> = {}): ContratoOut {
  const v = over.versao_atual !== undefined ? over.versao_atual : versao();
  return {
    id: "c1",
    atendimento_id: "a1",
    titulo: "Contrato de compra e venda",
    modelo: "compra_venda",
    status: "rascunho",
    status_em: null,
    status_por: null,
    origem: "upload",
    created_at: "2026-02-01T00:00:00+00:00",
    updated_at: "2026-02-01T00:00:00+00:00",
    versao_atual: v,
    versoes: v ? [v] : [],
    assinatura_data: null,
    prazo_pendencias_dias: null,
    ...over,
  };
}

function baseProps(over: Record<string, unknown> = {}) {
  return {
    contratos: [],
    showSkeleton: false,
    isRefreshing: false,
    isError: false,
    errorMessage: null,
    onRetry: vi.fn(),
    onNovoContrato: vi.fn(),
    onAddVersao: vi.fn(),
    onPatchStatus: vi.fn(),
    onPatchPrazos: vi.fn(),
    onDeleteVersao: vi.fn(),
    onDeleteContrato: vi.fn(),
    onOpen: vi.fn(),
    onDownload: vi.fn(),
    ...over,
  };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const props = baseProps(over);
  const view = rtl.render(
    <ContratosPanel {...(props as unknown as Parameters<typeof ContratosPanel>[0])} />,
  );
  return { ...view, ...rtl, props };
}

describe("ContratosPanel", () => {
  it("names both upload AND auto-generation in the empty state", async () => {
    const { screen } = await render({ contratos: [] });
    const empty = screen.getByTestId("contratos-vazio");
    expect(empty.textContent).toContain("Nenhum contrato");
    expect(empty.textContent).toContain("gerados automaticamente");
  });

  it("renders the list with título, modelo and the current version", async () => {
    const { screen } = await render({
      contratos: [contrato({ titulo: "Contrato ONE9" })],
    });
    expect(screen.getByText("Contrato ONE9")).toBeTruthy();
    expect(screen.getByText("Compra e venda")).toBeTruthy();
    expect(screen.getByTestId("contrato-abrir-c1")).toBeTruthy();
    expect(screen.getByTestId("contrato-baixar-c1")).toBeTruthy();
  });

  it("🔴 a 'gerado' contract shows the badge", async () => {
    const { screen } = await render({ contratos: [contrato({ origem: "gerado" })] });
    expect(screen.getByTestId("contrato-gerado-c1").textContent).toContain(
      "Gerado automaticamente",
    );
  });

  it("🔴 an uploaded contract does NOT show the badge", async () => {
    const { screen } = await render({ contratos: [contrato({ origem: "upload" })] });
    expect(screen.queryByTestId("contrato-gerado-c1")).toBeNull();
  });

  it("shows the skeleton, not the empty state, while first loading", async () => {
    const { screen } = await render({ contratos: undefined, showSkeleton: true });
    expect(screen.getByTestId("contratos-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("contratos-vazio")).toBeNull();
  });

  it("🔴 an error surfaces inline with a retry — never swallowed", async () => {
    const onRetry = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: undefined,
      isError: true,
      errorMessage: "Não foi possível carregar.",
      onRetry,
    });
    const erro = screen.getByTestId("contratos-erro");
    expect(erro.textContent).toContain("Não foi possível carregar.");
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("clicking 'Novo contrato' only calls the callback — no dialog rendered here", async () => {
    const onNovoContrato = vi.fn();
    const { screen, fireEvent } = await render({ onNovoContrato });
    fireEvent.click(screen.getByTestId("contrato-novo-btn"));
    expect(onNovoContrato).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("novo-contrato-dialog")).toBeNull();
  });

  it("🔴 a status change PATCHes status ALONE — never título/modelo alongside it", async () => {
    const onPatchStatus = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onPatchStatus,
    });
    fireEvent.click(screen.getByText("Assinado"));
    expect(onPatchStatus).toHaveBeenCalledWith("c1", "assinado");
    expect(onPatchStatus).toHaveBeenCalledTimes(1);
  });

  it("🔴 deleting a contract asks why — cancel/blank never calls back", async () => {
    const onDeleteContrato = vi.fn();
    const promptSpy = vi.spyOn(window, "prompt");
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onDeleteContrato,
    });

    promptSpy.mockReturnValueOnce(null);
    fireEvent.click(screen.getByTestId("contrato-excluir-c1"));
    expect(onDeleteContrato).not.toHaveBeenCalled();

    promptSpy.mockReturnValueOnce("   ");
    fireEvent.click(screen.getByTestId("contrato-excluir-c1"));
    expect(onDeleteContrato).not.toHaveBeenCalled();

    promptSpy.mockReturnValueOnce("Contrato cancelado pelo cliente");
    fireEvent.click(screen.getByTestId("contrato-excluir-c1"));
    expect(onDeleteContrato).toHaveBeenCalledWith("c1", "Contrato cancelado pelo cliente");
    promptSpy.mockRestore();
  });

  it("🔴 'Nova versão' rejects an unsupported extension before calling back", async () => {
    const onAddVersao = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onAddVersao,
    });
    const input = screen.getByTestId("contrato-input-c1") as HTMLInputElement;
    const arquivoRuim = new File(["conteudo"], "planilha.xlsx", {
      type: "application/vnd.ms-excel",
    });
    fireEvent.change(input, { target: { files: [arquivoRuim] } });
    expect(onAddVersao).not.toHaveBeenCalled();
    expect(screen.getByTestId("contrato-arquivo-erro-c1").textContent).toContain(
      "Formato não suportado",
    );
  });

  it("🔴 'Nova versão' rejects a file over 25 MB before calling back", async () => {
    const onAddVersao = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onAddVersao,
    });
    const input = screen.getByTestId("contrato-input-c1") as HTMLInputElement;
    const grande = new File(["x"], "contrato.pdf", { type: "application/pdf" });
    Object.defineProperty(grande, "size", { value: 26 * 1024 * 1024 });
    fireEvent.change(input, { target: { files: [grande] } });
    expect(onAddVersao).not.toHaveBeenCalled();
    expect(screen.getByTestId("contrato-arquivo-erro-c1").textContent).toContain(
      "muito grande",
    );
  });

  it("'Nova versão' calls back with a valid file", async () => {
    const onAddVersao = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onAddVersao,
    });
    const input = screen.getByTestId("contrato-input-c1") as HTMLInputElement;
    const bom = new File(["conteudo"], "revisao.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    fireEvent.change(input, { target: { files: [bom] } });
    expect(onAddVersao).toHaveBeenCalledWith("c1", bom);
    expect(screen.queryByTestId("contrato-arquivo-erro-c1")).toBeNull();
  });

  it("expands the version history and lists versions numero DESC", async () => {
    const v1 = versao({ id: "v1", numero: 1, rotulo: "REV 1" });
    const v2 = versao({ id: "v2", numero: 2, rotulo: "REV 2" });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v2, versoes: [v1, v2] })],
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    const linhas = screen.getAllByTestId(/^contrato-versao-v/);
    expect(linhas.map((l) => l.getAttribute("data-testid"))).toEqual([
      "contrato-versao-v2",
      "contrato-versao-v1",
    ]);
  });

  it("🔴 the only version cannot be deleted from the history row", async () => {
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    expect(screen.queryByTestId("contrato-versao-excluir-v1")).toBeNull();
  });

  it("🔴 deleting a version (when more than one exists) asks why", async () => {
    const onDeleteVersao = vi.fn();
    const promptSpy = vi.spyOn(window, "prompt").mockReturnValue("Versão substituída");
    const v1 = versao({ id: "v1", numero: 1 });
    const v2 = versao({ id: "v2", numero: 2 });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v2, versoes: [v1, v2] })],
      onDeleteVersao,
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    fireEvent.click(screen.getByTestId("contrato-versao-excluir-v1"));
    expect(onDeleteVersao).toHaveBeenCalledWith("c1", "v1", "Versão substituída");
    promptSpy.mockRestore();
  });

  it("omits the matrícula section entirely when renderMatriculaAtos is not wired", async () => {
    const { screen } = await render({ contratos: [contrato()] });
    expect(screen.queryByTestId("contrato-matricula-toggle-c1")).toBeNull();
  });

  it("🔴 the matrícula section is a RENDER PROP, not an import — it renders whatever the caller passes, keyed by contratoId", async () => {
    const renderMatriculaAtos = vi.fn((contratoId: string) => (
      <div data-testid="matricula-stub">{contratoId}</div>
    ));
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      renderMatriculaAtos,
    });
    fireEvent.click(screen.getByTestId("contrato-matricula-toggle-c1"));
    expect(renderMatriculaAtos).toHaveBeenCalledWith("c1");
    expect(screen.getByTestId("matricula-stub").textContent).toBe("c1");
  });

  // ─── F5 — "Gerar contrato" render prop ─────────────────────────────────
  it("omits the gerador-contrato section entirely when renderGeradorContrato is not wired", async () => {
    const { screen } = await render({ contratos: [contrato()] });
    expect(screen.queryByTestId("contrato-gerador-toggle-c1")).toBeNull();
  });

  it("🔴 'Gerar contrato' is a RENDER PROP that also carries the open state, so the caller can gate its lazy fetch on it", async () => {
    const renderGeradorContrato = vi.fn((contratoId: string, aberto: boolean) => (
      <div data-testid="gerador-stub">{`${contratoId}:${aberto}`}</div>
    ));
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      renderGeradorContrato,
    });
    // Called on first render too (Radix mounts collapsible content up front) —
    // the caller is the one deciding what "closed" means for its fetch.
    expect(renderGeradorContrato).toHaveBeenCalledWith("c1", false);

    fireEvent.click(screen.getByTestId("contrato-gerador-toggle-c1"));
    expect(renderGeradorContrato).toHaveBeenCalledWith("c1", true);
    expect(screen.getByTestId("gerador-stub").textContent).toBe("c1:true");
  });

  it("🔴 a generated VERSION (not just a generated contract) is marked on the current-version block", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9", origem: "gerado" }) })],
    });
    expect(screen.getByText("Gerado automaticamente")).toBeTruthy();
  });

  it("🔴 a generated VERSION is marked in the history list too", async () => {
    const v1 = versao({ id: "v1", numero: 1, origem: "upload" });
    const v2 = versao({ id: "v2", numero: 2, origem: "gerado" });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v2, versoes: [v1, v2] })],
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    expect(screen.getByTestId("contrato-versao-v2").textContent).toContain(
      "gerado automaticamente",
    );
    expect(screen.getByTestId("contrato-versao-v1").textContent).not.toContain(
      "gerado automaticamente",
    );
  });

  it("clicking Abrir / Baixar calls back with the current version id", async () => {
    const onOpen = vi.fn();
    const onDownload = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9" }) })],
      onOpen,
      onDownload,
    });
    fireEvent.click(screen.getByTestId("contrato-abrir-c1"));
    fireEvent.click(screen.getByTestId("contrato-baixar-c1"));
    expect(onOpen).toHaveBeenCalledWith("c1", "v9");
    expect(onDownload).toHaveBeenCalledWith("c1", "v9");
  });
});

describe("data de assinatura e prazo de pendências (migration 114)", () => {
  it("pré-carrega os valores existentes do contrato", async () => {
    const { screen } = await render({
      contratos: [
        contrato({ assinatura_data: "2026-03-01", prazo_pendencias_dias: 15 }),
      ],
    });
    expect(
      (screen.getByTestId("contrato-assinatura-data-c1") as HTMLInputElement).value,
    ).toBe("2026-03-01");
    expect(
      (screen.getByTestId("contrato-prazo-pendencias-c1") as HTMLInputElement).value,
    ).toBe("15");
  });

  it("o placeholder do prazo nomeia o padrão do escritório quando null", async () => {
    const { screen } = await render({
      contratos: [contrato({ prazo_pendencias_dias: null })],
    });
    expect(
      (screen.getByTestId("contrato-prazo-pendencias-c1") as HTMLInputElement).placeholder,
    ).toContain("10");
  });

  it("🔴 Salvar fica desabilitado até algo mudar, e envia AMBOS os campos juntos", async () => {
    const onPatchPrazos = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ assinatura_data: null, prazo_pendencias_dias: null })],
      onPatchPrazos,
    });
    const salvar = screen.getByTestId("contrato-prazos-salvar-c1");
    expect(salvar).toHaveProperty("disabled", true);

    fireEvent.change(screen.getByTestId("contrato-assinatura-data-c1"), {
      target: { value: "2026-04-10" },
    });
    expect(salvar).toHaveProperty("disabled", false);

    fireEvent.click(salvar);
    expect(onPatchPrazos).toHaveBeenCalledWith("c1", {
      assinatura_data: "2026-04-10",
      prazo_pendencias_dias: null,
    });
  });

  it("🔴 um prazo <= 0 bloqueia o salvar com a mensagem do backend", async () => {
    const onPatchPrazos = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      onPatchPrazos,
    });
    fireEvent.change(screen.getByTestId("contrato-prazo-pendencias-c1"), {
      target: { value: "0" },
    });
    expect(screen.getByTestId("contrato-prazo-erro-c1").textContent).toContain(
      "maior que zero",
    );
    expect(screen.getByTestId("contrato-prazos-salvar-c1")).toHaveProperty(
      "disabled",
      true,
    );
    fireEvent.click(screen.getByTestId("contrato-prazos-salvar-c1"));
    expect(onPatchPrazos).not.toHaveBeenCalled();
  });

  it("string vazia no prazo envia null — restaura o padrão do escritório", async () => {
    const onPatchPrazos = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ prazo_pendencias_dias: 20 })],
      onPatchPrazos,
    });
    fireEvent.change(screen.getByTestId("contrato-prazo-pendencias-c1"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByTestId("contrato-prazos-salvar-c1"));
    expect(onPatchPrazos).toHaveBeenCalledWith(
      "c1",
      expect.objectContaining({ prazo_pendencias_dias: null }),
    );
  });
});
