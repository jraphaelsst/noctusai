/** The roteiro flow: tick → "Gerar roteiro" (disabled with none ticked) → the
 *  EDITOR opens with the ticked imóveis as a new DRAFT (created + autosaved
 *  there). Nothing is downloaded from this list any more: the PDF exists only
 *  for a gerado roteiro. The editor itself is covered by
 *  `RoteiroEditorDialog.test.tsx`; here it is stubbed at its props seam. */
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  useInteresses: vi.fn(),
  add: vi.fn(),
  remove: vi.fn(),
  editor: vi.fn(),
  baixarPdf: vi.fn(),
}));

vi.mock("@/hooks/useInteresses", () => ({
  useInteresses: m.useInteresses,
  useInteresseMutations: () => ({
    add: { mutate: m.add, isPending: false },
    remove: { mutate: m.remove, isPending: false, variables: undefined },
  }),
}));
vi.mock("@/hooks/usePessoa", () => ({
  usePessoaResumo: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useCardHub", () => ({
  useImoveisBusca: () => ({ data: { items: [] }, isPending: false, isFetching: false, isError: false }),
  baixarRoteiroPdf: m.baixarPdf,
}));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));
vi.mock("@/components/card/RoteiroEditorDialog", () => ({
  RoteiroEditorDialog: (p: {
    clienteId: string;
    atendimentoId?: string | null;
    inicial?: { codigo: string }[];
    onGerado?: () => void;
    onOpenChange: (o: boolean) => void;
  }) => {
    m.editor(p);
    return (
      <div data-testid="editor-stub" data-cliente={p.clienteId} data-at={p.atendimentoId ?? ""}>
        <span data-testid="editor-inicial">{(p.inicial ?? []).map((i) => i.codigo).join(",")}</span>
        <button data-testid="editor-gerado" onClick={() => p.onGerado?.()} />
        <button data-testid="editor-fechar" onClick={() => p.onOpenChange(false)} />
      </div>
    );
  },
}));

import { cleanup, fireEvent, render } from "@testing-library/react";

import { ImovelInteressesList } from "./ImovelInteressesList";
import { interesse } from "./fixtures";

afterEach(() => {
  cleanup();
  Object.values(m).forEach((v) => typeof v === "function" && "mockReset" in v && v.mockReset());
});

function comLista(items = ["ONE9001", "ONE9002", "ONE9003"]) {
  m.useInteresses.mockReturnValue({
    data: { items: items.map((c) => interesse(c)), total: items.length },
    isPending: false,
    isFetching: false,
    isError: false,
  });
}

describe("ImovelInteressesList — rows", () => {
  it("renders photo, código, endereço + complemento, R$, origem and a checkbox per row", () => {
    comLista(["ONE9001"]);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    const row = getByTestId("interesse-ONE9001");
    expect(row.querySelector("img")?.getAttribute("src")).toContain("ONE9001");
    expect(row.textContent).toContain("apto 52");
    expect(row.textContent).toMatch(/R\$\s?850\.000/);
    expect(getByTestId("interesse-origem").textContent).toBe("Lead");
    expect(getByTestId("interesse-check-ONE9001")).toBeTruthy();
  });

  it("states: skeleton only on first load, empty, error", () => {
    m.useInteresses.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const a = render(<ImovelInteressesList clienteId="c1" />);
    expect(a.queryByTestId("interesses-loading")).toBeTruthy();
    a.unmount();

    m.useInteresses.mockReturnValue({ data: { items: [], total: 0 }, isPending: false, isFetching: false, isError: false });
    const b = render(<ImovelInteressesList clienteId="c1" />);
    expect(b.queryByTestId("interesses-vazio")).toBeTruthy();
    b.unmount();

    m.useInteresses.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    const c = render(<ImovelInteressesList clienteId="c1" />);
    expect(c.queryByTestId("interesses-erro")).toBeTruthy();
  });

  it("a refetch with rows on screen keeps the rows (spinner only)", () => {
    m.useInteresses.mockReturnValue({
      data: { items: [interesse("ONE9001")], total: 1 },
      isPending: false,
      isFetching: true,
      isError: false,
    });
    const { queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    expect(queryByTestId("interesse-ONE9001")).toBeTruthy();
    expect(queryByTestId("interesses-refreshing")).toBeTruthy();
    expect(queryByTestId("interesses-loading")).toBeNull();
  });

  it("remove calls the mutation with the interesse id", () => {
    comLista(["ONE9001"]);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-remover-ONE9001"));
    expect(m.remove.mock.calls[0][0]).toBe("int-ONE9001");
  });
});

describe("ImovelInteressesList — roteiro flow", () => {
  it("'Gerar roteiro' is disabled until at least one row is checked", () => {
    comLista();
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    const gerar = getByTestId("roteiro-gerar") as HTMLButtonElement;
    expect(gerar.disabled).toBe(true);

    fireEvent.click(getByTestId("interesse-check-ONE9002"));
    expect(gerar.disabled).toBe(false);

    fireEvent.click(getByTestId("interesse-check-ONE9002"));
    expect(gerar.disabled).toBe(true);
  });

  it("🔴 opens the editor with the ticked imóveis, in list order, and the atendimento — creating nothing itself", () => {
    comLista();
    const { getByTestId, queryByTestId } = render(
      <ImovelInteressesList clienteId="c1" atendimentoId="at-1" />,
    );
    expect(queryByTestId("editor-stub")).toBeNull();
    for (const c of ["ONE9003", "ONE9001"]) {
      fireEvent.click(getByTestId(`interesse-check-${c}`));
    }
    fireEvent.click(getByTestId("roteiro-gerar"));

    const stub = getByTestId("editor-stub");
    expect(stub.getAttribute("data-cliente")).toBe("c1");
    expect(stub.getAttribute("data-at")).toBe("at-1");
    // list order (the rows' order), not tick order
    expect(getByTestId("editor-inicial").textContent).toBe("ONE9001,ONE9003");
  });

  it("🔴 never downloads a PDF — not on open, not when the draft is generated, not on close", () => {
    comLista(["ONE9001"]);
    const { getByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-check-ONE9001"));
    fireEvent.click(getByTestId("roteiro-gerar"));
    fireEvent.click(getByTestId("editor-gerado"));
    expect(m.baixarPdf).not.toHaveBeenCalled();
  });

  it("clears the ticks once the roteiro was generated, and closing the editor unmounts it", () => {
    comLista(["ONE9001", "ONE9002"]);
    const { getByTestId, queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    fireEvent.click(getByTestId("interesse-check-ONE9001"));
    fireEvent.click(getByTestId("roteiro-gerar"));
    fireEvent.click(getByTestId("editor-gerado"));
    expect((getByTestId("interesse-check-ONE9001") as HTMLInputElement).getAttribute("data-state")).toBe(
      "unchecked",
    );
    fireEvent.click(getByTestId("editor-fechar"));
    expect(queryByTestId("editor-stub")).toBeNull();
  });
});

describe("ImovelInteressesList — adicionar interesse", () => {
  it("opens the search popup", () => {
    comLista();
    const { getByTestId, queryByTestId } = render(<ImovelInteressesList clienteId="c1" />);
    expect(queryByTestId("adicionar-interesse-dialog")).toBeNull();
    fireEvent.click(getByTestId("interesse-adicionar"));
    expect(queryByTestId("adicionar-interesse-dialog")).toBeTruthy();
    expect(queryByTestId("imovel-busca-input")).toBeTruthy();
  });
});
