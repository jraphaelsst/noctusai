/** Allowlist card: states (skeleton/error/empty/on/off), add (validation, 422/409), remove, switch, all as cache writes. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { PermitidosCard } from "./PermitidosCard";
import { PERMITIDOS_KEY, PROTECAO_KEY, type PermitidosLista } from "@/hooks/useJuliaProtecao";

const P = (id: string, numero = "5511999990001", rotulo: string | null = null) => ({ id, numero, rotulo, criado_em: "2026-11-05T10:00:00Z" });

/** A tiny stateful server: the background settle refetch must agree with the write, as the real one does. */
function setup(data: PermitidosLista | Error) {
  const server = data instanceof Error ? data : { ...data, items: [...data.items] };
  api.get.mockImplementation(() => (server instanceof Error ? Promise.reject(server) : Promise.resolve({ data: { ...server } })));
  if (!(server instanceof Error)) {
    api.put.mockImplementation(async (_u: string, b: { permitidos_ativo: boolean }) => { server.ativo = b.permitidos_ativo; return { data: {} }; });
    api.post.mockImplementation(async (_u: string, b: { numero: string; rotulo?: string }) => {
      const row = P("new", b.numero.replace(/\D/g, ""), b.rotulo ?? null);
      server.items.push(row);
      return { data: row };
    });
    api.delete.mockImplementation(async (u: string) => { server.items = server.items.filter((i) => !u.endsWith(`/${i.id}`)); return { data: { ok: true } }; });
  }
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData([...PROTECAO_KEY, "config"], { permitidos_ativo: data instanceof Error ? false : data.ativo });
  return { qc, ...render(<QueryClientProvider client={qc}><PermitidosCard /></QueryClientProvider>) };
}
const err = (status: number, code: string) => Object.assign(new Error("x"), { status, body: { error: { code, message: "srv" } } });
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("PermitidosCard", () => {
  it("skeleton, then the empty state with the 'responde a todos' status", async () => {
    setup({ ativo: false, items: [] });
    expect(screen.getByTestId("permitidos-skeleton")).toBeTruthy();
    expect(await screen.findByTestId("permitidos-vazio")).toBeTruthy();
    expect(screen.getByTestId("permitidos-status").textContent).toBe("Desligada: a Julia responde a todos");
  });

  it("switch on + empty list says the list is empty (she answers everyone)", async () => {
    setup({ ativo: true, items: [] });
    expect((await screen.findByTestId("permitidos-status")).textContent).toBe("Lista vazia: a Julia responde a todos");
  });

  it("switch on + list: counts the numbers (singular/plural) and formats them", async () => {
    setup({ ativo: true, items: [P("a", "5511999990001", "Maria"), P("b", "5511999990002")] });
    expect((await screen.findByTestId("permitidos-status")).textContent).toBe("Ligada: a Julia responde só a 2 números");
    expect(screen.getAllByTestId("permitido-item")).toHaveLength(2);
    expect(screen.getByText("+55 11 99999-0001")).toBeTruthy();
    expect(screen.getByText("Maria")).toBeTruthy();
  });

  it("error state with retry (never a silent empty)", async () => {
    setup(err(500, "boom"));
    expect((await screen.findByTestId("permitidos-erro")).textContent).toContain("srv");
    expect(screen.queryByTestId("permitidos-vazio")).toBeNull();
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeTruthy();
  });

  it("switch writes permitidos_ativo into the list and the config caches", async () => {
    const { qc } = setup({ ativo: false, items: [P("a")] });
    fireEvent.click(await screen.findByRole("switch"));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith("/api/julia/protecao/config", { permitidos_ativo: true }));
    await waitFor(() => expect((qc.getQueryData(PERMITIDOS_KEY) as PermitidosLista).ativo).toBe(true));
    expect((qc.getQueryData([...PROTECAO_KEY, "config"]) as { permitidos_ativo: boolean }).permitidos_ativo).toBe(true);
  });

  it("switch failure rolls back and says why", async () => {
    const { qc } = setup({ ativo: false, items: [] });
    api.put.mockRejectedValue(err(403, "x"));
    fireEvent.click(await screen.findByRole("switch"));
    expect((await screen.findByTestId("permitidos-erro-acao")).textContent).toBe("srv");
    expect((qc.getQueryData(PERMITIDOS_KEY) as PermitidosLista).ativo).toBe(false);
  });

  it("add: rejects a short number inline, then commits the server row into the cache and clears the form", async () => {
    const { qc } = setup({ ativo: true, items: [] });
    const num = await screen.findByLabelText("WhatsApp (com DDI e DDD)");
    fireEvent.change(num, { target: { value: "123" } });
    fireEvent.click(screen.getByTestId("permitido-adicionar"));
    expect(screen.getByTestId("permitido-numero-erro")).toBeTruthy();
    expect(num.getAttribute("aria-invalid")).toBe("true");
    expect(api.post).not.toHaveBeenCalled();

    fireEvent.change(num, { target: { value: "+55 11 98888-7777" } });
    fireEvent.change(screen.getByLabelText("Rótulo (opcional)"), { target: { value: "João" } });
    fireEvent.click(screen.getByTestId("permitido-adicionar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/protecao/permitidos", { numero: "+55 11 98888-7777", rotulo: "João" }));
    await waitFor(() => expect((qc.getQueryData(PERMITIDOS_KEY) as PermitidosLista).items.map((i) => i.id)).toEqual(["new"]));
    expect((num as HTMLInputElement).value).toBe("");
    expect(toast.success).toHaveBeenCalled();
  });

  it.each([
    [422, "numero_invalido", "Número inválido. Use o formato com DDI e DDD, por exemplo +55 11 99999-9999."],
    [409, "numero_ja_permitido", "Este número já está na lista."],
  ])("add refusal %s %s is shown inline", async (status, code, texto) => {
    setup({ ativo: true, items: [] });
    api.post.mockRejectedValue(err(status, code));
    fireEvent.change(await screen.findByLabelText("WhatsApp (com DDI e DDD)"), { target: { value: "+55 11 98888-7777" } });
    fireEvent.click(screen.getByTestId("permitido-adicionar"));
    expect((await screen.findByTestId("permitido-erro")).textContent).toBe(texto);
  });

  it("remove drops the row from the cache at once", async () => {
    const { qc } = setup({ ativo: true, items: [P("a", "5511999990001", "Maria"), P("b", "5511999990002")] });
    fireEvent.click(await screen.findByRole("button", { name: "Remover Maria da lista" }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/api/julia/protecao/permitidos/a"));
    await waitFor(() => expect((qc.getQueryData(PERMITIDOS_KEY) as PermitidosLista).items.map((i) => i.id)).toEqual(["b"]));
  });

  it("remove 404 shows the message", async () => {
    setup({ ativo: true, items: [P("a")] });
    api.delete.mockRejectedValue(err(404, "permitido_nao_encontrado"));
    fireEvent.click(await screen.findByTestId("permitido-remover"));
    expect((await screen.findByTestId("permitidos-erro-acao")).textContent).toBe("Este número já não está na lista.");
  });
});
