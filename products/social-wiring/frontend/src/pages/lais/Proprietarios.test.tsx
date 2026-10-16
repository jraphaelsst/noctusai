/** Lais › Atualização de imóveis — the owner-confirmed value is shown with its provenance. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import LaisProprietarios from "./Proprietarios";
import { textoConfirmacao, type Proprietario } from "@/hooks/useLaisProprietarios";

const BASE: Proprietario = { id: "p1", nome: "Dono Teste", imovel_codigo: "AP10", status: "atualizado" };

function setup(items: Proprietario[]) {
  api.get.mockResolvedValue({ data: items });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><LaisProprietarios /></QueryClientProvider>);
}
beforeEach(() => { api.get.mockReset(); });
afterEach(cleanup);

describe("textoConfirmacao", () => {
  it("is null until something was confirmed", () => {
    expect(textoConfirmacao(BASE)).toBeNull();
    expect(textoConfirmacao({ ...BASE, confirmado_at: "2026-10-10T15:00:00Z" })).toBeNull();
  });

  it("joins status + price (with its kind) and always names the provenance", () => {
    const t = textoConfirmacao({
      ...BASE, status_confirmado: "Suspenso", preco_confirmado: "450000.00", preco_tipo_confirmado: "locacao",
      confirmado_at: "2026-10-10T15:00:00Z",
    })!;
    expect(t).toContain("Suspenso");
    expect(t).toMatch(/R\$\s?450\.000,00 \(locação\)/);
    expect(t.endsWith("confirmado pelo proprietário em 10/10/2026")).toBe(true);
  });

  it("a price confirmed before the kind existed shows without a kind", () => {
    const t = textoConfirmacao({ ...BASE, preco_confirmado: 1000, confirmado_at: "2026-10-10T15:00:00Z" })!;
    expect(t).not.toContain("(");
  });
});

describe("Proprietários page", () => {
  it("renders the confirmation column per row, a dash when none", async () => {
    setup([
      { ...BASE, status_confirmado: "Vendido", confirmado_at: "2026-10-10T15:00:00Z" },
      { ...BASE, id: "p2", imovel_codigo: "AP11", status: "enviado" },
    ]);
    const cells = await screen.findAllByTestId("proprietario-confirmacao");
    expect(cells[0].textContent).toBe("Vendido — confirmado pelo proprietário em 10/10/2026");
    expect(cells[1].textContent).toBe("—");
    expect(screen.getByText("Confirmado pelo proprietário")).toBeTruthy();
  });
});
