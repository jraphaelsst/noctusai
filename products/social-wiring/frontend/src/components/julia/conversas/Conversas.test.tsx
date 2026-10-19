/** Julia Conversas v2 — tabs/filters, kanban by tag, header actions + confirms, Cliente column, history 403/404. */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const h = vi.hoisted(() => ({ confirm: true }));
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@noctusai/seed/infra", () => ({ api }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@noctusai/lib/components", async (orig) => {
  const real = await orig<Record<string, unknown>>();
  return { ...real, useConfirm: () => async () => h.confirm };
});
vi.mock("@/hooks/useWhatsAppChats", () => ({ useWhatsAppChats: () => ({ dataUpdatedAt: 0 }) }));
vi.mock("@/components/WhatsAppChatWindow", async () => {
  const React = await import("react");
  const ThreadsFeedContext = React.createContext<{ data: { id: string; title: string }[] } | null>(null);
  function WhatsAppChatWindow({ onSelectThread }: { onSelectThread?: (id: string) => void }) {
    const feed = React.useContext(ThreadsFeedContext);
    return <ul>{(feed?.data ?? []).map((t) => <li key={t.id}><button onClick={() => onSelectThread?.(t.id)}>{t.title}</button></li>)}</ul>;
  }
  return { WhatsAppChatWindow, ThreadsFeedContext };
});

import { ConversasPanel } from "./ConversasPanel";
import { ConversaAcoes } from "./ConversaAcoes";
import JuliaHistorico from "@/pages/julia/Historico";
import { montarColunas, patchDoMovimento } from "./kanbanColunas";
import { queryConversas, FILTROS_VAZIOS } from "@/hooks/useJuliaConversas";

const TAG = { id: "t1", nome: "Quente" };
const C1 = { contato_id: "k1", chat_id: "a@c.us", nome: "Ana", etiquetas: [TAG] };
const C2 = { contato_id: "k2", chat_id: "b@c.us", nome: "Beto", etiquetas: [] };

function wrap(ui: React.ReactNode, path = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>);
}
function routes(extra: Record<string, unknown> = {}) {
  api.get.mockImplementation((url: string) => {
    if (url in extra) return extra[url] instanceof Error ? Promise.reject(extra[url]) : Promise.resolve(extra[url]);
    if (url.startsWith("/api/julia/conversas?aba=arquivadas")) return Promise.resolve({ data: [] });
    if (url.startsWith("/api/julia/conversas")) return Promise.resolve({ data: [C1, C2] });
    if (url === "/api/julia/etiquetas") return Promise.resolve({ data: [TAG, { id: "t2", nome: "Frio" }] });
    if (url === "/api/team") return Promise.resolve({ data: [{ id: "u1", nome: "Ana Resp", email: "a@x", role: "", org_role: "", created_at: "" }] });
    if (url.endsWith("/notas")) return Promise.resolve({ data: [{ id: "n1", texto: "ligar amanhã", autor_nome: "Eu", created_at: "2026-10-15T10:00:00Z" }] });
    if (url.startsWith("/api/julia/historico/")) return Promise.resolve({ data: { contato: { id: "k1", nome: "Ana", telefone: "5511" }, interacoes: [{ id: "i1", tipo: "Qualificação", iniciada_em: "2026-10-15T10:00:00Z", canal: "WhatsApp", resumo: "quer apto", intencoes: ["quer visitar"] }], mensagens: [{ id: "m1", direction: "inbound", body: "oi", created_at: "2026-10-15T10:00:00Z" }] } });
    return Promise.resolve({ data: [] });
  });
}
const err = (status: number) => Object.assign(new Error("x"), { status });

beforeEach(() => { vi.clearAllMocks(); h.confirm = true; routes(); api.patch.mockResolvedValue({}); api.post.mockResolvedValue({ data: {} }); localStorage.clear(); });
afterEach(cleanup);

describe("query + column model", () => {
  it("serialises tab and filters", () => {
    const q = queryConversas("minhas", { ...FILTROS_VAZIOS, q: "ana", operacao: "compra", responsaveis: ["sem", "u1"], etiquetas: ["t1"] });
    expect(q).toContain("aba=minhas"); expect(q).toContain("operacao=compra");
    expect(q).toContain("responsavel=sem%2Cu1"); expect(q).toContain("etiqueta=t1");
  });
  it("builds Todas + one column per tag + Arquivadas and maps drops to tag/archive patches", () => {
    const cols = montarColunas({ todas: [C1, C2], arquivadas: [], etiquetas: [TAG], colunas: ["t1"], todasVisivel: true, arquivadasAberta: false });
    expect(cols.map((c) => c.stage.id)).toEqual(["__todas", "t1", "__arquivadas"]);
    expect(cols[1].cards.map((c) => c.conversa.nome)).toEqual(["Ana"]);
    expect(patchDoMovimento(C2, "__todas", "t1")).toEqual({ etiquetas: ["t1"] });
    expect(patchDoMovimento(C1, "t1", "t2")).toEqual({ etiquetas: ["t2"] });
    expect(patchDoMovimento(C1, "__todas", "__arquivadas")).toEqual({ arquivado: true });
  });
});

