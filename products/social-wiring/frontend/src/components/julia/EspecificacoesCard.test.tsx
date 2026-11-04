/**
 * Julia › Especificações do negócio — GET 200 renders each `tipo`; PUT 200 commits the answer (report mode shows
 * `invalidas` per field); PUT 422 (block mode) keeps the draft marked unsaved with per-field errors; 409
 * `agente_nao_conectado` points to the connection card; 502/503 are named; non-admin is read-only.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { EspecificacoesCard } from "./EspecificacoesCard";
import { JULIA_ESPECIFICACOES_KEY, type Especificacoes, type TipoEspecificacao } from "@/hooks/useJuliaEspecificacoes";

const decl = (chave: string, tipo: TipoEspecificacao, over: Record<string, unknown> = {}) => ({
  id: `id-${chave}`, chave, rotulo: `Rótulo ${chave}`, descricao: `Descrição ${chave}`, tipo, obrigatoria: false, exemplo: `ex-${chave}`, ...over,
});
const TIPOS: TipoEspecificacao[] = ["texto_curto", "texto", "texto_longo", "url", "dominios", "contatos", "cnpj", "creci", "horario", "duracao", "lista"];

const ESPEC: Especificacoes = {
  agent_key: "julia", version_id: "v1", versao: 3,
  declaradas: [
    decl("nome_empresa", "texto_curto", { obrigatoria: true }),
    ...TIPOS.filter((t) => t !== "texto_curto").map((t) => decl(`c_${t}`, t)),
    decl("aviso_privacidade_url", "url"),
  ],
  valores: [{ chave: "nome_empresa", valor: "Lastro", updated_at: "2026-11-04T10:00:00Z" }],
  faltando: [], invalidas: [], modo_validacao: "bloquear",
};

function erro(status: number, body: unknown) {
  return Object.assign(new Error(`[${status}] x`), { status, body });
}

function setup(opts: { get?: unknown; admin?: boolean } = {}) {
  api.get.mockImplementation(() => (opts.get instanceof Error ? Promise.reject(opts.get) : Promise.resolve(opts.get ?? ESPEC)));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><EspecificacoesCard isAdmin={opts.admin ?? true} /></QueryClientProvider>);
  return qc;
}

const lab = (chave: string) => new RegExp(`^Rótulo ${chave}\\*?$`);
const SLOW = { timeout: 6000 };

beforeEach(() => Object.values(api).forEach((f) => f.mockReset()));
afterEach(cleanup);

describe("GET 200", () => {
  it("skeleton first, then one field per declaration with rotulo, descricao and exemplo", async () => {
    setup();
    expect(screen.getByTestId("espec-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("espec-form")).toBeTruthy();
    for (const d of ESPEC.declaradas) {
      expect(screen.getByLabelText(new RegExp(`^${d.rotulo}\\*?$`))).toBeTruthy();
    }
    const nome = screen.getByLabelText(lab("nome_empresa")) as HTMLInputElement;
    expect(nome.value).toBe("Lastro");
    expect(nome.placeholder).toBe("Ex.: ex-nome_empresa");
    expect(screen.getByText(/Descrição nome_empresa/)).toBeTruthy();
  });

  it("renders each tipo with the right control", async () => {
    setup();
    await screen.findByTestId("espec-form");
    const el = (t: string) => screen.getByLabelText(lab(`c_${t}`)) as HTMLInputElement | HTMLTextAreaElement;
    expect(el("texto_longo").tagName).toBe("TEXTAREA");
    expect(el("dominios").tagName).toBe("TEXTAREA");
    expect(el("lista").tagName).toBe("TEXTAREA");
    expect(el("url").tagName).toBe("INPUT");
    expect((el("url") as HTMLInputElement).type).toBe("url");
    expect(el("cnpj").getAttribute("inputmode")).toBe("numeric");
    expect(screen.getByText(/Um domínio por linha/)).toBeTruthy();
  });

  it("the SW-derived privacy URL is read-only", async () => {
    setup();
    await screen.findByTestId("espec-form");
    expect((screen.getByLabelText(lab("aviso_privacidade_url")) as HTMLInputElement).disabled).toBe(true);
  });

  it("flags a required field that is missing", async () => {
    setup({ get: { ...ESPEC, valores: [], faltando: ["nome_empresa"] } });
    expect((await screen.findByTestId("espec-problema-nome_empresa")).textContent).toContain("Obrigatório");
  });

  it("empty: no declarations", async () => {
    setup({ get: { ...ESPEC, declaradas: [], valores: [] } });
    expect(await screen.findByTestId("espec-vazio")).toBeTruthy();
  });

  it("accepts the {data} envelope too", async () => {
    setup({ get: { data: ESPEC } });
    expect(await screen.findByTestId("espec-form")).toBeTruthy();
  });
});

describe("who last changed a value", () => {
  it("shows 'Alterado por <nome> em <data>' when provided and hides the line when absent", async () => {
    setup({ get: { ...ESPEC, valores: [{ chave: "nome_empresa", valor: "Lastro", updated_at: "2026-11-04T10:00:00Z", updated_by_nome: "Ana Dona" }] } });
    const t = (await screen.findByTestId("espec-alterado-nome_empresa")).textContent!;
    expect(t).toContain("Alterado por Ana Dona em ");
    expect(screen.queryByTestId("espec-alterado-c_url")).toBeNull();
  });

  it("null or missing nome shows nothing", async () => {
    setup({ get: { ...ESPEC, valores: [{ chave: "nome_empresa", valor: "Lastro", updated_at: "2026-11-04T10:00:00Z", updated_by_nome: null }] } });
    await screen.findByTestId("espec-form");
    expect(screen.queryByTestId("espec-alterado-nome_empresa")).toBeNull();
  });
});

describe("editing is a draft until the server accepts it", () => {
  it("says 'não salvas' while dirty and the save is disabled while clean", async () => {
    setup();
    const nome = (await screen.findByLabelText(lab("nome_empresa"))) as HTMLInputElement;
    expect((screen.getByTestId("espec-salvar") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByTestId("espec-nao-salvo")).toBeNull();
    fireEvent.change(nome, { target: { value: "Lastro Imóveis" } });
    expect(screen.getByTestId("espec-nao-salvo").textContent).toContain("não salvas");
    expect((screen.getByTestId("espec-salvar") as HTMLButtonElement).disabled).toBe(false);
  });

  it("PUT 200 sends every declared key, commits the answer to the cache and clears the draft", async () => {
    const resposta: Especificacoes = { ...ESPEC, valores: [{ chave: "nome_empresa", valor: "Lastro Imóveis", updated_at: "2026-11-04T11:00:00Z" }] };
    api.put.mockImplementation(async () => {
      api.get.mockResolvedValue(resposta); // the background settle re-reads: it now agrees with the commit
      return resposta;
    });
    const qc = setup();
    fireEvent.change(await screen.findByLabelText(lab("nome_empresa")), { target: { value: "Lastro Imóveis" } });
    fireEvent.change(screen.getByLabelText(lab("c_url")), { target: { value: "" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/api/julia/especificacoes");
    expect(body.valores.nome_empresa).toBe("Lastro Imóveis");
    expect(Object.keys(body.valores)).toHaveLength(ESPEC.declaradas.length);
    await waitFor(() => expect((qc.getQueryData(JULIA_ESPECIFICACOES_KEY) as Especificacoes).valores[0].valor).toBe("Lastro Imóveis"));
    await waitFor(() => expect(screen.queryByTestId("espec-nao-salvo")).toBeNull());
  });

  it("report mode: a 200 with `invalidas` shows them per field", async () => {
    const resposta = {
      ...ESPEC,
      valores: [{ chave: "nome_empresa", valor: "x", updated_at: null }],
      invalidas: [{ chave: "c_cnpj", codigo: "cnpj_invalido", motivo: "digito", mensagem: "CNPJ inválido." }],
      modo_validacao: "reportar",
    };
    api.put.mockImplementation(async () => {
      api.get.mockResolvedValue(resposta);
      return resposta;
    });
    setup();
    fireEvent.change(await screen.findByLabelText(lab("nome_empresa")), { target: { value: "x" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    expect((await screen.findByTestId("espec-problema-c_cnpj")).textContent).toBe("CNPJ inválido.");
  });
});

describe("PUT 422 (block mode)", () => {
  it("keeps the draft, marks it unsaved and names each field", async () => {
    api.put.mockRejectedValue(erro(422, {
      code: "especificacao_invalida", detail: "invalid",
      violacoes: [{ chave: "c_url", codigo: "url_invalida", motivo: "esquema", mensagem: "Use uma URL https." }],
    }));
    setup();
    fireEvent.change(await screen.findByLabelText(lab("c_url")), { target: { value: "ftp://x" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    expect((await screen.findByTestId("espec-problema-c_url")).textContent).toBe("Use uma URL https.");
    expect((screen.getByLabelText(lab("c_url")) as HTMLInputElement).value).toBe("ftp://x");
    expect(screen.getByTestId("espec-nao-salvo")).toBeTruthy();
    expect(screen.getByTestId("espec-erro-salvar").textContent).toContain("Nada foi salvo");
    expect(screen.getByLabelText(lab("c_url")).getAttribute("aria-invalid")).toBe("true");
  });

  it("also reads violacoes nested under detail", async () => {
    api.put.mockRejectedValue(erro(422, { detail: { code: "x", violacoes: [{ chave: "c_cnpj", codigo: "c", motivo: "m", mensagem: "CNPJ ruim." }] } }));
    setup();
    fireEvent.change(await screen.findByLabelText(lab("c_cnpj")), { target: { value: "1" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    expect((await screen.findByTestId("espec-problema-c_cnpj")).textContent).toBe("CNPJ ruim.");
  });
});

describe("named refusals", () => {
  it("409 agente_nao_conectado on read points to the connection card", async () => {
    setup({ get: erro(409, { error: { code: "agente_nao_conectado", message: "m" } }) });
    const box = await screen.findByTestId("espec-erro");
    expect(box.textContent).toContain("Conexão com a plataforma");
    expect(screen.getByTestId("espec-ver-conexao").getAttribute("href")).toBe("#conexao-plataforma");
  });

  it("409 agente_nao_conectado on save shows the same pointer sentence", async () => {
    api.put.mockRejectedValue(erro(409, { error: { code: "agente_nao_conectado", message: "m" } }));
    setup();
    fireEvent.change(await screen.findByLabelText(lab("nome_empresa")), { target: { value: "z" } });
    fireEvent.click(screen.getByTestId("espec-salvar"));
    expect((await screen.findByTestId("espec-erro-salvar")).textContent).toContain("Conexão com a plataforma");
    expect(screen.getByTestId("espec-nao-salvo")).toBeTruthy();
  });

  it.each([
    [503, "agents_indisponivel", "indisponível"],
    [502, "agents_token_invalido", "suporte NoctusAI para reconectar"],
  ])("%s %s on read is a named error state with retry", async (status, code, texto) => {
    setup({ get: erro(status, { error: { code, message: "m" } }) });
    const box = await screen.findByTestId("espec-erro", {}, SLOW);
    expect(box.getAttribute("data-codigo")).toBe(code);
    expect(box.textContent).toContain(texto);
    expect(screen.getByText("Tentar de novo")).toBeTruthy();
  });

  it("an unknown failure still says so (never an empty card)", async () => {
    setup({ get: new Error("boom") });
    expect((await screen.findByTestId("espec-erro", {}, SLOW)).textContent).toContain("Não foi possível carregar");
  });
});

describe("permissions and copy", () => {
  it("non-admin reads but cannot edit or save", async () => {
    setup({ admin: false });
    expect(((await screen.findByLabelText(lab("nome_empresa"))) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId("espec-salvar") as HTMLButtonElement).disabled).toBe(true);
  });

  it("says these are the business's data and Julia's core is managed by NoctusAI", async () => {
    setup();
    const t = (await screen.findByTestId("especificacoes-card")).textContent!;
    expect(t).toContain("mantido pela NoctusAI");
    expect(t.toLowerCase()).not.toContain("app de agentes");
  });
});
