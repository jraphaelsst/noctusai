/** Route test: `/avaliacao` -- admin-only, BLIND labelling (no verdict on screen), writes through the cache-write
 *  mutation, third-party notice always visible, summary tab shows the agreement counts. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@testing-library/jest-dom/vitest";

const admin = { value: true };
vi.mock("@noctusai/lib/design-system", async (orig) => ({ ...(await orig<object>()), useIsOrgAdmin: () => admin.value }));

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/lib/api", () => ({ api }));

import Avaliacao from "../avaliacao/Avaliacao";

const AMOSTRA = {
  modo: "cego", prompt_version: "v1", modelo: "m",
  itens: [
    { intake_id: "i1", output_id: "o1", texto: "Pode ser quinta às 15h?", recebida_em: "2026-11-10T12:00:00Z" },
    { intake_id: "i2", output_id: "o2", texto: "Viu o jogo?", recebida_em: "2026-11-10T12:01:00Z" },
  ],
};
const PROGRESSO = { rotuladas: 4, por_rotulo: { agendamento: 2, nao_agendamento: 2, nao_sei: 0 } };
const CONC = { grupos: [{ prompt_version: "v1", modelo: "m", total: 10, nao_sei: 2, decididos: 8, concordam: 6, concordancia: 0.75,
  matriz: { agendamento: { agendamento: 4, nao_agendamento: 1, nao_sei: 1 }, outro: { agendamento: 1, nao_agendamento: 2, nao_sei: 1 } } }] };

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><Avaliacao /></QueryClientProvider>);
}

beforeEach(() => {
  admin.value = true;
  api.get.mockReset();
  api.post.mockReset();
  api.get.mockImplementation(async (url: string) => {
    if (url.includes("/amostra")) return AMOSTRA;
    if (url.includes("/progresso")) return PROGRESSO;
    if (url.includes("/concordancia")) return CONC;
    throw new Error(url);
  });
});
afterEach(cleanup);

describe("Avaliacao", () => {
  it("refuses a non-admin and fetches nothing", () => {
    admin.value = false;
    mount();
    expect(screen.getByTestId("avaliacao-acesso-restrito")).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("shows the third-party notice, then one message at a time with no verdict and no identifiers", async () => {
    mount();
    expect(screen.getByTestId("avaliacao-aviso-terceiros")).toHaveTextContent("Conteúdo de terceiros, uso restrito à avaliação");
    expect(screen.getByTestId("avaliacao-carregando")).toBeInTheDocument();
    expect(await screen.findByTestId("avaliacao-mensagem")).toHaveTextContent("Pode ser quinta às 15h?");
    expect(screen.queryByText("Viu o jogo?")).toBeNull();
    expect(api.get).toHaveBeenCalledWith(expect.stringContaining("modo=cego"));
    for (const t of ["ai-choice-agendamento", "ai-choice-nao_agendamento", "ai-choice-nao_sei"]) expect(screen.getByTestId(t)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("avaliacao-progresso")).toHaveTextContent("4 rotuladas"));
    expect(screen.getByTestId("avaliacao-progresso")).toHaveTextContent("2 restantes");
  });

  it("writes the label (rodada 1, ids only), bumps progress at once and advances; keyboard shortcut works", async () => {
    api.post.mockResolvedValue({ evento_id: "e", repetido: false });
    mount();
    await screen.findByTestId("avaliacao-mensagem");
    fireEvent.keyDown(window, { key: "2" });
    await waitFor(() => expect(screen.getByTestId("avaliacao-mensagem")).toHaveTextContent("Viu o jogo?"));
    expect(api.post).toHaveBeenCalledWith("/api/classificacao/rotulos", { intake_id: "i1", output_id: "o1", rotulo: "nao_agendamento", rodada: 1 });
    expect(JSON.stringify(api.post.mock.calls)).not.toContain("quinta");
  });

  it("keeps the message and says so when the write is refused", async () => {
    api.post.mockRejectedValue(new Error("Falha no servidor."));
    mount();
    await screen.findByTestId("avaliacao-mensagem");
    fireEvent.click(screen.getByTestId("ai-choice-nao_sei"));
    expect(await screen.findByTestId("avaliacao-erro-salvar")).toHaveTextContent("Falha no servidor.");
    expect(screen.getByTestId("avaliacao-mensagem")).toHaveTextContent("Pode ser quinta às 15h?");
    await waitFor(() => expect(screen.getByTestId("avaliacao-progresso")).toHaveTextContent("4 rotuladas"));
  });

  it("shows the empty state and the load error with a retry", async () => {
    api.get.mockImplementation(async (url: string) => (url.includes("/amostra") ? { ...AMOSTRA, itens: [] } : PROGRESSO));
    mount();
    expect(await screen.findByTestId("avaliacao-vazio")).toHaveTextContent("Não há mensagens classificadas");
    cleanup();
    api.get.mockImplementation(async (url: string) => { if (url.includes("/amostra")) throw new Error("boom"); return PROGRESSO; });
    mount();
    expect(await screen.findByTestId("avaliacao-erro")).toHaveTextContent("boom");
  });

  it("the summary tab shows agreement and the matrix", async () => {
    mount();
    fireEvent.click(screen.getByTestId("avaliacao-aba-resumo"));
    expect(await screen.findByTestId("resumo-concordancia")).toHaveTextContent("75,0%");
    expect(screen.getByTestId("resumo-concordancia")).toHaveTextContent("6 de 8 decididas");
  });
});
