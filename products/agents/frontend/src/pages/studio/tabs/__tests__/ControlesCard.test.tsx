/** ControlesCard — the 3-state switch, the confirmation dialog and the server refusals (CONTRACT §5). */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { CONTROLE, KEY } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
const mockAdmin = vi.fn(() => true);
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockAdmin() }));

import { ControlesCard, consequencia } from "@/components/studio/ControlesCard";

const P = `/api/studio/agents/${KEY}/controle`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mockAdmin.mockReturnValue(true);
});

describe("ControlesCard", () => {
  it("shows mode, open-thread count and drain ages from the server", async () => {
    installFetch([{ method: "GET", path: P, body: CONTROLE }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    expect((await screen.findByTestId("controle-abertas")).textContent).toBe("4");
    expect(screen.getByTestId("controle-modo").textContent).toBe("Ligado");
    expect(screen.getByTestId("controle-idades").textContent).toContain("9, 2, 1, 0");
  });

  it("explains the consequence for the open conversations before turning off, then PUTs", async () => {
    const net = installFetch([
      { method: "GET", path: P, body: CONTROLE },
      { method: "PUT", path: P, body: { ...CONTROLE, modo: "desligado" } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.click(await screen.findByTestId("controle-modo-desligado"));
    expect(screen.getByTestId("controle-consequencia").textContent).toContain("4 conversa(s) aberta(s)");
    expect(net.calls.some((c) => c.method === "PUT")).toBe(false); // nothing before the confirmation
    fireEvent.click(screen.getByTestId("controle-confirmar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: "desligado" });
  });

  it("drenando asks for the idle days and sends them", async () => {
    const net = installFetch([
      { method: "GET", path: P, body: CONTROLE },
      { method: "PUT", path: P, body: { ...CONTROLE, modo: "drenando" } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.click(await screen.findByTestId("controle-modo-drenando"));
    expect(screen.getByTestId("controle-consequencia").textContent).toContain("deixa de aceitar novos leads");
    fireEvent.change(screen.getByLabelText("Dias de inatividade para encerrar"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("controle-confirmar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: "drenando", dreno_inatividade_dias: 10 });
  });

  it("keeps the dialog open and shows the server's 409 refusal", async () => {
    installFetch([
      { method: "GET", path: P, body: { ...CONTROLE, modo: "desligado" } },
      { method: "PUT", path: P, status: 409, body: { detail: "O conteúdo do agente está incompleto: nome_empresa", code: "conteudo_incompleto" } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.click(await screen.findByTestId("controle-modo-ligado"));
    fireEvent.click(screen.getByTestId("controle-confirmar"));
    expect((await screen.findByTestId("controle-erro-dialog")).textContent).toContain("conteúdo do agente está incompleto");
    expect(screen.getByTestId("controle-confirmar")).toBeTruthy();
  });

  it("is read-only for a non-admin member", async () => {
    mockAdmin.mockReturnValue(false);
    installFetch([{ method: "GET", path: P, body: CONTROLE }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    const btn = (await screen.findByTestId("controle-modo-desligado")) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("consequencia() names the drain days", () => {
    expect(consequencia("drenando", CONTROLE, 5)).toContain("5 dia(s)");
  });
});
