/** ContatosPermitidosSection (inside ControlesCard) — the phone allow-list: empty = everybody, add/remove, refusals. */
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

import { ControlesCard } from "@/components/studio/ControlesCard";
import { normalizarTelefone } from "@/components/studio/ContatosPermitidosSection";

const P = `/api/studio/agents/${KEY}/controle`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  mockAdmin.mockReturnValue(true);
});

describe("normalizarTelefone", () => {
  it("keeps only digits and demands 8..15 of them", () => {
    expect(normalizarTelefone("+55 (11) 99999-0000")).toBe("+5511999990000");
    expect(normalizarTelefone("123")).toBeNull();
    expect(normalizarTelefone("abc")).toBeNull();
  });
});

describe("Contatos permitidos", () => {
  it("says an empty list answers every number", async () => {
    installFetch([{ method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: [] } }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    expect((await screen.findByTestId("contatos-permitidos-resumo")).textContent).toContain("responde qualquer número");
    expect(screen.queryByTestId("contatos-permitidos-lista")).toBeNull();
  });

  it("lists the numbers and says only they are answered", async () => {
    installFetch([{ method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: ["+5511999990000"] } }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    expect((await screen.findByTestId("contatos-permitidos-resumo")).textContent).toContain("somente a 1 número(s)");
    expect(screen.getByTestId("contato-permitido-+5511999990000")).toBeTruthy();
  });

  it("adds a normalised number with a PUT that keeps the mode", async () => {
    const net = installFetch([
      { method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: [] } },
      { method: "PUT", path: P, body: { ...CONTROLE, contatos_permitidos: ["+5511999990000"] } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Número (com DDI e DDD)"), { target: { value: "+55 (11) 99999-0000" } });
    fireEvent.click(screen.getByTestId("contato-permitido-adicionar"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: CONTROLE.modo, contatos_permitidos: ["+5511999990000"] });
  });

  it("refuses a non-phone without calling the server", async () => {
    const net = installFetch([{ method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: [] } }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Número (com DDI e DDD)"), { target: { value: "abc" } });
    fireEvent.click(screen.getByTestId("contato-permitido-adicionar"));
    expect((await screen.findByTestId("contatos-permitidos-erro")).textContent).toContain("número válido");
    expect(net.calls.some((c) => c.method === "PUT")).toBe(false);
  });

  it("removes a number (an empty list is allowed: everybody again)", async () => {
    const net = installFetch([
      { method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: ["+5511999990000"] } },
      { method: "PUT", path: P, body: { ...CONTROLE, contatos_permitidos: [] } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.click(await screen.findByLabelText("Remover +5511999990000"));
    await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
    expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: CONTROLE.modo, contatos_permitidos: [] });
  });

  it("shows the server refusal", async () => {
    installFetch([
      { method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: [] } },
      { method: "PUT", path: P, status: 422, body: { detail: "contatos_permitidos: número inválido", code: "contatos_permitidos_invalido" } },
    ]);
    renderWith(<ControlesCard agentKey={KEY} />);
    fireEvent.change(await screen.findByLabelText("Número (com DDI e DDD)"), { target: { value: "+5511999990000" } });
    fireEvent.click(screen.getByTestId("contato-permitido-adicionar"));
    expect((await screen.findByTestId("contatos-permitidos-erro")).textContent).toContain("número inválido");
  });

  it("is read-only for a non-admin member", async () => {
    mockAdmin.mockReturnValue(false);
    installFetch([{ method: "GET", path: P, body: { ...CONTROLE, contatos_permitidos: ["+55 11 *****-0000"] } }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    await screen.findByTestId("contatos-permitidos");
    expect(screen.queryByTestId("contato-permitido-adicionar")).toBeNull();
    expect(screen.queryByLabelText(/^Remover /)).toBeNull();
  });
});
