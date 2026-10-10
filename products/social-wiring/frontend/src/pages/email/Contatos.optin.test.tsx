import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// Double opt-in surface of Contatos (P1b(d)): the Opt-in column badge, the
// per-row "Reenviar confirmação" action, and the import dialog's checkbox.
// The ResourceManager organ is stubbed to render one row through the page's
// own `columns[].render` + `rowActions` — what the organ itself does.

const { toastSuccess, toastError } = vi.hoisted(() => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError, info: vi.fn() } }));
vi.mock("@noctusai/lib/design-system", () => ({ AIIndicator: () => null }));
vi.mock("@/lib/api", () => ({ api: {} }));

interface Row {
  id: string;
  email: string;
  email_optin: string;
}
let rows: Row[] = [];
vi.mock("@noctusai/lib/components", () => ({
  ResourceManager: (p: {
    columns: Array<{ key: string; render?: (r: Row) => ReactNode }>;
    rowActions?: (r: Row, reload: () => void) => ReactNode;
  }) => (
    <div data-testid="rm">
      {rows.map((r) => (
        <div key={r.id} data-testid={`row-${r.id}`}>
          {p.columns.find((c) => c.key === "email_optin")?.render?.(r)}
          {p.rowActions?.(r, () => {})}
        </div>
      ))}
    </div>
  ),
}));

let resendImpl: (id: string) => Promise<unknown> = async () => ({});
const importMutate = vi.fn();
vi.mock("@/hooks/useEmailMarketing", async () => {
  const { useMutation } = await import("@tanstack/react-query");
  return {
    useEmContactMutations: () => ({
      importMany: { mutate: importMutate, isPending: false },
      resendConfirmation: useMutation({ mutationFn: (id: string) => resendImpl(id) }),
    }),
    useEmAi: () => ({ segmentContacts: { mutate: vi.fn(), isPending: false, isError: false, isSuccess: false } }),
  };
});

import EmailContatos from "./Contatos";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EmailContatos />
    </QueryClientProvider>,
  );
}

describe("Contatos — double opt-in", () => {
  beforeEach(() => {
    toastSuccess.mockReset();
    toastError.mockReset();
    importMutate.mockReset();
    rows = [
      { id: "p1", email: "pend@ex.com", email_optin: "pending" },
      { id: "c1", email: "conf@ex.com", email_optin: "confirmed" },
      { id: "n1", email: "none@ex.com", email_optin: "not_required" },
    ];
  });
  afterEach(cleanup);

  it("badges pending contacts and offers resend only to them", () => {
    renderPage();
    const pending = screen.getByTestId("row-p1");
    expect(pending.textContent).toContain("Aguardando confirmação");
    expect(pending.querySelector('[data-testid="contatos-resend-confirmation"]')).toBeTruthy();
    expect(screen.getByTestId("row-c1").textContent).toContain("Confirmado");
    expect(screen.getByTestId("row-c1").querySelector('[data-testid="contatos-resend-confirmation"]')).toBeNull();
    expect(screen.getByTestId("row-n1").querySelector('[data-testid="contatos-resend-confirmation"]')).toBeNull();
  });

  it("resend success toasts success", async () => {
    resendImpl = async () => ({ data: { confirmation: { sent: true, reason: null } } });
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-resend-confirmation"));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
    expect(toastError).not.toHaveBeenCalled();
  });

  it("a not-sent confirmation is an error with the backend's reason, never success", async () => {
    resendImpl = async () => ({ data: { confirmation: { sent: false, reason: "RESEND_API_KEY não configurado" } } });
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-resend-confirmation"));
    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("Confirmação não enviada.", {
        description: "RESEND_API_KEY não configurado",
      }),
    );
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it("the import dialog sends the double opt-in flag", () => {
    renderPage();
    fireEvent.click(screen.getByTestId("contatos-import-open"));
    fireEvent.change(screen.getByTestId("contatos-import-textarea"), { target: { value: "a@ex.com" } });
    fireEvent.click(screen.getByTestId("contatos-import-double-optin"));
    fireEvent.click(screen.getByTestId("contatos-import-submit"));
    expect(importMutate).toHaveBeenCalledWith(
      { contacts: [{ email: "a@ex.com" }], doubleOptIn: true },
      expect.anything(),
    );
  });
});
