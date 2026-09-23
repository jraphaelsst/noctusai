/**
 * "Marcar como perdido": the motivo is REQUIRED (it is what the loss
 * statistics are made of) and travels to `POST /negocios/{id}/perder`.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn(), upload: vi.fn() },
}));
vi.mock("@noctusai/seed/infra", () => ({ api }));

import { PerderNegocioDialog } from "../NegocioCardDialog";
import { usePerderNegocio } from "@/hooks/useComercial";
import type { Negocio } from "@/types/crm";

const NEGOCIO = { id: "n1", titulo: "Padaria", status: "aberto" } as Negocio;

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("PerderNegocioDialog", () => {
  it("keeps confirm disabled until a motivo is typed, then sends it trimmed", () => {
    const onConfirm = vi.fn();
    render(<PerderNegocioDialog negocio={NEGOCIO} onConfirm={onConfirm} onCancel={vi.fn()} />);
    const confirmar = screen.getByRole("button", { name: "Marcar como perdido" });
    expect(confirmar).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "  escolheu outra agência " } });
    expect(confirmar).not.toBeDisabled();
    fireEvent.click(confirmar);
    expect(onConfirm).toHaveBeenCalledWith("escolheu outra agência");
  });

  it("renders nothing without a negócio", () => {
    render(<PerderNegocioDialog negocio={null} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("usePerderNegocio", () => {
  it("POSTs the motivo to /perder and refreshes the funnel", async () => {
    api.post.mockResolvedValue({ data: { id: "n1", status: "perdido" } });
    const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => usePerderNegocio(), {
      wrapper: ({ children }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>,
    });
    await act(async () => {
      await result.current.mutateAsync({ id: "n1", motivo: "sem orçamento" });
    });
    expect(api.post).toHaveBeenCalledWith("/api/comercial/negocios/n1/perder", { motivo: "sem orçamento" });
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["igig-comercial"] }));
  });
});
