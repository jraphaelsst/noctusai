/**
 * Cliente HTTP.
 *
 * Dois comportamentos valem teste: o token do Supabase precisa entrar no
 * header sozinho (senão toda rota protegida devolve 401 e o bug aparece
 * longe daqui), e o `detail` do FastAPI precisa virar `Error.message` — é
 * esse texto que a UI mostra no toast. Um 422 do Pydantic traz `detail` como
 * lista de objetos, não string; jogar `[object Object]` na tela seria pior
 * que não mostrar nada.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const getSession = vi.fn();

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: () => getSession() } },
}));

const { api, qs } = await import("@/lib/api");

// House single-container model: same-origin by default under vitest (no
// `VITE_BACKEND_API_URL` env in the test env) → BASE resolves to "" and
// requests are relative to the current origin. See `src/lib/api.ts`.
const BASE = "";

function respostaFake(
  body: unknown,
  { status = 200, jsonThrows = false }: { status?: number; jsonThrows?: boolean } = {}
) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => {
      if (jsonThrows) throw new SyntaxError("Unexpected end of JSON input");
      return body;
    },
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  getSession.mockResolvedValue({ data: { session: null } });
});

// ── qs ────────────────────────────────────────────────────────────────────

describe("qs", () => {
  it("sem parâmetros devolve string vazia", () => {
    expect(qs()).toBe("");
    expect(qs({})).toBe("");
  });

  it("monta a query", () => {
    expect(qs({ status: "atrasado" })).toBe("?status=atrasado");
  });

  it("descarta undefined, null e string vazia", () => {
    expect(qs({ a: "1", b: undefined, c: null, d: "" })).toBe("?a=1");
  });

  it("zero é valor legítimo e não é descartado", () => {
    expect(qs({ pagina: 0 })).toBe("?pagina=0");
  });

  it("escapa o que precisa", () => {
    expect(qs({ nome: "Imobiliária Alfa" })).toBe("?nome=Imobili%C3%A1ria+Alfa");
  });

  it("tudo vazio devolve string vazia em vez de um '?' solto", () => {
    expect(qs({ a: undefined, b: null })).toBe("");
  });
});

// ── request ───────────────────────────────────────────────────────────────

describe("api", () => {
  it("faz GET no host do backend e devolve o corpo", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respostaFake([{ id: "1" }]) as any);

    await expect(api.get("/api/clientes")).resolves.toEqual([{ id: "1" }]);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/api/clientes`);
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
  });

  it("anexa o bearer quando há sessão", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "jwt-de-teste" } },
    });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respostaFake({}) as any);

    await api.get("/api/me");

    const headers = (fetchMock.mock.calls[0][1]?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-de-teste");
  });

  it("sem sessão não manda header de autorização", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respostaFake({}) as any);

    await api.get("/api/health");

    const headers = (fetchMock.mock.calls[0][1]?.headers ?? {}) as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("serializa o corpo do POST", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respostaFake({ id: "novo" }, { status: 201 }) as any);

    await api.post("/api/clientes", { nome: "Alfa" });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ nome: "Alfa" }));
    expect((init?.headers as any)["Content-Type"]).toBe("application/json");
  });

  it("204 devolve undefined sem tentar ler JSON", async () => {
    const json = vi.fn();
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      status: 204,
      ok: true,
      json,
    } as any);

    await expect(api.del("/api/clientes/1")).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("erro com detail string vira a mensagem do Error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respostaFake({ detail: "Cliente não encontrado" }, { status: 404 }) as any
    );

    await expect(api.get("/api/clientes/x")).rejects.toThrow("Cliente não encontrado");
  });

  it("detail estruturado do 422 não vira [object Object]", async () => {
    const detail = [{ loc: ["body", "nome"], msg: "Field required" }];
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respostaFake({ detail }, { status: 422 }) as any
    );

    await expect(api.post("/api/clientes", {})).rejects.toThrow(JSON.stringify(detail));
  });

  it("erro sem corpo cai na mensagem genérica com o status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respostaFake(null, { status: 500, jsonThrows: true }) as any
    );

    await expect(api.get("/api/dashboard")).rejects.toThrow("Erro 500");
  });

  it("erro sem detail também usa a mensagem genérica", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      respostaFake({ algo: "outro" }, { status: 503 }) as any
    );

    await expect(api.get("/api/dashboard")).rejects.toThrow("Erro 503");
  });

  it("PATCH usa o verbo certo", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(respostaFake({}) as any);

    await api.patch("/api/negocios/1/etapa", { etapa: "aprovado" });

    expect(fetchMock.mock.calls[0][1]?.method).toBe("PATCH");
  });
});
