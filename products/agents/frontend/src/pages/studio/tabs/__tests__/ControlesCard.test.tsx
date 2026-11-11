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

  it("an instance shows the core's testing switch as a read-only badge, with no switch or list", async () => {
    installFetch([{ method: "GET", path: P, body: { ...CONTROLE, modo_avaliacao: true, avaliacao_herdada: true, avaliacao_usuarios: [] } }]);
    renderWith(<ControlesCard agentKey={KEY} />);
    expect((await screen.findByTestId("controle-avaliacao-badge")).textContent).toBe("Julia em modo de avaliação");
    expect(screen.getByTestId("controle-avaliacao-herdada").textContent).toContain("núcleo da Julia");
    expect(screen.queryByTestId("controle-avaliacao-switch")).toBeNull();
    expect(screen.queryByTestId("controle-avaliacao-lista")).toBeNull();
  });

  it("consequencia() names the drain days", () => {
    expect(consequencia("drenando", CONTROLE, 5)).toContain("5 dia(s)");
  });

  describe("modo de avaliação", () => {
    const M = `/api/team`;
    const MEMBROS = { data: [
      { id: "u1", nome: "Raphael", email: "r@x.com", org_role: "owner", created_at: "" },
      { id: "u2", nome: "Maria", email: "m@x.com", org_role: "admin", created_at: "" },
    ] };
    const R1 = { usuario_id: "u1", nome: "Raphael", telefone: "+5511999998888" };
    const R2 = { usuario_id: "u2", nome: "Maria", telefone: null };

    it("disables the switch with a hint while no chosen member has a phone", async () => {
      installFetch([
        { method: "GET", path: P, body: { ...CONTROLE, modo_avaliacao: false, avaliacao_usuarios: ["u2"], avaliacao_resolvidos: [R2] } },
        { method: "GET", path: M, body: MEMBROS },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      const sw = await screen.findByTestId("controle-avaliacao-switch");
      expect((sw as HTMLButtonElement).disabled).toBe(true);
      expect(screen.getByTestId("controle-avaliacao-dica")).toBeTruthy();
      expect(screen.queryByTestId("controle-avaliacao-badge")).toBeNull();
    });

    it("shows the no-WhatsApp chip linking to the core account settings", async () => {
      installFetch([
        { method: "GET", path: P, body: { ...CONTROLE, avaliacao_usuarios: ["u1", "u2"], avaliacao_resolvidos: [R1, R2] } },
        { method: "GET", path: M, body: MEMBROS },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      const chip = await screen.findByTestId("controle-avaliacao-sem-whatsapp-u2");
      expect(chip.textContent).toBe("Sem WhatsApp — cadastre no noc");
      expect(chip.getAttribute("href")).toMatch(/\/settings$/);
      expect(screen.getByText("+5511999998888")).toBeTruthy();
      expect((screen.getByTestId("controle-avaliacao-switch") as HTMLButtonElement).disabled).toBe(false);
    });

    it("adds a member from the picker (user id sent, current modo)", async () => {
      const net = installFetch([
        { method: "GET", path: P, body: { ...CONTROLE, modo_avaliacao: false, avaliacao_usuarios: [], avaliacao_resolvidos: [] } },
        { method: "GET", path: M, body: MEMBROS },
        { method: "PUT", path: P, body: { ...CONTROLE, modo_avaliacao: false, avaliacao_usuarios: ["u1"], avaliacao_resolvidos: [R1] } },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      const sel = await screen.findByLabelText("Membro permitido");
      await screen.findByText("Maria");
      fireEvent.change(sel, { target: { value: "u1" } });
      fireEvent.click(screen.getByTestId("controle-avaliacao-adicionar"));
      await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
      expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: "ligado", avaliacao_usuarios: ["u1"] });
    });

    it("removes a member", async () => {
      const net = installFetch([
        { method: "GET", path: P, body: { ...CONTROLE, modo_avaliacao: false, avaliacao_usuarios: ["u1", "u2"], avaliacao_resolvidos: [R1, R2] } },
        { method: "GET", path: M, body: MEMBROS },
        { method: "PUT", path: P, body: { ...CONTROLE, modo_avaliacao: false, avaliacao_usuarios: ["u2"], avaliacao_resolvidos: [R2] } },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      fireEvent.click(await screen.findByLabelText("Remover Raphael"));
      await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
      expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: "ligado", avaliacao_usuarios: ["u2"] });
    });

    it("shows the amber badge counting members with a phone, and turns it off", async () => {
      const on = { ...CONTROLE, modo_avaliacao: true, avaliacao_usuarios: ["u1", "u2"], avaliacao_resolvidos: [R1, R2] };
      const net = installFetch([
        { method: "GET", path: P, body: on },
        { method: "GET", path: M, body: MEMBROS },
        { method: "PUT", path: P, body: { ...on, modo_avaliacao: false } },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      expect((await screen.findByTestId("controle-avaliacao-badge")).textContent).toBe("Em avaliação — responde só a 1 número(s)");
      fireEvent.click(screen.getByTestId("controle-avaliacao-switch"));
      await waitFor(() => expect(net.calls.some((c) => c.method === "PUT")).toBe(true));
      expect(net.calls.find((c) => c.method === "PUT")!.body).toEqual({ modo: "ligado", modo_avaliacao: false, avaliacao_usuarios: ["u1", "u2"] });
    });

    it("shows the server's avaliacao_sem_telefone refusal", async () => {
      installFetch([
        { method: "GET", path: P, body: { ...CONTROLE, avaliacao_usuarios: ["u1"], avaliacao_resolvidos: [R1] } },
        { method: "GET", path: M, body: MEMBROS },
        { method: "PUT", path: P, status: 422, body: { detail: "Nenhum membro escolhido tem WhatsApp cadastrado no noc.", code: "avaliacao_sem_telefone" } },
      ]);
      renderWith(<ControlesCard agentKey={KEY} />);
      fireEvent.click(await screen.findByTestId("controle-avaliacao-switch"));
      expect((await screen.findByTestId("controle-erro")).textContent).toContain("WhatsApp");
    });
  });
});
