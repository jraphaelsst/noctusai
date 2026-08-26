/**
 * CriarRoteiroDialog — the live property search and the ordered list.
 *
 * 🔴 THE LOAD-BEARING TEST is `typing ONE9 queries with that term`: the user
 * described this flow precisely — "Once i type 'ONE9' i want to see on this
 * listing all ONE9xxxx refs that we have automatically" — and it works by
 * reusing `GET /api/imoveis?search=`, which already `ilike`s `codigo`.
 *
 * WHAT THIS FILE DOES NOT SIMULATE, STATED RATHER THAN IMPLIED: the drag
 * gesture itself. dnd-kit's pointer/keyboard sensors need a real layout to
 * resolve a drop target, and a jsdom approximation of that would assert the
 * mock, not the feature. What IS asserted is everything around it — the list
 * order is the submitted order, and the sortable list is fed the same items in
 * the same sequence the user built.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseImoveisBusca } = vi.hoisted(() => ({ mockUseImoveisBusca: vi.fn() }));

// The dialog is tested as a component, not as a data layer: mocking the one
// hook it consumes keeps react-query, the API client and the debounce timer
// out of assertions about clicking a row.
vi.mock("@/hooks/useCardHub", () => ({ useImoveisBusca: mockUseImoveisBusca }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockUseImoveisBusca.mockReset();
});

import { CriarRoteiroDialog } from "./CriarRoteiroDialog";
import type { ImovelBusca } from "@/types/cardHub";

function hit(codigo: string, over: Partial<ImovelBusca> = {}): ImovelBusca {
  return {
    codigo,
    titulo: `Apartamento ${codigo}`,
    empreendimento: "Edifício Aurora",
    bairro: "Centro",
    cidade: "Florianópolis",
    foto_destaque: null,
    ...over,
  };
}

function busca(items: ImovelBusca[], over: Record<string, unknown> = {}) {
  return {
    data: { items },
    isPending: false,
    isFetching: false,
    isError: false,
    ...over,
  };
}

async function render(props: Partial<React.ComponentProps<typeof CriarRoteiroDialog>> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(
    React.createElement(CriarRoteiroDialog, {
      open: true,
      onOpenChange: vi.fn(),
      onCriar: vi.fn(),
      ...props,
    }),
  );
}

async function digitar(getByTestId: (id: string) => HTMLElement, termo: string) {
  const rtl = await import("@testing-library/react");
  rtl.fireEvent.change(getByTestId("roteiro-busca"), { target: { value: termo } });
}

describe("CriarRoteiroDialog — a busca ao vivo", () => {
  it("🔴 queries with the typed term, so ONE9 finds every ONE9xxxx", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { getByTestId } = await render();
    await digitar(getByTestId, "ONE9");
    expect(mockUseImoveisBusca).toHaveBeenLastCalledWith("ONE9");
  });

  it("lists every match under the field", async () => {
    mockUseImoveisBusca.mockReturnValue(
      busca([hit("ONE9001"), hit("ONE9002"), hit("ONE9481")]),
    );
    const { getByTestId } = await render();
    await digitar(getByTestId, "ONE9");
    expect(getByTestId("roteiro-busca-item-ONE9001")).toBeTruthy();
    expect(getByTestId("roteiro-busca-item-ONE9002")).toBeTruthy();
    expect(getByTestId("roteiro-busca-item-ONE9481")).toBeTruthy();
  });

  it("asks for two characters before spending a round trip", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { getByTestId } = await render();
    await digitar(getByTestId, "O");
    expect(getByTestId("roteiro-busca-popover").textContent).toContain("2 caracteres");
  });

  it("🔴 shows the spinner during a background refetch, never 'nenhum imóvel'", async () => {
    // The lying-loading-state class: `isPending` is false on a refetch, so a
    // branch keyed off it alone would render "no results" over results.
    mockUseImoveisBusca.mockReturnValue(
      busca([hit("ONE9001")], { isPending: false, isFetching: true }),
    );
    const { getByTestId, queryByTestId } = await render();
    await digitar(getByTestId, "ONE9");
    expect(getByTestId("roteiro-busca-carregando")).toBeTruthy();
    expect(queryByTestId("roteiro-busca-vazio")).toBeNull();
  });

  it("says so when nothing matches", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { getByTestId } = await render();
    await digitar(getByTestId, "ZZZ9");
    expect(getByTestId("roteiro-busca-vazio")).toBeTruthy();
  });

  it("surfaces a failed search instead of an empty one", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([], { isError: true, data: undefined }));
    const { getByTestId, queryByTestId } = await render();
    await digitar(getByTestId, "ONE9");
    expect(getByTestId("roteiro-busca-erro")).toBeTruthy();
    expect(queryByTestId("roteiro-busca-vazio")).toBeNull();
  });
});

describe("CriarRoteiroDialog — montando o roteiro", () => {
  it("adds the clicked property and clears the field, keeping the popover usable", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { getByTestId } = await render();
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));

    expect(getByTestId("imovel-visita-ONE9001")).toBeTruthy();
    expect((getByTestId("roteiro-busca") as HTMLInputElement).value).toBe("");
  });

  it("disables a property already on the route", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { getByTestId } = await render();
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));
    await digitar(getByTestId, "ONE9");

    const linha = getByTestId("roteiro-busca-item-ONE9001") as HTMLButtonElement;
    expect(linha.disabled).toBe(true);
    expect(linha.textContent).toContain("já no roteiro");
  });

  it("removes a property from the list", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { getByTestId, queryByTestId } = await render();
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));
    rtl.fireEvent.click(getByTestId("imovel-visita-remover-ONE9001"));

    expect(queryByTestId("imovel-visita-ONE9001")).toBeNull();
    expect(getByTestId("roteiro-lista-vazia")).toBeTruthy();
  });

  it("numbers the list in visiting order", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001"), hit("ONE9002")]));
    const { getByTestId } = await render();
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9002"));
    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));

    const lista = getByTestId("roteiro-lista");
    const codigos = Array.from(lista.querySelectorAll("[data-testid^='imovel-visita-ONE']")).map(
      (el) => el.getAttribute("data-testid"),
    );
    expect(codigos).toEqual(["imovel-visita-ONE9002", "imovel-visita-ONE9001"]);
  });
});

describe("CriarRoteiroDialog — salvar", () => {
  it("🔴 posts the códigos IN LIST ORDER — the order IS the plan", async () => {
    mockUseImoveisBusca.mockReturnValue(
      busca([hit("ONE9001"), hit("ONE9002"), hit("ONE9003")]),
    );
    const onCriar = vi.fn();
    const { getByTestId } = await render({ onCriar });
    const rtl = await import("@testing-library/react");

    for (const codigo of ["ONE9003", "ONE9001", "ONE9002"]) {
      await digitar(getByTestId, "ONE9");
      rtl.fireEvent.click(getByTestId(`roteiro-busca-item-${codigo}`));
    }
    rtl.fireEvent.change(getByTestId("roteiro-titulo"), {
      target: { value: "Terça de manhã" },
    });
    rtl.fireEvent.click(getByTestId("roteiro-salvar"));

    expect(onCriar).toHaveBeenCalledWith({
      titulo: "Terça de manhã",
      imoveis: ["ONE9003", "ONE9001", "ONE9002"],
    });
  });

  it("sends a null título rather than an empty string", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const onCriar = vi.fn();
    const { getByTestId } = await render({ onCriar });
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));
    rtl.fireEvent.click(getByTestId("roteiro-salvar"));

    expect(onCriar).toHaveBeenCalledWith({ titulo: null, imoveis: ["ONE9001"] });
  });

  it("cannot save an empty roteiro", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([]));
    const { getByTestId } = await render();
    expect((getByTestId("roteiro-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("cannot double-submit while saving", async () => {
    mockUseImoveisBusca.mockReturnValue(busca([hit("ONE9001")]));
    const { getByTestId } = await render({ saving: true });
    const rtl = await import("@testing-library/react");

    await digitar(getByTestId, "ONE9");
    rtl.fireEvent.click(getByTestId("roteiro-busca-item-ONE9001"));
    expect((getByTestId("roteiro-salvar") as HTMLButtonElement).disabled).toBe(true);
  });
});
