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
import type { AssinaturaEntry, AssinaturaOut, ContratoOut, VersaoOut } from "@/hooks/useContratos";

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
    docx_disponivel: false,
    modalidade_assinatura: null,
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
    processo_legado: false,
    processo_legado_por: null,
    processo_legado_em: null,
    processo_legado_motivo: null,
    modalidade_assinatura: "digital",
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
    expect(empty.textContent).toContain("Gerar contrato");
    expect(empty.textContent).toContain(".docx ou PDF");
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

  describe("processo anterior à plataforma (migration 151)", () => {
    it("🔴 the amber badge renders for EVERYONE when the flag is set", async () => {
      const { screen } = await render({
        contratos: [contrato({ processo_legado: true })],
        isAdmin: false,
      });
      expect(screen.getByTestId("contrato-processo-legado-badge-c1").textContent).toContain(
        "Processo anterior à plataforma",
      );
    });

    it("the badge does not render when the flag is unset", async () => {
      const { screen } = await render({ contratos: [contrato({ processo_legado: false })] });
      expect(screen.queryByTestId("contrato-processo-legado-badge-c1")).toBeNull();
    });

    it("🔴 the checkbox is hidden for a non-admin", async () => {
      const onSetProcessoLegado = vi.fn();
      const { screen } = await render({
        contratos: [contrato()],
        isAdmin: false,
        onSetProcessoLegado,
      });
      expect(screen.queryByTestId("contrato-processo-legado-checkbox-c1")).toBeNull();
    });

    it("the checkbox is hidden when no handler is wired, even for an admin", async () => {
      const { screen } = await render({ contratos: [contrato()], isAdmin: true });
      expect(screen.queryByTestId("contrato-processo-legado-checkbox-c1")).toBeNull();
    });

    it("checking it as admin opens the dialog — no callback until confirmed", async () => {
      const onSetProcessoLegado = vi.fn();
      const { screen, fireEvent } = await render({
        contratos: [contrato()],
        isAdmin: true,
        onSetProcessoLegado,
      });
      fireEvent.click(screen.getByTestId("contrato-processo-legado-checkbox-c1"));
      expect(screen.getByTestId("processo-legado-dialog")).toBeTruthy();
      expect(onSetProcessoLegado).not.toHaveBeenCalled();
    });

    it("🔴 the dialog requires a 3-char motivo before confirming", async () => {
      const onSetProcessoLegado = vi.fn();
      const { screen, fireEvent } = await render({
        contratos: [contrato()],
        isAdmin: true,
        onSetProcessoLegado,
      });
      fireEvent.click(screen.getByTestId("contrato-processo-legado-checkbox-c1"));
      const confirmar = screen.getByTestId("processo-legado-confirmar") as HTMLButtonElement;
      expect(confirmar.disabled).toBe(true);

      fireEvent.change(screen.getByTestId("processo-legado-motivo"), {
        target: { value: "ok" },
      });
      expect(confirmar.disabled).toBe(true);

      fireEvent.change(screen.getByTestId("processo-legado-motivo"), {
        target: { value: "Deal iniciado antes da plataforma." },
      });
      expect(confirmar.disabled).toBe(false);
      fireEvent.click(confirmar);
      expect(onSetProcessoLegado).toHaveBeenCalledWith(
        "c1",
        true,
        "Deal iniciado antes da plataforma.",
      );
    });

    it("unchecking an active flag calls back directly — no dialog, no motivo", async () => {
      const onSetProcessoLegado = vi.fn();
      const { screen, fireEvent } = await render({
        contratos: [contrato({ processo_legado: true })],
        isAdmin: true,
        onSetProcessoLegado,
      });
      fireEvent.click(screen.getByTestId("contrato-processo-legado-checkbox-c1"));
      expect(onSetProcessoLegado).toHaveBeenCalledWith("c1", false, undefined);
      expect(screen.queryByTestId("processo-legado-dialog")).toBeNull();
    });
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

  // ─── "Gerar contrato" header button ────────────────────────────────────
  it("omits the header 'Gerar contrato' button when onGerarContrato is not wired", async () => {
    const { screen } = await render({ contratos: [] });
    expect(screen.queryByTestId("contrato-gerar-btn")).toBeNull();
  });

  it("the header 'Gerar contrato' button fires onGerarContrato and is disabled while it runs", async () => {
    const onGerarContrato = vi.fn();
    const { screen, fireEvent, rerender, props } = await render({ contratos: [], onGerarContrato });
    fireEvent.click(screen.getByTestId("contrato-gerar-btn"));
    expect(onGerarContrato).toHaveBeenCalledTimes(1);

    rerender(
      <ContratosPanel
        {...({ ...props, iniciandoGeracao: true } as unknown as Parameters<typeof ContratosPanel>[0])}
      />,
    );
    expect((screen.getByTestId("contrato-gerar-btn") as HTMLButtonElement).disabled).toBe(true);
  });

  it("the contract a 'Gerar contrato' click created opens on its generator section", async () => {
    const renderGeradorContrato = vi.fn((contratoId: string, aberto: boolean) => (
      <div data-testid={`gerador-stub-${contratoId}`}>{`${contratoId}:${aberto}`}</div>
    ));
    const semVersao = contrato({ id: "c2", origem: "gerado", versao_atual: null });
    await render({
      contratos: [contrato(), semVersao],
      renderGeradorContrato,
      contratoIniciadoId: "c2",
    });
    expect(renderGeradorContrato).toHaveBeenCalledWith("c2", true);
    expect(renderGeradorContrato).toHaveBeenCalledWith("c1", false);
    expect(renderGeradorContrato).not.toHaveBeenCalledWith("c1", true);
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

  // ─── Proveniência render prop (`sw-extraction-contract`) ──────────────
  it("omits the proveniência section entirely when renderProveniencia is not wired", async () => {
    const { screen } = await render({ contratos: [contrato()] });
    expect(screen.queryByTestId("contrato-proveniencia-toggle-c1")).toBeNull();
  });

  it("🔴 'Proveniência' is a RENDER PROP that also carries the open state, same lazy-fetch discipline as 'Gerar contrato'", async () => {
    const renderProveniencia = vi.fn((contratoId: string, aberto: boolean) => (
      <div data-testid="proveniencia-stub">{`${contratoId}:${aberto}`}</div>
    ));
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      renderProveniencia,
    });
    expect(renderProveniencia).toHaveBeenCalledWith("c1", false);

    fireEvent.click(screen.getByTestId("contrato-proveniencia-toggle-c1"));
    expect(renderProveniencia).toHaveBeenCalledWith("c1", true);
    expect(screen.getByTestId("proveniencia-stub").textContent).toBe("c1:true");
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
    // Third arg (`formato`) is `undefined` for the plain pdf Abrir/Baixar
    // click — only "Baixar .docx" passes `"docx"` explicitly.
    expect(onOpen).toHaveBeenCalledWith("c1", "v9", undefined);
    expect(onDownload).toHaveBeenCalledWith("c1", "v9", undefined);
  });

  it("🔴 every icon-only action on the current-version row has an accessible name", async () => {
    // Before this row went icon-only these buttons had neither text nor
    // aria-label on the history row — invisible to a screen reader and to a
    // keyboard user. `TooltipIconButton` makes the caption and the accessible
    // name the same string by construction; this pins that they are present.
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9", docx_disponivel: true }) })],
    });
    expect(screen.getByTestId("contrato-abrir-c1").getAttribute("aria-label")).toBe("Abrir");
    expect(screen.getByTestId("contrato-baixar-c1").getAttribute("aria-label")).toBe("Baixar PDF");
    expect(screen.getByTestId("contrato-baixar-docx-c1").getAttribute("aria-label")).toBe(
      "Baixar .docx",
    );
  });

  // ─── "Baixar .docx" (migration 120) ────────────────────────────────────
  it("🔴 'Baixar .docx' is hidden on the current-version row without docx_disponivel", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9", docx_disponivel: false }) })],
    });
    expect(screen.queryByTestId("contrato-baixar-docx-c1")).toBeNull();
  });

  it("🔴 'Baixar .docx' shows on the current-version row and calls onDownload with formato: 'docx'", async () => {
    const onDownload = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9", docx_disponivel: true }) })],
      onDownload,
    });
    const botao = screen.getByTestId("contrato-baixar-docx-c1");
    // Icon-only: the caption lives on `aria-label` (and the hover tooltip),
    // never in `textContent`. Asserting the ACCESSIBLE NAME is the stronger
    // check — a screen-reader user and a sighted user must get the same word.
    expect(botao.getAttribute("aria-label")).toBe("Baixar .docx");
    fireEvent.click(botao);
    expect(onDownload).toHaveBeenCalledWith("c1", "v9", "docx");
  });

  it("🔴 'Baixar .docx' shows a pending state while baixandoDocxVersaoId matches this version", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v9", docx_disponivel: true }) })],
      baixandoDocxVersaoId: "v9",
    });
    expect(screen.getByTestId("contrato-baixar-docx-c1")).toHaveProperty("disabled", true);
  });

  it("🔴 the histórico row hides 'Baixar .docx' without docx_disponivel and shows it — calling back with formato: 'docx' — when available", async () => {
    const onDownload = vi.fn();
    const v1 = versao({ id: "v1", numero: 1, docx_disponivel: false });
    const v2 = versao({ id: "v2", numero: 2, docx_disponivel: true });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v2, versoes: [v1, v2] })],
      onDownload,
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    expect(screen.queryByTestId("contrato-versao-baixar-docx-v1")).toBeNull();
    const botao = screen.getByTestId("contrato-versao-baixar-docx-v2");
    fireEvent.click(botao);
    expect(onDownload).toHaveBeenCalledWith("c1", "v2", "docx");
  });

  it("🔴 the histórico row's 'Baixar .docx' is disabled while its own download is pending", async () => {
    const v1 = versao({ id: "v1", numero: 1, docx_disponivel: true });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v1, versoes: [v1] })],
      baixandoDocxVersaoId: "v1",
    });
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    expect(screen.getByTestId("contrato-versao-baixar-docx-v1")).toHaveProperty(
      "disabled",
      true,
    );
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

