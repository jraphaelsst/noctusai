/**
 * CerebroPerguntas.test.tsx — FE-B: questionnaire (reveal in groups, autosave
 * debounce/blur, chips, accept/dismiss, Finalizar not gated by review,
 * replace/append modal, synthesis navigation, voice flag OFF). Hooks mocked.
 */
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const m = {
  brain: vi.fn(),
  salvar: vi.fn(),
  zerar: vi.fn(),
  revisar: vi.fn(),
  decidir: vi.fn(),
  finalizar: vi.fn(),
};
vi.mock("@/hooks/useCerebroPerguntas", () => ({
  useCerebroPerguntas: (id: any) => m.brain(id),
  useSalvarResposta: () => ({ mutateAsync: m.salvar, isPending: false }),
  useZerarRespostas: () => ({ mutateAsync: m.zerar, isPending: false }),
  useRevisarRespostas: () => ({ mutateAsync: m.revisar, isPending: false }),
  useDecidirSugestao: () => ({ mutateAsync: m.decidir, isPending: false }),
  useFinalizarRespostas: () => ({ mutateAsync: m.finalizar, isPending: false }),
}));

import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import CerebroPerguntas from "./CerebroPerguntas";

const quest = (n: number, group: number) => ({
  id: `q${n}`, position: n, group, text: `Pergunta ${n}`, hint: n === 1 ? "Dica 1" : null, optional: false,
});
const NOVE = [1, 2, 3, 4, 5, 6].map((n) => quest(n, n <= 3 ? 1 : 2));
const ans = (qid: string, text: string, review: Partial<any> = {}, transcricao: any = null) => ({
  question_id: qid, text, updated_at: null, transcricao,
  review: { status: "none", verdict: null, reason: null, improved: null, decision: null, error: null, ...review },
});
function detail(over: Partial<any> = {}) {
  return {
    id: "b1", marca_id: "m1", kind: "sistema", template_slug: "x", name: "Núcleo", status: "vazio",
    content_chars: 0, answered: 0, total_questions: 6, synthesis_status: "idle", updated_at: "",
    content: "", content_version: 4, synthesis_error: null, synthesized_at: null,
    template: { slug: "x", name: "Núcleo", description: "", sort_order: 1, questions: NOVE },
    answers: [], imports: [], ...over,
  };
}
const q = (data: any, over: Partial<any> = {}) => ({
  data, showSkeleton: false, isRefreshing: false, refetch: vi.fn(), ...over,
});

