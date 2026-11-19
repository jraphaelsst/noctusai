/** CriacaoStatusLine: live sentence + bar from the stream; sub-state fallback; indeterminate when unmeasured. */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ progresso: vi.fn() }));
vi.mock("@/hooks/geracao/useCriacao", async () => {
  const real = await vi.importActual<typeof import("@/hooks/geracao/useCriacao")>("@/hooks/geracao/useCriacao");
  return { ...real, useCriacaoProgresso: (...a: unknown[]) => m.progresso(...a) };
});

import { CriacaoStatusLine } from "./CriacaoStatusLine";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CriacaoStatusLine", () => {
  it("mostra a frase ao vivo e a barra com o percentual do stream", () => {
    m.progresso.mockReturnValue({ progresso: { passo: "tts", mensagem: "Sintetizando voz (2/3)", progresso: 0.4, terminal: false } });
    render(<CriacaoStatusLine postId="p1" estado="gerando" />);
    expect(screen.getByRole("status")).toHaveTextContent("Sintetizando voz (2/3)");
    expect(screen.getByRole("progressbar", { name: "Progresso da criação" })).toHaveAttribute("aria-valuetext", "40%");
  });

  it("sem frame ao vivo cai na frase do sub-estado e a barra fica indeterminada (nunca inventa %)", () => {
    m.progresso.mockReturnValue({ progresso: null });
    render(<CriacaoStatusLine postId="p1" estado="na_fila" />);
    expect(screen.getByRole("status")).toHaveTextContent("Na fila de criação");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "Em andamento");
  });

  it("falha mostra o código e não tem barra", () => {
    m.progresso.mockReturnValue({ progresso: null });
    render(<CriacaoStatusLine postId="p1" estado="falhou" falhaCodigo="cota" />);
    expect(screen.getByRole("status")).toHaveTextContent("A criação falhou (cota)");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("estado sem linha (aguardando aprovação) não renderiza nada", () => {
    m.progresso.mockReturnValue({ progresso: null });
    const { container } = render(<CriacaoStatusLine postId="p1" estado="aguardando_aprovacao" />);
    expect(container).toBeEmptyDOMElement();
  });
});