describe("assinatura digital (signature-integration-CONTRACT §4)", () => {
  function envelope(over: Partial<AssinaturaOut> = {}): AssinaturaOut {
    return {
      assinatura_id: "as1",
      external_id: "ext1",
      link_assinatura: "https://d4sign.example/ext1",
      provedor: "d4sign",
      status: "pendente",
      signatarios: [],
      enviado_em: "2026-09-17T20:00:00Z",
      ...over,
    };
  }

  function entry(over: Partial<AssinaturaEntry> = {}): AssinaturaEntry {
    return { data: null, isPending: false, isFetching: false, isError: false, ...over };
  }

  it("🔴 'Enviar para assinatura' shows ONLY on a gerado current version with no envelope", async () => {
    const onAbrirEnvioAssinatura = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry({ data: null }) },
      onAbrirEnvioAssinatura,
    });
    fireEvent.click(screen.getByTestId("contrato-enviar-assinatura-c1"));
    expect(onAbrirEnvioAssinatura).toHaveBeenCalledWith("c1", "v1");
  });

  it("🔴 hides 'Enviar para assinatura' on an UPLOADED current version", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "upload" }) })],
      assinaturas: { c1: entry({ data: null }) },
      onAbrirEnvioAssinatura: vi.fn(),
    });
    expect(screen.queryByTestId("contrato-enviar-assinatura-c1")).toBeNull();
  });

  it("🔴 hides 'Enviar para assinatura' while a LIVE envelope exists, shows the status block instead", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry({ data: envelope({ status: "pendente" }) }) },
      onAbrirEnvioAssinatura: vi.fn(),
    });
    expect(screen.queryByTestId("contrato-enviar-assinatura-c1")).toBeNull();
    expect(screen.getByTestId("contrato-assinatura-status-c1")).toBeTruthy();
    expect(screen.getByTestId("contrato-assinatura-chip-c1").textContent).toContain("Pendente");
    const link = screen.getByTestId("contrato-abrir-provedor-c1") as HTMLAnchorElement;
    expect(link.textContent).toContain("Abrir no d4sign");
    expect(link.href).toContain("https://d4sign.example/ext1");
  });

  it("🔴 a CANCELLED envelope lets 'Enviar para assinatura' show again (superseded, not permanently blocked)", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry({ data: envelope({ status: "cancelado" }) }) },
      onAbrirEnvioAssinatura: vi.fn(),
    });
    expect(screen.getByTestId("contrato-enviar-assinatura-c1")).toBeTruthy();
    expect(screen.queryByTestId("contrato-assinatura-status-c1")).toBeNull();
  });

  it("🔴 shows nothing while the assinatura status is still unresolved — never guesses from `undefined`", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry({ data: undefined, isPending: true }) },
      onAbrirEnvioAssinatura: vi.fn(),
    });
    expect(screen.queryByTestId("contrato-enviar-assinatura-c1")).toBeNull();
    expect(screen.queryByTestId("contrato-assinatura-status-c1")).toBeNull();
    expect(screen.getByTestId("contrato-assinatura-carregando-c1")).toBeTruthy();
  });

  it("🔴 the status select is DISABLED once ANY envelope exists — even a concluído/cancelado one", async () => {
    const { screen } = await render({
      contratos: [contrato()],
      assinaturas: { c1: entry({ data: envelope({ status: "concluido" }) }) },
    });
    const trigger = screen.getByTestId("contrato-status-c1");
    expect(trigger.parentElement?.getAttribute("data-disabled")).toBe("true");
    expect(screen.getByTestId("contrato-status-assinatura-hint-c1").textContent).toContain(
      "definido pela plataforma de assinatura",
    );
  });

  it("the status select stays ENABLED while there has never been an envelope", async () => {
    const { screen } = await render({
      contratos: [contrato()],
      assinaturas: { c1: entry({ data: null }) },
    });
    const trigger = screen.getByTestId("contrato-status-c1");
    expect(trigger.parentElement?.getAttribute("data-disabled")).toBe("false");
    expect(screen.queryByTestId("contrato-status-assinatura-hint-c1")).toBeNull();
  });

  it("🔴 'Cancelar envio' requires a motivo 3..500 chars before it calls back", async () => {
    const onCancelarAssinatura = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry({ data: envelope({ status: "parcial" }) }) },
      onCancelarAssinatura,
    });
    fireEvent.click(screen.getByTestId("contrato-cancelar-envio-c1"));
    const confirmar = screen.getByTestId("cancelar-envio-confirmar") as HTMLButtonElement;
    expect(confirmar.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("cancelar-envio-motivo"), { target: { value: "ok" } });
    expect(confirmar.disabled).toBe(true);

    fireEvent.change(screen.getByTestId("cancelar-envio-motivo"), {
      target: { value: "Cliente desistiu do negócio" },
    });
    expect(confirmar.disabled).toBe(false);
    fireEvent.click(confirmar);
    expect(onCancelarAssinatura).toHaveBeenCalledWith("c1", "Cliente desistiu do negócio");
  });

  it("🔴 a version with origem 'assinado' shows the Assinado badge, current and historic", async () => {
    const v1 = versao({ id: "v1", numero: 1, origem: "gerado" });
    const v2 = versao({ id: "v2", numero: 2, origem: "assinado" });
    const { screen, fireEvent } = await render({
      contratos: [contrato({ versao_atual: v2, versoes: [v1, v2] })],
    });
    expect(screen.getByTestId("contrato-assinado-c1").textContent).toContain("Assinado");
    fireEvent.click(screen.getByTestId("contrato-historico-toggle-c1"));
    expect(screen.getByTestId("contrato-versao-v2").textContent).toContain("Assinado");
    expect(screen.getByTestId("contrato-versao-v1").textContent).not.toContain("(Assinado)");
  });
});