function mount(props: any = {}) {
  return render(
    <MemoryRouter initialEntries={["/media-creation/cerebro/b1/perguntas"]}>
      <Routes>
        <Route path="/media-creation/cerebro/:brainId/perguntas" element={<CerebroPerguntas {...props} />} />
        <Route path="/media-creation/cerebro/:brainId" element={<div>EDITOR-ROTA</div>} />
      </Routes>
    </MemoryRouter>,
  );
}
const area = (n: number) => screen.getByLabelText(`Resposta da pergunta ${n}`) as HTMLTextAreaElement;
async function tick(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  m.brain.mockReturnValue(q(detail()));
  m.salvar.mockResolvedValue({});
  m.zerar.mockResolvedValue({ deleted: 1 });
  m.revisar.mockResolvedValue({ queued: 1 });
  m.finalizar.mockResolvedValue({});
  m.decidir.mockResolvedValue(ans("q1", "melhorada"));
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("CerebroPerguntas", () => {
  it("shows skeleton and error states", () => {
    m.brain.mockReturnValue(q(undefined, { showSkeleton: true }));
    mount();
    expect(screen.getByTestId("perguntas-skeleton")).toBeTruthy();
    cleanup();
    m.brain.mockReturnValue(q(undefined));
    mount();
    expect(screen.getByText("Tentar novamente")).toBeTruthy();
  });

  it("renders header, progress, numbered card with hint and only the first group", () => {
    m.brain.mockReturnValue(q(detail({ answers: [ans("q1", "oi")] })));
    mount();
    expect(screen.getByText("Personalize seu cérebro")).toBeTruthy();
    expect(screen.getByText("Núcleo - Sistema")).toBeTruthy();
    expect(screen.getByText("Progresso das respostas 1 de 6")).toBeTruthy();
    expect(screen.getByText("Dica 1")).toBeTruthy();
    expect(screen.getAllByTestId("pergunta-card")).toHaveLength(3);
    expect(screen.getByTestId("grupo-aviso").textContent).toContain("Grupo 1 de 2");
    expect(screen.getByText("Respondida")).toBeTruthy();
    expect(screen.getAllByText("Aguardando resposta")).toHaveLength(2);
  });

  it("reveals every group when more than 3 are answered on load", () => {
    m.brain.mockReturnValue(q(detail({ answers: ["q1", "q2", "q3", "q4"].map((i) => ans(i, "x")) })));
    mount();
    expect(screen.getAllByTestId("pergunta-card")).toHaveLength(6);
  });

  it("reveals the next group once the current one is complete", () => {
    mount();
    for (const n of [1, 2, 3]) fireEvent.change(area(n), { target: { value: "r" } });
    expect(screen.getAllByTestId("pergunta-card")).toHaveLength(6);
  });

  it("autosaves 1.5 s after typing (debounced) and on blur", async () => {
    mount();
    fireEvent.change(area(1), { target: { value: "a" } });
    fireEvent.change(area(1), { target: { value: "ab" } });
    await tick(1400);
    expect(m.salvar).not.toHaveBeenCalled();
    await tick(200);
    expect(m.salvar).toHaveBeenCalledTimes(1);
    expect(m.salvar).toHaveBeenCalledWith({ questionId: "q1", text: "ab" });
    fireEvent.change(area(2), { target: { value: "z" } });
    fireEvent.blur(area(2));
    await tick(0);
    expect(m.salvar).toHaveBeenCalledWith({ questionId: "q2", text: "z" });
  });

  it("shows chips for transcription and review states", () => {
    m.brain.mockReturnValue(
      q(detail({
        answers: [
          ans("q1", "", {}, { id: "t", status: "na_fila", posicao: 2, duracao_s: null, texto: null, erro: null }),
          ans("q2", "", {}, { id: "t2", status: "falhou", posicao: null, duracao_s: null, texto: null, erro: { codigo: "x", mensagem: "Áudio ruim" } }),
          ans("q3", "texto", { status: "pending" }),
        ],
      })),
    );
    mount();
    expect(screen.getByText("Na fila (posição 2)")).toBeTruthy();
    expect(screen.getByText("Falha na transcrição")).toBeTruthy();
    expect(screen.getByText("Áudio ruim")).toBeTruthy();
    expect(screen.getByText("Revisando…")).toBeTruthy();
  });

  it("accepts a suggestion and puts the improved text in the field", async () => {
    m.brain.mockReturnValue(
      q(detail({ answers: [ans("q1", "curta", { status: "done", verdict: "rejected", reason: "Vaga", improved: "melhorada" })] })),
    );
    mount();
    expect(screen.getByText("Rejeitada")).toBeTruthy();
    expect(screen.getByText("Motivo: Vaga")).toBeTruthy();
    fireEvent.click(screen.getByText("Usar sugestão"));
    await tick(0);
    expect(m.decidir).toHaveBeenCalledWith({ questionId: "q1", action: "accept" });
    expect(area(1).value).toBe("melhorada");
  });

  it("dismisses an approved suggestion without improvement via OK", async () => {
    m.brain.mockReturnValue(q(detail({ answers: [ans("q1", "ok", { status: "done", verdict: "approved" })] })));
    mount();
    expect(screen.getByText("Aprovada")).toBeTruthy();
    fireEvent.click(screen.getByText("OK"));
    await tick(0);
    expect(m.decidir).toHaveBeenCalledWith({ questionId: "q1", action: "dismiss" });
  });

  it("Finalizar is enabled despite a rejected review and synthesises directly when content is empty", async () => {
    m.brain.mockReturnValue(
      q(detail({ answers: [ans("q1", "x", { status: "done", verdict: "rejected", decision: "dismissed" })] })),
    );
    mount();
    const btn = screen.getByText("Finalizar Respostas") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await tick(0);
    expect(m.finalizar).toHaveBeenCalledWith({ mode: "replace", expected_version: 4 });
    expect(screen.getByText("Gerando cérebro...")).toBeTruthy();
  });

  it("asks replace/append when the brain already has content", async () => {
    m.brain.mockReturnValue(q(detail({ content: "algo", answers: [ans("q1", "x")] })));
    mount();
    fireEvent.click(screen.getByText("Finalizar Respostas"));
    await tick(0);
    expect(m.finalizar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Anexar abaixo"));
    await tick(0);
    expect(m.finalizar).toHaveBeenCalledWith({ mode: "append", expected_version: 4 });
  });

  it("navigates to the editor when the polled synthesis finishes", async () => {
    m.brain.mockReturnValue(q(detail({ answers: [ans("q1", "x")] })));
    const view = mount();
    fireEvent.click(screen.getByText("Finalizar Respostas"));
    await tick(0);
    m.brain.mockReturnValue(q(detail({ synthesis_status: "processing", answers: [ans("q1", "x")] })));
    view.rerender(
      <MemoryRouter initialEntries={["/media-creation/cerebro/b1/perguntas"]}>
        <Routes>
          <Route path="/media-creation/cerebro/:brainId/perguntas" element={<CerebroPerguntas />} />
          <Route path="/media-creation/cerebro/:brainId" element={<div>EDITOR-ROTA</div>} />
        </Routes>
      </MemoryRouter>,
    );
    m.brain.mockReturnValue(q(detail({ synthesis_status: "idle", synthesized_at: "2026-10-09T10:00:00Z", content: "novo", answers: [ans("q1", "x")] })));
    view.rerender(
      <MemoryRouter initialEntries={["/media-creation/cerebro/b1/perguntas"]}>
        <Routes>
          <Route path="/media-creation/cerebro/:brainId/perguntas" element={<CerebroPerguntas />} />
          <Route path="/media-creation/cerebro/:brainId" element={<div>EDITOR-ROTA</div>} />
        </Routes>
      </MemoryRouter>,
    );
    await tick(0);
    expect(toast.success).toHaveBeenCalledWith("Cérebro gerado!");
    expect(screen.getByText("EDITOR-ROTA")).toBeTruthy();
  });

  it("Revisar com IA saves drafts then queues the review", async () => {
    m.brain.mockReturnValue(q(detail({ answers: [ans("q1", "x")] })));
    mount();
    fireEvent.change(area(1), { target: { value: "xy" } });
    fireEvent.click(screen.getByText("Revisar com IA"));
    await tick(0);
    expect(m.salvar).toHaveBeenCalledWith({ questionId: "q1", text: "xy" });
    expect(m.revisar).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Respostas enviadas para revisão. Aguarde...");
  });

  it("Salvar Rascunho flushes and toasts; Zerar Tudo confirms then resets", async () => {
    m.brain.mockReturnValue(q(detail({ answers: [ans("q1", "x")] })));
    mount();
    fireEvent.click(screen.getByText("Salvar Rascunho"));
    await tick(0);
    expect(toast.success).toHaveBeenCalledWith("Rascunho salvo com sucesso!");
    fireEvent.click(screen.getByText("Zerar Tudo"));
    expect(screen.getByText("Confirmar Exclusão")).toBeTruthy();
    fireEvent.click(screen.getByText("Sim, Zerar Tudo"));
    await tick(0);
    expect(m.zerar).toHaveBeenCalled();
    expect(area(1).value).toBe("");
  });

  it("keeps the voice toggle hidden by default and shows it behind the flag", () => {
    mount();
    expect(screen.queryByText("Prefiro falar")).toBeNull();
    cleanup();
    mount({ vozHabilitada: true });
    expect(screen.getByText("Prefiro falar")).toBeTruthy();
  });

  it("redirects custom brains to the editor", async () => {
    m.brain.mockReturnValue(q(detail({ kind: "custom", template: null })));
    mount();
    await tick(0);
    expect(screen.getByText("EDITOR-ROTA")).toBeTruthy();
  });
});
