/**
 * LembretesSubpage — create/list/edit/mark-done/delete, presentational only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { LembretesSubpage, type LembretesSubpageProps } from "./LembretesSubpage";
import type { Lembrete } from "./types";

function lembrete(id: string, over: Partial<Lembrete> = {}): Lembrete {
  return {
    id,
    titulo: `Lembrete ${id}`,
    dispara_em: "2026-01-10T12:00:00+00:00",
    responsavel: null,
    concluido: false,
    concluido_em: null,
    created_at: "2026-01-01T00:00:00+00:00",
    ...over,
  };
}

function baseProps(over: Partial<LembretesSubpageProps> = {}): LembretesSubpageProps {
  return {
    lembretes: [],
    loading: false,
    responsaveis: [],
    onCreate: vi.fn(),
    onUpdate: vi.fn(),
    onDelete: vi.fn(),
    ...over,
  };
}

async function render(props: LembretesSubpageProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(LembretesSubpage, props));
}

describe("loading + empty states", () => {
  it("shows a skeleton only when there is genuinely nothing yet", async () => {
    const { getByTestId, queryByTestId } = await render(baseProps({ loading: true }));
    expect(getByTestId("lembretes-loading")).toBeTruthy();
    expect(queryByTestId("lembretes-subpage")).toBeNull();
  });

  it("says so when there are no lembretes (not loading)", async () => {
    const { getByTestId } = await render(baseProps());
    expect(getByTestId("lembretes-vazio")).toBeTruthy();
  });

  it("shows the pt-BR error, when set", async () => {
    const { getByTestId } = await render(baseProps({ error: "Não foi possível carregar os lembretes." }));
    expect(getByTestId("lembretes-error").textContent).toBe("Não foi possível carregar os lembretes.");
  });
});

describe("pending / done split + overdue highlight", () => {
  it("splits pending from concluído, oldest pending first (server order preserved)", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({
        lembretes: [lembrete("a"), lembrete("b", { concluido: true, concluido_em: "2026-01-05T00:00:00Z" })],
      }),
    );
    expect(getByTestId("lembretes-pendentes")).toBeTruthy();
    expect(getByTestId("lembretes-concluidos")).toBeTruthy();
    expect(getByTestId("lembrete-row-a").parentElement?.getAttribute("data-testid")).toBe("lembretes-pendentes");
    expect(queryByTestId("lembretes-vazio")).toBeNull();
  });

  it("flags a pending reminder whose dispara_em is in the past as atrasado", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({ lembretes: [lembrete("a", { dispara_em: "2000-01-01T00:00:00Z" })] }),
    );
    expect(getByTestId("lembrete-atrasado-a")).toBeTruthy();
    expect(queryByTestId("lembrete-atrasado-b")).toBeNull();
  });

  it("never flags a concluído reminder as atrasado even if its date is past", async () => {
    const { queryByTestId } = await render(
      baseProps({
        lembretes: [lembrete("a", { dispara_em: "2000-01-01T00:00:00Z", concluido: true, concluido_em: "2000-01-02T00:00:00Z" })],
      }),
    );
    expect(queryByTestId("lembrete-atrasado-a")).toBeNull();
  });

  it("shows the responsável name on the row, when set", async () => {
    const { getByTestId } = await render(
      baseProps({ lembretes: [lembrete("a", { responsavel: { id: "m1", nome: "Bia" } })] }),
    );
    expect(getByTestId("lembrete-row-a").textContent).toContain("Bia");
  });
});

describe("create", () => {
  it("requires título and data/hora before Adicionar is enabled", async () => {
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await render(baseProps());
    rtl.fireEvent.click(getByTestId("lembrete-novo-btn"));
    expect(getByTestId("lembrete-salvar-btn")).toBeDisabled();
  });

  it("sends titulo + a NAIVE ISO dispara_em (no browser-timezone conversion) + a null responsavel_id", async () => {
    const rtl = await import("@testing-library/react");
    const onCreate = vi.fn();
    const { getByTestId } = await render(baseProps({ onCreate }));
    rtl.fireEvent.click(getByTestId("lembrete-novo-btn"));
    rtl.fireEvent.change(getByTestId("lembrete-titulo-input"), { target: { value: "Ligar para o cliente" } });
    rtl.fireEvent.change(getByTestId("lembrete-data-hora-input"), { target: { value: "2026-10-01T14:00" } });
    rtl.fireEvent.click(getByTestId("lembrete-salvar-btn"));
    expect(onCreate).toHaveBeenCalledWith({
      titulo: "Ligar para o cliente",
      dispara_em: "2026-10-01T14:00:00",
      responsavel_id: null,
    });
    // the form closes on submit
    expect(rtl.screen.queryByTestId("lembrete-form-criar")).toBeNull();
  });

  it("offers a responsável select only when there is at least one candidate", async () => {
    const rtl = await import("@testing-library/react");
    const { getByTestId, queryByTestId } = await render(baseProps({ responsaveis: [{ id: "m1", nome: "Bia" }] }));
    rtl.fireEvent.click(getByTestId("lembrete-novo-btn"));
    expect(getByTestId("lembrete-responsavel-select")).toBeTruthy();

    rtl.cleanup();
    const semResponsaveis = await render(baseProps({ responsaveis: [] }));
    rtl.fireEvent.click(semResponsaveis.getByTestId("lembrete-novo-btn"));
    expect(semResponsaveis.queryByTestId("lembrete-responsavel-select")).toBeNull();
  });

  it("cancel closes the form without calling onCreate", async () => {
    const rtl = await import("@testing-library/react");
    const onCreate = vi.fn();
    const { getByTestId, queryByTestId } = await render(baseProps({ onCreate }));
    rtl.fireEvent.click(getByTestId("lembrete-novo-btn"));
    rtl.fireEvent.click(getByTestId("lembrete-cancelar-btn"));
    expect(queryByTestId("lembrete-form-criar")).toBeNull();
    expect(onCreate).not.toHaveBeenCalled();
  });
});

describe("edit + mark done + delete", () => {
  it("pre-fills the edit form from the row's own data (São Paulo wall-clock)", async () => {
    const rtl = await import("@testing-library/react");
    const { getByTestId } = await render(
      baseProps({ lembretes: [lembrete("a", { titulo: "Original", dispara_em: "2026-10-01T17:00:00+00:00" })] }),
    );
    rtl.fireEvent.click(getByTestId("lembrete-editar-a"));
    expect((getByTestId("lembrete-titulo-input") as HTMLInputElement).value).toBe("Original");
    expect((getByTestId("lembrete-data-hora-input") as HTMLInputElement).value).toBe("2026-10-01T14:00");
  });

  it("saving an edit calls onUpdate with only the edited fields shape (titulo + dispara_em + responsavel_id)", async () => {
    const rtl = await import("@testing-library/react");
    const onUpdate = vi.fn();
    const { getByTestId } = await render(baseProps({ lembretes: [lembrete("a")], onUpdate }));
    rtl.fireEvent.click(getByTestId("lembrete-editar-a"));
    rtl.fireEvent.change(getByTestId("lembrete-titulo-input"), { target: { value: "Editado" } });
    rtl.fireEvent.click(getByTestId("lembrete-salvar-btn"));
    expect(onUpdate).toHaveBeenCalledWith("a", {
      titulo: "Editado",
      dispara_em: "2026-01-10T09:00:00",
      responsavel_id: null,
    });
  });

  it("toggling the checkbox marks/reopens via onUpdate({ concluido })", async () => {
    const rtl = await import("@testing-library/react");
    const onUpdate = vi.fn();
    const { getByTestId } = await render(baseProps({ lembretes: [lembrete("a")], onUpdate }));
    rtl.fireEvent.click(getByTestId("lembrete-concluido-a"));
    expect(onUpdate).toHaveBeenCalledWith("a", { concluido: true });
  });

  it("delete requires a second tap (confirmation) before onDelete fires", async () => {
    const rtl = await import("@testing-library/react");
    const onDelete = vi.fn();
    const { getByTestId, queryByTestId } = await render(baseProps({ lembretes: [lembrete("a")], onDelete }));
    rtl.fireEvent.click(getByTestId("lembrete-excluir-a"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(getByTestId("lembrete-confirmar-excluir-a")).toBeTruthy();

    rtl.fireEvent.click(getByTestId("lembrete-confirmar-excluir-a"));
    expect(onDelete).toHaveBeenCalledWith("a");
    expect(queryByTestId("lembrete-confirmar-excluir-a")).toBeNull();
  });

  it("cancelling the delete confirmation never calls onDelete", async () => {
    const rtl = await import("@testing-library/react");
    const onDelete = vi.fn();
    const { getByTestId, queryByTestId } = await render(baseProps({ lembretes: [lembrete("a")], onDelete }));
    rtl.fireEvent.click(getByTestId("lembrete-excluir-a"));
    rtl.fireEvent.click(getByTestId("lembrete-cancelar-excluir-a"));
    expect(onDelete).not.toHaveBeenCalled();
    expect(queryByTestId("lembrete-confirmar-excluir-a")).toBeNull();
  });
});