describe("ConversasPanel", () => {
  it("lists conversations, switches tab and applies a filter from the drawer", async () => {
    wrap(<ConversasPanel connectionId="c1" autoReplyEnabled={false} />);
    expect(await screen.findByText("Ana")).toBeTruthy();
    fireEvent.click(screen.getByTestId("aba-arquivadas"));
    await waitFor(() => expect(api.get.mock.calls.some(([u]) => String(u).includes("aba=arquivadas"))).toBe(true));
    fireEvent.click(screen.getByTestId("filtro-abrir"));
    const dlg = await screen.findByTestId("filtro-drawer");
    fireEvent.click(within(dlg).getByLabelText("Compra"));
    fireEvent.click(within(dlg).getByLabelText("Julia atendendo"));
    fireEvent.click(within(dlg).getByText("Filtrar"));
    await waitFor(() => expect(api.get.mock.calls.some(([u]) => String(u).includes("operacao=compra") && String(u).includes("atendimento=julia"))).toBe(true));
  });

  it("selecting a conversation shows the Cliente column sections", async () => {
    wrap(<ConversasPanel connectionId="c1" autoReplyEnabled={false} />);
    fireEvent.click(await screen.findByText("Ana"));
    const col = await screen.findByTestId("cliente-column");
    for (const t of ["Perfil", "Visitas solicitadas", "Etiquetas", "Notas internas", "Interações"]) expect(within(col).getByLabelText(t)).toBeTruthy();
    expect(await within(col).findByText("ligar amanhã")).toBeTruthy();
    expect(await within(col).findByText("quer visitar")).toBeTruthy();
    fireEvent.click(within(col).getByLabelText("Remover etiqueta Quente"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/contatos/k1", { etiquetas: [] }));
  });

  it("kanban view renders Todas (n), tag column added through the picker, collapsed Arquivadas", async () => {
    wrap(<ConversasPanel connectionId="c1" autoReplyEnabled={false} />, "/?view=kanban");
    await waitFor(() => expect(screen.getByTestId("kanban-todas-olho").closest("div")?.textContent).toContain("Todas (2)"));
    expect(screen.getByTestId("kanban-arquivadas").getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByTestId("kanban-add-coluna"));
    fireEvent.click(within(await screen.findByTestId("etiqueta-picker")).getByText("Quente"));
    expect(await screen.findByText("Quente (1)")).toBeTruthy();
  });
});

describe("ConversaAcoes", () => {
  const contato = { contatoId: "k1", arquivado: false, bloqueado: false, responsavelUserId: null };
  function setup() { return wrap(<ConversaAcoes contato={contato} />); }

  it("archive and block patch only after confirm", async () => {
    setup();
    h.confirm = false;
    fireEvent.click(screen.getByTestId("acao-arquivar"));
    await new Promise((r) => setTimeout(r, 0));
    expect(api.patch).not.toHaveBeenCalled();
    h.confirm = true;
    fireEvent.click(screen.getByTestId("acao-arquivar"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/contatos/k1", { arquivado: true }));
    fireEvent.click(screen.getByTestId("acao-bloquear"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/contatos/k1", { bloqueado: true }));
  });

  it("assigns a responsável, sends like and written feedback", async () => {
    setup();
    fireEvent.click(screen.getByTestId("acao-atribuir"));
    fireEvent.click(await screen.findByText("Ana Resp"));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/api/julia/contatos/k1", { responsavel_user_id: "u1" }));
    fireEvent.click(screen.getByTestId("acao-like"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/contatos/k1/feedback", { nota: "like", comentario: undefined }));
    fireEvent.click(screen.getByTestId("acao-dislike"));
    fireEvent.change(await screen.findByLabelText("Comentário"), { target: { value: "errou o preço" } });
    fireEvent.click(screen.getByTestId("feedback-enviar"));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/julia/contatos/k1/feedback", { nota: "dislike", comentario: "errou o preço" }));
  });

  it("copies the history link", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    setup();
    fireEvent.click(screen.getByTestId("acao-link"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/julia\/conversas\/h\/k1$/)));
  });
});

describe("History page", () => {
  function page() {
    return wrap(<Routes><Route path="/julia/conversas/h/:contatoId" element={<JuliaHistorico />} /></Routes>, "/julia/conversas/h/k1");
  }
  it("renders contact, interactions and messages", async () => {
    page();
    expect(await screen.findByText("Qualificação")).toBeTruthy();
    expect(screen.getByText("oi")).toBeTruthy();
  });
  it("403 → no access", async () => {
    routes({ "/api/julia/historico/k1": err(403) });
    page();
    expect(await screen.findByText("Você não tem acesso a esta conversa")).toBeTruthy();
  });
  it("404 → not found", async () => {
    routes({ "/api/julia/historico/k1": err(404) });
    page();
    expect(await screen.findByText("Conversa não encontrada")).toBeTruthy();
  });
});