describe("modalidade de assinatura — Digital/Física (migration 157)", () => {
  function entry(over: Partial<AssinaturaEntry> = {}): AssinaturaEntry {
    return { data: null, isPending: false, isFetching: false, isError: false, ...over };
  }

  it("🔴 digital (default) keeps 'Enviar para assinatura' and shows no física actions", async () => {
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: { c1: entry() },
      onAbrirEnvioAssinatura: vi.fn(),
      onPatchModalidade: vi.fn(),
    });
    expect(screen.getByTestId("contrato-modalidade-digital-c1").getAttribute("aria-checked")).toBe("true");
    expect(screen.getByTestId("contrato-enviar-assinatura-c1")).toBeTruthy();
    expect(screen.queryByTestId("contrato-baixar-impressao-c1")).toBeNull();
    expect(screen.queryByTestId("contrato-marcar-assinado-c1")).toBeNull();
  });

  it("🔴 física hides the send-for-signature path and shows print + 'Marcar como assinado'", async () => {
    const onDownload = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [
        contrato({
          modalidade_assinatura: "fisica",
          versao_atual: versao({ id: "v2", origem: "gerado", modalidade_assinatura: "fisica" }),
        }),
      ],
      assinaturas: { c1: entry() },
      onAbrirEnvioAssinatura: vi.fn(),
      onPatchModalidade: vi.fn(),
      onMarcarAssinadoFisico: vi.fn(),
      onDownload,
    });
    expect(screen.queryByTestId("contrato-enviar-assinatura-c1")).toBeNull();
    fireEvent.click(screen.getByTestId("contrato-baixar-impressao-c1"));
    expect(onDownload).toHaveBeenCalledWith("c1", "v2", "pdf");
    expect(screen.getByTestId("contrato-marcar-assinado-c1").textContent).toContain(
      "Marcar como assinado",
    );
  });

  it("clicking the other segment PATCHes the modalidade for that contract", async () => {
    const onPatchModalidade = vi.fn();
    const { screen, fireEvent } = await render({
      contratos: [contrato()],
      assinaturas: { c1: entry() },
      onPatchModalidade,
    });
    fireEvent.click(screen.getByTestId("contrato-modalidade-fisica-c1"));
    expect(onPatchModalidade).toHaveBeenCalledWith("c1", "fisica");
  });

  it("🔴 'Física' is disabled while a digital envelope is live, and says why", async () => {
    const onPatchModalidade = vi.fn();
    const { screen } = await render({
      contratos: [contrato({ versao_atual: versao({ id: "v1", origem: "gerado" }) })],
      assinaturas: {
        c1: entry({
          data: {
            assinatura_id: "s1",
            external_id: "ext1",
            link_assinatura: "https://d4sign.example/ext1",
            provedor: "d4sign",
            status: "pendente",
            signatarios: [],
            enviado_em: "2026-09-17T20:00:00Z",
          },
        }),
      },
      onPatchModalidade,
    });
    expect((screen.getByTestId("contrato-modalidade-fisica-c1") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("contrato-modalidade-bloqueio-c1").textContent).toContain("cancele o envio");
  });
});
