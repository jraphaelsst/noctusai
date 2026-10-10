/** GerarHeadlinesDialog — forms get the fixed marca + post_id, then progress, then the result hand-off. */
import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ lote: vi.fn(), me: vi.fn(), viral: vi.fn() }));

vi.mock("@/components/geracao/headlines/FormMePublico", () => ({
  FormMePublico: (p: any) => {
    m.me(p);
    return <button onClick={() => p.onCriado({ id: "l1" })}>criar-me</button>;
  },
}));
vi.mock("@/components/geracao/headlines/FormViral", () => ({
  FormViral: (p: any) => {
    m.viral(p);
    return <span>form-viral</span>;
  },
}));
vi.mock("@/components/geracao/headlines/lote", () => ({
  ProgressoLote: () => <div>progresso</div>,
}));
vi.mock("@/hooks/geracao/useHeadlines", () => ({ useLote: (id: string | null) => m.lote(id) }));

import { GerarHeadlinesDialog } from "./GerarHeadlinesDialog";

let rerender: () => void = () => {};
const montar = (onConcluido = vi.fn()) => {
  const el = <GerarHeadlinesDialog open onClose={vi.fn()} marcaId="m1" postId="p1" onConcluido={onConcluido} />;
  const r = render(el);
  rerender = () => r.rerender(<GerarHeadlinesDialog open onClose={vi.fn()} marcaId="m1" postId="p1" onConcluido={onConcluido} />);
  return onConcluido;
};

beforeEach(() => m.lote.mockReturnValue({ data: undefined, isError: false, refetch: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GerarHeadlinesDialog", () => {
  it("os formulários recebem marca e post fixos (post_id)", () => {
    montar();
    expect(m.me.mock.calls.at(-1)![0]).toMatchObject({ marcaId: "m1", postId: "p1", who: "me" });
    fireEvent.click(screen.getByText("Viral"));
    expect(m.viral.mock.calls.at(-1)![0]).toMatchObject({ marcaId: "m1", postId: "p1" });
  });

  it("depois de criar, mostra o carregamento e depois o progresso real", () => {
    montar();
    fireEvent.click(screen.getByText("criar-me"));
    expect(screen.getByTestId("gerar-headlines-carregando")).toBeInTheDocument();
    m.lote.mockReturnValue({ data: { id: "l1", status: "processando" }, isError: false });
    rerender();
    expect(screen.getByText("progresso")).toBeInTheDocument();
  });

  it("lote concluído oferece 'Ver headlines'", () => {
    const onConcluido = montar();
    fireEvent.click(screen.getByText("criar-me"));
    m.lote.mockReturnValue({ data: { id: "l1", status: "completo" }, isError: false });
    rerender();
    fireEvent.click(screen.getByText("Ver headlines"));
    expect(onConcluido).toHaveBeenCalledWith("l1");
  });

  it("lote com falha não oferece ver, só gerar de novo", () => {
    montar();
    fireEvent.click(screen.getByText("criar-me"));
    m.lote.mockReturnValue({ data: { id: "l1", status: "falha" }, isError: false });
    rerender();
    expect(screen.getByText("A geração falhou.")).toBeInTheDocument();
    expect(screen.queryByText("Ver headlines")).not.toBeInTheDocument();
  });

  it("erro ao acompanhar o lote mostra alerta", () => {
    montar();
    fireEvent.click(screen.getByText("criar-me"));
    m.lote.mockReturnValue({ data: undefined, isError: true, refetch: vi.fn() });
    rerender();
    expect(screen.getByTestId("gerar-headlines-erro")).toBeInTheDocument();
  });
});
