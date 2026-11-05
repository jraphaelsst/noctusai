/**
 * Julia › Agente — states, the WhatsApp card (#whatsapp), the read-only platform connection, the business specs card,
 * the line list (on/off + handoff target), every refusal code's pt-BR message, handoff options (owner/admin only), and
 * the privacy notice. No behaviour is configured here and nothing sends the user to the agents app.
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
};
const CONEXAO = {
  status: "ativa", conectada: true, motivo: null, token_prefix: "noc_ab12", token_mascarado: "noc_…9f3a",
  conectada_em: "2026-11-04T17:50:00Z", agent_key: "julia", verificada_em: "2026-11-04T18:00:00Z",
  ultima_falha_em: null, expires_at: null,
};
const ESPEC = {
  agent_key: "julia", version_id: "v1", versao: 3,
  declaradas: [{ id: "i1", chave: "nome_empresa", rotulo: "Nome da empresa", descricao: "Como a Julia se apresenta.", tipo: "texto_curto", obrigatoria: true, exemplo: "Lastro" }],
  valores: [{ chave: "nome_empresa", valor: "Lastro", updated_at: null }], faltando: [], invalidas: [], modo_validacao: "bloquear",
};
const WA_STATUS = { connection_id: "c1", status: "SCAN_QR_CODE", paired: false, me_id: null, me_name: null, session: "default", error: null };
const AGENTE = {
  conexoes: [],
  conexao_plataforma: CONEXAO,
  status_agente: { agent_key: "julia", nome: "Julia", ativo: true, versao_ativa: 4, provider: "anthropic", model: "claude-x", llm_configurado: true },
  erro: null,
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

function setup(agente: unknown = AGENTE, aviso: unknown = AVISO, roteamento: unknown = ROTEAMENTO, espec: unknown = ESPEC) {
  api.get.mockImplementation((url: string) => {
    if (url === "/api/julia/roteamento") return roteamento instanceof Error ? Promise.reject(roteamento) : Promise.resolve({ data: roteamento });
    if (url === "/api/julia/agente") return agente instanceof Error ? Promise.reject(agente) : Promise.resolve({ data: agente });
    if (url === "/api/julia/agente/aviso") return Promise.resolve({ data: aviso });
    if (url === "/api/julia/especificacoes") return espec instanceof Error ? Promise.reject(espec) : Promise.resolve(espec);
    if (url.startsWith("/api/whatsapp/connections/")) return Promise.resolve(url.endsWith("/qr") ? { connection_id: "c1", scannable: false, status: "SCAN_QR_CODE", png_base64: null } : WA_STATUS);
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

  it("never sends the user to the agents app", async () => {
    setup();
    await screen.findByTestId("julia-roteamento-card");
    expect(screen.queryByTestId("configurar-julia-link")).toBeNull();
    expect(screen.queryByTestId("configurar-julia-indisponivel")).toBeNull();
  });
});

describe("Platform connection card — read-only", () => {
  it("shows the masked token, the status badge and the agent status", async () => {
    setup();
    expect((await screen.findByTestId("conexao-token")).textContent).toBe("noc_…9f3a");
    expect(screen.getByTestId("conexao-status").textContent).toContain("Conectada");
    const st = screen.getByTestId("agent-status").textContent!;
    expect(st).toContain("Julia");
    expect(st).toContain("4");
    expect(st).toContain("anthropic / claude-x");
    expect(st).toContain("Configurada");
  });

  it("not configured: says what to do and offers no token field", async () => {
    setup({ ...AGENTE, conexao_plataforma: { ...CONEXAO, status: "nao_configurada", conectada: false, token_mascarado: null }, status_agente: null, erro: "Julia ainda não conectada." });
    expect((await screen.findByTestId("conexao-ajuda")).textContent).toContain("suporte NoctusAI");
    expect(screen.getByTestId("link-erro").textContent).toContain("Julia ainda não conectada.");
    expect(screen.queryByTestId("agent-status")).toBeNull();
    expect(screen.queryByLabelText(/token/i)).toBeNull();
    expect(screen.queryByTestId("salvar-token")).toBeNull();
  });

  it("never offers to paste, replace or save a token, and never PUTs one", async () => {
    setup();
    await screen.findByTestId("agents-link-card");
    expect(screen.getByTestId("agents-link-card").querySelector("input")).toBeNull();
    expect(api.put).not.toHaveBeenCalled();
  });

  it("Testar conexão is admin-only", async () => {
    h.admin = false;
    setup();
    await screen.findByTestId("agents-link-card");
    expect(screen.queryByTestId("conexao-testar")).toBeNull();
  });
});

describe("New cards on the page", () => {
  it("WhatsApp da Julia is the #whatsapp anchor, and the specs card is present", async () => {
    setup();
    const card = await screen.findByTestId("whatsapp-julia-card");
    expect(card.id).toBe("whatsapp");
    expect(await screen.findByTestId("especificacoes-card")).toBeTruthy();
    expect(await screen.findByTestId("espec-form")).toBeTruthy();
  });

  it("a failing specs read degrades that card only", async () => {
    setup(AGENTE, AVISO, ROTEAMENTO, new Error("boom"));
    expect(await screen.findByTestId("julia-roteamento-card")).toBeTruthy();
    expect(await screen.findByTestId("espec-erro", {}, { timeout: 6000 })).toBeTruthy();
    expect(screen.getByTestId("whatsapp-julia-card")).toBeTruthy();
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

  it("no authorized-numbers gate: a line with none can still be switched on", async () => {
    setup(AGENTE, AVISO, { ...ROTEAMENTO, linhas: [{ ...LINHA, numeros_autorizados: 0 }] });
    expect(((await screen.findByRole("switch")) as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("motivo-desabilitado")).toBeNull();
  });

  it("explains who gets whom (new chats / pre-existing; no One Chat)", async () => {
    setup();
    const t = (await screen.findByTestId("julia-roteamento-card")).textContent!;
    expect(t).not.toContain("One Chat");
    expect(t).toContain("NOVAS");
    expect(t).toContain("já existiam");
  });

  it.each([
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
