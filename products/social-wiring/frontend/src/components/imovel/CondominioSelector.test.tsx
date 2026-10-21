/** CondominioSelector (migration 300): search-as-you-type dropdown, attach one,
 *  chip with trocar/remover, "Cadastrar condomínio “…”", casa de rua
 *  exclusivity, honest loading states. Data layer mocked at the hook seam. */
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockBusca, mockCriar } = vi.hoisted(() => ({ mockBusca: vi.fn(), mockCriar: vi.fn() }));
vi.mock("@/hooks/useCondominios", () => ({
  useCondominioBusca: mockBusca,
  useCriarCondominio: () => ({ mutate: mockCriar, isPending: false, isError: false, error: null }),
}));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));

import { useState } from "react";
import { cleanup, fireEvent, render } from "@testing-library/react";

import CondominioSelector, { type CondominioValor } from "./CondominioSelector";

afterEach(() => {
  cleanup();
  mockBusca.mockReset();
  mockCriar.mockReset();
});

const c = (id: string, nome: string) => ({
  id,
  nome,
  cidade: "Cotia",
  bairro: "Granja Viana",
  status_validacao: "validado" as const,
});
const TODOS = [c("c-1", "Vila Verde"), c("c-2", "Vila Velha"), c("c-3", "Chácara Ipê")];

function servidor(q: string) {
  const t = q.trim().toLowerCase();
  const data = t ? TODOS.filter((x) => x.nome.toLowerCase().includes(t)) : undefined;
  return { data, isPending: !t, isFetching: false, isError: false };
}

function Harness({ inicial, onChange }: { inicial?: CondominioValor; onChange?: (v: CondominioValor) => void }) {
  const [v, setV] = useState<CondominioValor>(inicial ?? { condominio: null, casaDeRua: false });
  return (
    <CondominioSelector
      value={v}
      onChange={(n) => {
        setV(n);
        onChange?.(n);
      }}
    />
  );
}

describe("CondominioSelector", () => {
  it("fetches as the user types and lists clickable items under the field", () => {
    mockBusca.mockImplementation(servidor);
    const { getByTestId, queryByTestId } = render(<Harness />);
    expect(queryByTestId("imovel-condominio-resultados")).toBeNull();
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "vila" } });
    expect(mockBusca).toHaveBeenLastCalledWith("vila");
    expect(getByTestId("imovel-condominio-item-c-1")).toBeTruthy();
    expect(getByTestId("imovel-condominio-item-c-2")).toBeTruthy();
    expect(queryByTestId("imovel-condominio-item-c-3")).toBeNull();
    // The last item always offers to create the typed name.
    expect(getByTestId("imovel-condominio-cadastrar").textContent).toContain("Cadastrar condomínio “vila”");
  });

  it("clicking an item attaches exactly one and shows it as a chip", () => {
    mockBusca.mockImplementation(servidor);
    const onChange = vi.fn();
    const { getByTestId, queryByTestId } = render(<Harness onChange={onChange} />);
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "velha" } });
    fireEvent.click(getByTestId("imovel-condominio-item-c-2"));
    expect(onChange).toHaveBeenLastCalledWith({ condominio: TODOS[1], casaDeRua: false });
    expect(getByTestId("imovel-condominio-chip").textContent).toContain("Vila Velha");
    expect(queryByTestId("imovel-condominio-busca")).toBeNull();
  });

  it("'Trocar' re-opens the search; 'Remover' detaches", () => {
    mockBusca.mockImplementation(servidor);
    const onChange = vi.fn();
    const { getByTestId, queryByTestId } = render(
      <Harness inicial={{ condominio: TODOS[0], casaDeRua: false }} onChange={onChange} />,
    );
    fireEvent.click(getByTestId("imovel-condominio-trocar"));
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "ipê" } });
    fireEvent.click(getByTestId("imovel-condominio-item-c-3"));
    expect(getByTestId("imovel-condominio-chip").textContent).toContain("Chácara Ipê");
    fireEvent.click(getByTestId("imovel-condominio-remover"));
    expect(onChange).toHaveBeenLastCalledWith({ condominio: null, casaDeRua: false });
    expect(queryByTestId("imovel-condominio-chip")).toBeNull();
    expect(getByTestId("imovel-condominio-pendente")).toBeTruthy();
  });

  it("'Cadastrar' creates with the typed name and attaches the server's answer", () => {
    mockBusca.mockImplementation(servidor);
    const novo = { ...c("c-9", "Reserva do Vianna"), criado: true };
    mockCriar.mockImplementation((_body, opts) => opts.onSuccess(novo));
    const onChange = vi.fn();
    const { getByTestId } = render(<Harness onChange={onChange} />);
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "  Reserva do Vianna " } });
    fireEvent.click(getByTestId("imovel-condominio-cadastrar"));
    expect(mockCriar).toHaveBeenCalledWith({ nome: "Reserva do Vianna" }, expect.anything());
    expect(onChange).toHaveBeenLastCalledWith({ condominio: novo, casaDeRua: false });
    expect(getByTestId("imovel-condominio-chip").textContent).toContain("Reserva do Vianna");
  });

  it("'Casa de rua' is exclusive: it detaches and hides the search", () => {
    mockBusca.mockImplementation(servidor);
    const onChange = vi.fn();
    const { getByTestId, queryByTestId } = render(
      <Harness inicial={{ condominio: TODOS[0], casaDeRua: false }} onChange={onChange} />,
    );
    fireEvent.click(getByTestId("imovel-casa-de-rua"));
    expect(onChange).toHaveBeenLastCalledWith({ condominio: null, casaDeRua: true });
    expect(queryByTestId("imovel-condominio-chip")).toBeNull();
    expect(queryByTestId("imovel-condominio-busca")).toBeNull();
    expect(queryByTestId("imovel-condominio-pendente")).toBeNull();
    // Unchecking returns to "not answered" — never back to the old link.
    fireEvent.click(getByTestId("imovel-casa-de-rua"));
    expect(onChange).toHaveBeenLastCalledWith({ condominio: null, casaDeRua: false });
    expect(getByTestId("imovel-condominio-busca")).toBeTruthy();
  });

  it("loading: skeleton only with no data; a refetch keeps the items on screen", () => {
    mockBusca.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const { getByTestId, queryByTestId, rerender } = render(<Harness />);
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "vi" } });
    expect(getByTestId("imovel-condominio-carregando")).toBeTruthy();
    expect(queryByTestId("imovel-condominio-vazio")).toBeNull();

    mockBusca.mockReturnValue({ data: [TODOS[0]], isPending: false, isFetching: true, isError: false });
    rerender(<Harness />);
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "vil" } });
    expect(queryByTestId("imovel-condominio-carregando")).toBeNull();
    expect(getByTestId("imovel-condominio-item-c-1")).toBeTruthy();
    expect(getByTestId("imovel-condominio-atualizando")).toBeTruthy();
  });

  it("an empty answer says so only when nothing is in flight", () => {
    mockBusca.mockReturnValue({ data: [], isPending: false, isFetching: false, isError: false });
    const { getByTestId } = render(<Harness />);
    fireEvent.change(getByTestId("imovel-condominio-busca"), { target: { value: "zzz" } });
    expect(getByTestId("imovel-condominio-vazio").textContent).toContain("Nenhum condomínio encontrado");
    expect(getByTestId("imovel-condominio-cadastrar")).toBeTruthy();
  });
});
