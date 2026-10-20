/**
 * Julia › Agente (routing only) — states, the agents-link status, the line list (on/off + handoff target), every
 * refusal code's pt-BR message, the disabled-switch reason, handoff options (owner/admin only), the write-only token,
 * the "Configurar a Julia no app de agentes" link, and the privacy notice. No behaviour is configured here.
 * `@/lib/api` is the seam (real hooks + real components); `useIsOrgAdmin` / the team list are the only other fakes.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const h = vi.hoisted(() => ({ admin: true, team: { data: [] as unknown[], isError: false } }));
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), patch: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/lib/design-system", () => ({ useIsOrgAdmin: () => h.admin }));
vi.mock("@/hooks/useTeam", () => ({ useTeamMembers: () => h.team }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import JuliaAgente from "./Agente";

const LINHA = {
  connection_id: "c1",
  label: "Comercial",
  alimenta: false,
  alimenta_desde: null,
  numeros_autorizados: 2,
  destino_handoff_user_id: null,
};
const ROTEAMENTO = {
  linhas: [LINHA],
  destino_handoff_padrao: { tipo: "dono_da_organizacao", user_id: "u1" },
  agents_url: "https://agents.example.test/",
};
const AGENTE = {
  conexoes: [],
  token_configurado: true,
  status_agente: { agent_key: "julia", nome: "Julia", ativo: true, versao_ativa: 4, provider: "anthropic", model: "claude-x", llm_configurado: true },
  erro: null,
  agents_url: "https://agents.example.test/",
};
const AVISO = {
  slug: "empresa-x", titulo: "Aviso de privacidade", empresa_nome: "Empresa X", contato_email: "a@x.test",
  contato_whatsapp: null, mensagem_inicial: "Olá, sou da {empresa}. Veja {link}", incompleto: false,
  secoes: [{ n: "1", title: "Controlador", blocks: [{ p: "Texto." }, { ul: ["a", "b"] }] }],
  versao: 1, atualizado_em: "2026-10-14T00:00:00Z",
};

function serverError(code: string, status = 409) {
  return Object.assign(new Error(`[${status}] x`), { status, body: { error: { code, message: "msg do servidor" } } });
}

function setup(agente: unknown = AGENTE, aviso: unknown = AVISO, roteamento: unknown = ROTEAMENTO) {
  api.get.mockImplementation((url: string) => {
    if (url === "/api/julia/roteamento") return roteamento instanceof Error ? Promise.reject(roteamento) : Promise.resolve({ data: roteamento });
    if (url === "/api/julia/agente") return agente instanceof Error ? Promise.reject(agente) : Promise.resolve({ data: agente });
    if (url === "/api/julia/agente/aviso") return Promise.resolve({ data: aviso });
    return Promise.reject(new Error(`unexpected GET ${url}`));
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><JuliaAgente /></QueryClientProvider>);
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  h.admin = true;
  h.team = { data: [], isError: false };
});
afterEach(cleanup);

describe("Julia › Agente — states", () => {
  it("shows a skeleton first, then the cards", async () => {
    setup();
    expect(screen.getByTestId("agente-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("julia-roteamento-card")).toBeTruthy();
    expect(screen.queryByTestId("agente-skeleton")).toBeNull();
    expect(await screen.findByTestId("agents-link-card")).toBeTruthy();
    expect(await screen.findByTestId("aviso-card")).toBeTruthy();
  });

  it("shows an error state with retry when the routing query fails", async () => {
    setup(AGENTE, AVISO, new Error("boom"));
    expect(await screen.findByTestId("agente-erro")).toBeTruthy();
    expect(screen.getByText("Tentar de novo")).toBeTruthy();
  });

  it("empty: no lines points to Conexões", async () => {
    setup(AGENTE, AVISO, { ...ROTEAMENTO, linhas: [] });
    expect(await screen.findByTestId("sem-linhas")).toBeTruthy();
  });

  it("a failing link-status query degrades that card only, the routing still renders", async () => {
    setup(new Error("boom"));
    expect(await screen.findByTestId("julia-roteamento-card")).toBeTruthy();
    expect(await screen.findByTestId("agents-link-erro")).toBeTruthy();
  });

  it("is ROUTING ONLY: no behaviour setting, prompt or rule text is rendered", async () => {
    setup();
    await screen.findByTestId("julia-roteamento-card");
    const t = document.body.textContent!.toLowerCase();
    for (const w of ["prompt", "instruç", "persona", "tom de voz", "dica"]) expect(t).not.toContain(w);
  });

  it("links to configure Julia in the agents app", async () => {
    setup();
    const a = (await screen.findByTestId("configurar-julia-link")) as HTMLAnchorElement;
    expect(a.textContent).toContain("Configurar a Julia no app de agentes");
    expect(a.href).toBe("https://agents.example.test/studio/julia");
  });

  it("says so when the agents URL is unresolvable", async () => {
    setup({ ...AGENTE, agents_url: null }, AVISO, { ...ROTEAMENTO, agents_url: null });
    expect(await screen.findByTestId("configurar-julia-indisponivel")).toBeTruthy();
  });
});

describe("Agents link — status + token", () => {
  it("shows token state, Julia status and the Agents link", async () => {
    setup();
    expect((await screen.findByTestId("token-status")).textContent).toContain("Token configurado");
    const st = screen.getByTestId("agent-status").textContent!;
    expect(st).toContain("Julia");
    expect(st).toContain("4");
    expect(st).toContain("anthropic / claude-x");
    expect(st).toContain("Configurada");
  });

  it("shows the link error and a missing token", async () => {
    setup({ ...AGENTE, token_configurado: false, status_agente: null, erro: "Token do Agents não configurado." });
    expect((await screen.findByTestId("token-status")).textContent).toContain("Token não configurado");
    expect(screen.getByTestId("link-erro").textContent).toContain("Token do Agents não configurado.");
    expect(screen.queryByTestId("agent-status")).toBeNull();
  });

  it("saves the token, never echoes it, and clears the input", async () => {
    api.put.mockResolvedValue(null);
    setup();
    const input = (await screen.findByLabelText("Substituir token")) as HTMLInputElement;
    expect(input.type).toBe("password");
    fireEvent.change(input, { target: { value: "pk_super_secreto_123" } });
    fireEvent.click(screen.getByTestId("salvar-token"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/agente/token", { token: "pk_super_secreto_123" }));
    await waitFor(() => expect(input.value).toBe(""));
    expect(document.body.textContent).not.toContain("pk_super_secreto_123");
  });

  it.each([
    ["token_invalido", 422, "O Agents recusou este token."],
    ["agents_indisponivel", 502, "Não foi possível validar o token com o Agents agora."],
  ])("token error %s -> pt-BR message", async (code, status, texto) => {
    api.put.mockRejectedValue(serverError(code, status));
    setup();
    fireEvent.change(await screen.findByLabelText("Substituir token"), { target: { value: "token-comprido-1" } });
    fireEvent.click(screen.getByTestId("salvar-token"));
    expect((await screen.findByTestId("token-erro")).textContent).toContain(texto);
  });

  it("non-admin cannot edit the token", async () => {
    h.admin = false;
    setup();
    await screen.findByTestId("agents-link-card");
    expect(screen.queryByLabelText("Substituir token")).toBeNull();
  });
});

describe("Line list — routing switch and handoff target", () => {
  it("turning a line on sends the routing PUT", async () => {
    api.put.mockResolvedValue({ data: {} });
    setup();
    fireEvent.click(await screen.findByRole("switch"));
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/api/julia/roteamento/linhas/c1", { alimenta: true }),
    );
  });

  it("labels the switch as the line feeding Julia", async () => {
    setup();
    expect((await screen.findByLabelText(/Esta linha atende leads com a Julia/)).getAttribute("role")).toBe("switch");
  });

  it("disables the switch with the reason when there are no authorized numbers", async () => {
    setup(AGENTE, AVISO, { ...ROTEAMENTO, linhas: [{ ...LINHA, numeros_autorizados: 0 }] });
    const sw = (await screen.findByRole("switch")) as HTMLButtonElement;
    expect(sw.disabled).toBe(true);
    expect(screen.getByTestId("motivo-desabilitado").textContent).toContain("número autorizado");
  });

  it("an already-on switch stays turn-off-able even with an emptied list", async () => {
    setup(AGENTE, AVISO, { ...ROTEAMENTO, linhas: [{ ...LINHA, alimenta: true, numeros_autorizados: 0 }] });
    expect(((await screen.findByRole("switch")) as HTMLButtonElement).disabled).toBe(false);
  });

  it("explains who gets whom (One Chat / new chats / pre-existing)", async () => {
    setup();
    const t = (await screen.findByTestId("julia-roteamento-card")).textContent!;
    expect(t).toContain("One Chat");
    expect(t).toContain("NOVAS");
    expect(t).toContain("já existiam");
  });

  it.each([
    ["authorized_numbers_required", 409, "número autorizado"],
    ["webhook_hmac_required", 409, "HMAC"],
    ["aviso_incompleto", 409, "aviso de privacidade ainda está incompleto"],
    ["url_publica_indisponivel", 409, "link público"],
    ["snapshot_falhou", 502, "Não foi possível ler as conversas existentes deste número; a Julia continua desligada."],
    ["destinatario_invalido", 422, "owner ou admin"],
  ])("switch error %s -> pt-BR message", async (code, status, texto) => {
    api.put.mockRejectedValue(serverError(code, status));
    setup();
    fireEvent.click(await screen.findByRole("switch"));
    expect((await screen.findByTestId("linha-erro")).textContent).toContain(texto);
  });

  it("handoff select defaults to the org owner, lists ONLY owner/admin members, and saves null for the default", async () => {
    h.team = {
      isError: false,
      data: [
        { id: "u1", nome: "Ana Dona", email: "a@x", org_role: "owner" },
        { id: "u2", nome: "Beto Admin", email: "b@x", org_role: "admin" },
        { id: "u3", nome: "Caio Moderador", email: "c@x", org_role: "moderador" },
      ],
    };
    api.put.mockResolvedValue({ data: {} });
    setup(AGENTE, AVISO, { ...ROTEAMENTO, linhas: [{ ...LINHA, destino_handoff_user_id: "u2" }] });
    const select = (await screen.findByLabelText(/avisar/)) as HTMLSelectElement;
    const options = within(select).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Dono da organização (padrão)", "Ana Dona", "Beto Admin"]);
    expect(select.value).toBe("u2");
    fireEvent.change(select, { target: { value: "" } });
    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith("/api/julia/roteamento/linhas/c1", {
        alimenta: false,
        destino_handoff_user_id: null,
      }),
    );
  });

  it("non-admin sees everything read-only", async () => {
    h.admin = false;
    setup();
    expect(((await screen.findByRole("switch")) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText(/avisar/) as HTMLSelectElement).disabled).toBe(true);
  });
});

describe("Privacy notice (legal, lives in SW)", () => {
  it("renders the editor and the public-page link", async () => {
    setup();
    expect(((await screen.findByLabelText("Empresa (controlador)")) as HTMLInputElement).value).toBe("Empresa X");
    expect((screen.getByLabelText("Texto da seção 1") as HTMLTextAreaElement).value).toBe("Texto.\n\n- a\n- b");
    expect(screen.getByText(/obrigatório/)).toBeTruthy();
    expect((screen.getByTestId("aviso-pagina-publica") as HTMLAnchorElement).getAttribute("href")).toBe("/privacidade/empresa-x");
  });

  it("shows the incompleto warning", async () => {
    setup(AGENTE, { ...AVISO, incompleto: true, empresa_nome: null });
    expect(await screen.findByTestId("aviso-incompleto")).toBeTruthy();
  });

  it("saves the edited notice with blocks rebuilt from the text", async () => {
    api.put.mockResolvedValue({ data: { ...AVISO, versao: 2 } });
    setup();
    fireEvent.change(await screen.findByLabelText("Título"), { target: { value: "Novo título" } });
    fireEvent.change(screen.getByLabelText("Texto da seção 1"), { target: { value: "Um parágrafo.\n\n- x\n- y" } });
    fireEvent.click(screen.getByTestId("salvar-aviso"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/api/julia/agente/aviso");
    expect(body).toMatchObject({
      titulo: "Novo título",
      empresa_nome: "Empresa X",
      contato_whatsapp: null,
      secoes: [{ n: "1", title: "Controlador", blocks: [{ p: "Um parágrafo." }, { ul: ["x", "y"] }] }],
    });
  });

  it("blocks a message without {link} client-side with the pt-BR message (no request)", async () => {
    setup();
    fireEvent.change(await screen.findByLabelText("Mensagem inicial"), { target: { value: "Olá sem link" } });
    fireEvent.click(screen.getByTestId("salvar-aviso"));
    expect((await screen.findByTestId("aviso-erro-salvar")).textContent).toContain("{link}");
    expect(api.put).not.toHaveBeenCalled();
  });

  it.each([
    ["link_obrigatorio", "{link}"],
    ["secoes_invalidas", "parágrafo ou uma lista"],
  ])("server error %s -> pt-BR message", async (code, texto) => {
    api.put.mockRejectedValue(serverError(code, 422));
    setup();
    await screen.findByLabelText("Título");
    fireEvent.click(screen.getByTestId("salvar-aviso"));
    expect((await screen.findByTestId("aviso-erro-salvar")).textContent).toContain(texto);
  });

  it("non-admin gets a read-only form", async () => {
    h.admin = false;
    setup();
    expect(((await screen.findByLabelText("Título")) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByTestId("salvar-aviso")).toBeNull();
  });
});
