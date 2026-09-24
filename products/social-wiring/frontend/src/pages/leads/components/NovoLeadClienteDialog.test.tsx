/**
 * NovoLeadClienteDialog — Base de Leads' "Novo lead" flow (leads-novo-lead).
 *
 * Exercises the whole attach-to-existing-cliente round trip: type into the
 * live search field, pick a result from the dropdown, submit, and confirm
 * BOTH the outer "Novo lead" dialog and (separately) the nested "+" cliente
 * dialog close on success — plus the "+" escape hatch selecting a brand-new
 * cliente draft as the chosen one.
 *
 * `ClienteAttachPicker`/`NovoClienteInlineDialog` are the REAL components
 * (not stubbed) — what is under test here is the whole composed flow, the
 * same rationale `ImovelCodigoPicker.test.tsx` gives for mocking the HOOK
 * rather than the fetch: `useClientesBusca` is mocked so a result set is
 * driven directly, without wiring react-query + a debounce timer through
 * the assertions.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockUseClientesBusca, mockCreateMutate } = vi.hoisted(() => ({
  mockUseClientesBusca: vi.fn(),
  mockCreateMutate: vi.fn(),
}));

vi.mock("@/hooks/useClientes", () => ({
  useClientesBusca: mockUseClientesBusca,
}));
vi.mock("@/hooks/useDebouncedValue", () => ({
  useDebouncedValue: (v: string) => v,
}));
vi.mock("@/hooks/useLeadsSources", () => ({
  useLeadSources: () => ({ data: [], isPending: false }),
}));
vi.mock("@/hooks/useLeadsCorretores", () => ({
  useLeadCorretores: () => ({ data: [], isPending: false }),
}));
vi.mock("@/hooks/useLeads", () => ({
  useLeadMutations: () => ({
    create: { mutate: mockCreateMutate, isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    remove: { mutate: vi.fn(), isPending: false },
  }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

beforeEach(() => {
  mockUseClientesBusca.mockReturnValue(busca([]));
});

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockUseClientesBusca.mockReset();
  mockCreateMutate.mockReset();
});

import { NovoLeadClienteDialog } from "./NovoLeadClienteDialog";
import type { Cliente } from "@/hooks/useClientes"; // type-only — erased at build, not affected by the mock above

function cliente(over: Partial<Cliente> = {}): Cliente {
  return {
    id: "c1",
    nome: "Fernando Souza",
    chave_canonica: "+5511987654321",
    chave_tipo: "telefone",
    identidade_incerta: false,
    ativo: true,
    inativo_em: null,
    arquivado_em: null,
    primeiro_contato_em: null,
    ultimo_contato_em: null,
    celular: "+5511987654321",
    email: null,
    ...over,
  };
}

function busca(items: Cliente[], over: Record<string, unknown> = {}) {
  return { data: { items, total: items.length, page: 1, pages: 1 }, isPending: false, isFetching: false, ...over };
}

async function render() {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const onOpenChange = vi.fn();
  const view = rtl.render(
    React.createElement(NovoLeadClienteDialog, { open: true, onOpenChange }),
  );
  return { ...rtl, ...view, onOpenChange };
}

async function digitar(testId: string, termo: string) {
  const rtl = await import("@testing-library/react");
  rtl.fireEvent.change(rtl.screen.getByTestId(testId), { target: { value: termo } });
}

describe("NovoLeadClienteDialog — anexar a um cliente já cadastrado", () => {
  it("mostra o campo de busca e o dropdown com resultados ao digitar", async () => {
    mockUseClientesBusca.mockReturnValue(busca([cliente()]));
    const { getByTestId } = await render();

    await digitar("novo-lead-cliente-picker-input", "Fer");

    const opcao = getByTestId("novo-lead-cliente-picker-opcao-c1");
    expect(opcao.textContent).toContain("Fernando Souza");
  });

  it("seleciona um cliente existente da lista e envia contato = chave_canonica no create", async () => {
    mockUseClientesBusca.mockReturnValue(busca([cliente()]));
    const { getByTestId, fireEvent } = await render();

    await digitar("novo-lead-cliente-picker-input", "Fer");
    fireEvent.click(getByTestId("novo-lead-cliente-picker-opcao-c1"));

    // Chosen-cliente chip replaces the search field.
    expect(getByTestId("novo-lead-cliente-picker-escolhido").textContent).toContain(
      "Fernando Souza",
    );

    fireEvent.click(getByTestId("novo-lead-submit"));

    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    const [body] = mockCreateMutate.mock.calls[0];
    expect(body.cliente_nome).toBe("Fernando Souza");
    // The EXACT chave_canonica, not a re-typed/re-formatted value — this is
    // what lets `attach_lead_now`'s exact-key lookup reattach to the SAME
    // cliente instead of creating a duplicate.
    expect(body.contato).toBe("+5511987654321");
  });

  it("'+' abre o modal aninhado; salvar seleciona o novo cliente e fecha SÓ o modal aninhado", async () => {
    mockUseClientesBusca.mockReturnValue(busca([]));
    const { getByTestId, queryByTestId, fireEvent } = await render();

    fireEvent.click(getByTestId("novo-lead-cliente-picker-novo-abrir"));
    expect(getByTestId("novo-lead-cliente-picker-novo")).toBeTruthy();

    fireEvent.change(getByTestId("novo-lead-cliente-picker-novo-nome"), {
      target: { value: "Beatriz Nova" },
    });
    fireEvent.change(getByTestId("novo-lead-cliente-picker-novo-contato"), {
      target: { value: "11 99999-0000" },
    });
    fireEvent.click(getByTestId("novo-lead-cliente-picker-novo-salvar"));

    // Nested dialog closed on its own save...
    expect(queryByTestId("novo-lead-cliente-picker-novo")).toBeNull();
    // ...and the outer dialog is still open, now showing the draft as chosen.
    expect(getByTestId("novo-lead-cliente-dialog")).toBeTruthy();
    expect(getByTestId("novo-lead-cliente-picker-escolhido").textContent).toContain(
      "Beatriz Nova",
    );
  });

  it("cria o lead com o cliente novo e fecha o modal externo ao ter sucesso", async () => {
    mockUseClientesBusca.mockReturnValue(busca([]));
    const { getByTestId, fireEvent, onOpenChange } = await render();

    fireEvent.click(getByTestId("novo-lead-cliente-picker-novo-abrir"));
    fireEvent.change(getByTestId("novo-lead-cliente-picker-novo-nome"), {
      target: { value: "Beatriz Nova" },
    });
    fireEvent.click(getByTestId("novo-lead-cliente-picker-novo-salvar"));

    fireEvent.click(getByTestId("novo-lead-submit"));

    expect(mockCreateMutate).toHaveBeenCalledTimes(1);
    const [body, opts] = mockCreateMutate.mock.calls[0];
    expect(body.cliente_nome).toBe("Beatriz Nova");
    expect(body.contato).toBeNull();

    // Drive the mutate's onSuccess (mockCreateMutate is a plain vi.fn(),
    // not the real hook) — mirrors LeadFormDialog.test.tsx's pattern of
    // asserting the callback the component WIRED, not react-query's own
    // machinery.
    opts.onSuccess();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("o botão 'Criar lead' fica desabilitado até um cliente ser escolhido", async () => {
    const { getByTestId } = await render();
    expect((getByTestId("novo-lead-submit") as HTMLButtonElement).disabled).toBe(true);
  });
});
