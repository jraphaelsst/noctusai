/**
 * ClienteAttachPicker — a FAILED search is an error, never "Nenhum cliente"
 * (F76: an error rendered as empty invites registering a duplicate).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseClientesBusca } = vi.hoisted(() => ({ mockUseClientesBusca: vi.fn() }));
vi.mock("@/hooks/useClientes", () => ({ useClientesBusca: mockUseClientesBusca }));
vi.mock("@/hooks/useDebouncedValue", () => ({ useDebouncedValue: (v: string) => v }));
vi.mock("./NovoClienteInlineDialog", () => ({ NovoClienteInlineDialog: () => null }));

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
  mockUseClientesBusca.mockReset();
});

import { ClienteAttachPicker } from "./ClienteAttachPicker";

async function digitar(over: Record<string, unknown>) {
  mockUseClientesBusca.mockReturnValue({
    data: { items: [] },
    isPending: false,
    isFetching: false,
    isError: false,
    ...over,
  });
  const rtl = await import("@testing-library/react");
  rtl.render(<ClienteAttachPicker value={null} onChange={vi.fn()} />);
  rtl.fireEvent.change(rtl.screen.getByTestId("cliente-attach-picker-input"), {
    target: { value: "Maria" },
  });
  return rtl.screen;
}

describe("ClienteAttachPicker", () => {
  it("error -> error state + retry, no empty message", async () => {
    const refetch = vi.fn();
    const screen = await digitar({ data: undefined, isError: true, refetch });
    expect(screen.getByTestId("cliente-attach-picker-erro")).toBeTruthy();
    expect(screen.queryByTestId("cliente-attach-picker-vazio")).toBeNull();
    const rtl = await import("@testing-library/react");
    rtl.fireEvent.click(screen.getByTestId("cliente-attach-picker-tentar-novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("success-empty -> empty message", async () => {
    const screen = await digitar({});
    expect(screen.getByTestId("cliente-attach-picker-vazio")).toBeTruthy();
    expect(screen.queryByTestId("cliente-attach-picker-erro")).toBeNull();
  });
});
