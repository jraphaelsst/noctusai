/** ConversasTab — lead threads for the org admin: author labels, stage/score chips, per-thread pause/resume. */
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { installFetch } from "@/api/studio/__fixtures__/fetchMock";
import { CONVERSA, KEY } from "./juliaFixtures";
import { renderWith } from "./harness";

vi.mock("@/lib/api", async () => {
  const { createApiClient } = await import("@noctusai/lib/api");
  const { TEST_BASE_URL: base } = await import("@/api/studio/__fixtures__/fetchMock");
  return { api: createApiClient({ getBaseUrl: () => base, getAuthToken: async () => "t" }) };
});
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => true }));

import ConversasTab, { autorLabel } from "../ConversasTab";

const MSGS = [
  { id: "m1", role: "user", texto: "mensagem do lead", agent_key: null, agent_nome: null, autor_user_id: null, created_at: "2026-10-10T10:00:00Z" },
  { id: "m2", role: "assistant", texto: "resposta do agente", agent_key: KEY, agent_nome: "Agente X", autor_user_id: null, created_at: "2026-10-10T10:01:00Z" },
  { id: "m3", role: "humano", texto: "intervenção humana", agent_key: null, agent_nome: null, autor_user_id: "u1", created_at: "2026-10-10T10:02:00Z" },
  { id: "m4", role: "evento", texto: "agente pausado", agent_key: null, agent_nome: null, autor_user_id: null, created_at: "2026-10-10T10:03:00Z" },
];
const LIST = { method: "GET" as const, path: "/api/conversations/channel", body: { items: [CONVERSA], total: 1 } };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ConversasTab", () => {
  it("lists channel threads with stage/score chips and violation counts", async () => {
    const net = installFetch([LIST]);
    renderWith(<ConversasTab agentKey={KEY} />);
    expect(await screen.findByTestId(`conversa-${CONVERSA.id}`)).toBeTruthy();
    expect(screen.getByTestId("resultado-chips").textContent).toContain("Estágio: estagio_a");
    expect(screen.getByTestId("resultado-chips").textContent).toContain("2 violação(ões)");
    expect(net.calls[0].search.get("agent_key")).toBe(KEY);
  });

  it("banners a thread whose lead asked to stop (plain text, no link)", async () => {
    const evento = { id: "ev-1", tipo: "opt_out", em: "2026-10-20T14:30:00Z", motivo: "Cliente pediu para sair", origem: "agente", agent_nome: "Agente X", agent_key: KEY };
    installFetch([
      { ...LIST, body: { items: [{ ...CONVERSA, opt_out_evento: evento }], total: 1 } },
      { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS },
    ]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    const banner = await screen.findByTestId("optout-banner");
    expect(banner.textContent).toContain("O lead pediu para não ser mais contatado em");
    expect(banner.textContent).toContain("Cliente pediu para sair");
    expect(banner.textContent).toContain("Agente Agente X");
    expect(banner.querySelector("a")).toBeNull();
  });

  it("banners a reactivated lead as such", async () => {
    const evento = { id: "ev-2", tipo: "reativacao", em: "2026-10-21T09:00:00Z", motivo: "Cliente voltou a pedir contato", origem: "operador", agent_nome: null, agent_key: null };
    installFetch([
      { ...LIST, body: { items: [{ ...CONVERSA, opt_out_evento: evento }], total: 1 } },
      { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS },
    ]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    const banner = await screen.findByTestId("optout-banner");
    expect(banner.textContent).toContain("Atendimento reativado em");
    expect(banner.textContent).toContain("Cliente voltou a pedir contato");
    expect(banner.textContent).toContain("Operador");
  });

  it("shows no banner when the lead did not opt out", async () => {
    installFetch([LIST, { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS }]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    await screen.findByTestId("conversa-mensagens");
    expect(screen.queryByTestId("optout-banner")).toBeNull();
  });

  it("labels each line as lead / agente / humano / evento", async () => {
    installFetch([LIST, { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS }]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    const lista = await screen.findByTestId("conversa-mensagens");
    const rotulos = Array.from(lista.querySelectorAll("li[data-role]")).map((li) => li.querySelector("p")!.textContent);
    expect(rotulos).toEqual(["Lead", "Agente · Agente X", "Humano", "Evento"]);
    expect(autorLabel({ role: "assistant", agent_nome: null })).toBe("Agente");
  });

  it("pauses and resumes the agent in one thread, showing the server's answer", async () => {
    const participante = { agent_key: KEY, agent_nome: "Agente X", estado: "pausado", entrou_em: "2026-10-10T09:00:00Z", saiu_em: null, motivo: null, ultimo_turno_em: null, pausado_ate: null };
    const net = installFetch([
      LIST,
      { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS },
      { method: "PATCH", path: `/api/studio/threads/${CONVERSA.id}/participantes/${KEY}`, body: participante },
    ]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    fireEvent.click(await screen.findByTestId("conversa-pausar"));
    await waitFor(() => expect(screen.getByTestId("conversa-estado").textContent).toContain("pausado"));
    expect(net.calls.find((c) => c.method === "PATCH")!.body).toEqual({ estado: "pausado" });
  });

  it("shows a 409 transition refusal inline", async () => {
    installFetch([
      LIST,
      { method: "GET", path: `/api/studio/threads/${CONVERSA.id}/mensagens`, body: MSGS },
      { method: "PATCH", path: `/api/studio/threads/${CONVERSA.id}/participantes/${KEY}`, status: 409, body: { detail: "Não é possível mudar de concluido para ativo.", code: "transicao_invalida" } },
    ]);
    renderWith(<ConversasTab agentKey={KEY} />, `/?tab=conversas&conversa=${CONVERSA.id}`);
    fireEvent.click(await screen.findByTestId("conversa-retomar"));
    expect((await screen.findByTestId("conversa-erro")).textContent).toContain("Não é possível mudar");
  });

  it("empty state when the agent has no lead threads", async () => {
    installFetch([{ method: "GET", path: "/api/conversations/channel", body: { items: [], total: 0 } }]);
    renderWith(<ConversasTab agentKey={KEY} />);
    expect(await screen.findByText("Ainda não há conversas de leads com este agente.")).toBeTruthy();
  });
});
