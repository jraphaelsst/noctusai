import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConjugeDaCertidaoContainer } from "@/components/ConjugeDaCertidaoContainer";
import type { ConjugeSugerido } from "@/types/partes";

const mutate = vi.fn();
vi.mock("@/hooks/usePartes", () => ({
  useAdicionarConjugeDaCertidao: () => ({ mutate, isPending: false }),
}));

const sugestao: ConjugeSugerido = {
  principal_cliente_id: "cli-1",
  documento_id: "doc-1",
  lado: "comprador",
  nome: "RAFAEL MENEZES DO PRADO",
  nome_anterior: null,
  data_nascimento: "1985-03-10",
  nacionalidade: null,
  profissao: null,
  genero: null,
  naturalidade: null,
  nome_mae: null,
  nome_pai: null,
};

describe("<ConjugeDaCertidaoContainer/>", () => {
  beforeEach(() => mutate.mockReset());

  it("shows the name and birthdate read from the certidão and adds with one click", () => {
    render(<ConjugeDaCertidaoContainer clienteId="cli-1" sugestao={sugestao} />);
    expect(screen.getByTestId("conjuge-da-certidao-texto").textContent).toContain(
      "RAFAEL MENEZES DO PRADO (nasc. 10/03/1985)",
    );
    fireEvent.click(screen.getByTestId("conjuge-da-certidao-adicionar"));
    expect(mutate.mock.calls[0][0]).toEqual({ documento_id: "doc-1", lado: "comprador" });
  });

  it("a refusal is visible; the same-person 409 offers link or create-new", () => {
    mutate.mockImplementationOnce((_body, opts) =>
      opts.onError({
        message: "x",
        body: {
          error: {
            message: "Já existe uma pessoa com este nome e data de nascimento.",
            details: { candidatos: [{ cliente_id: "c-9", nome: "Rafael", data_nascimento: "1985-03-10" }] },
          },
        },
      }),
    );
    render(<ConjugeDaCertidaoContainer clienteId="cli-1" sugestao={sugestao} />);
    fireEvent.click(screen.getByTestId("conjuge-da-certidao-adicionar"));
    expect(screen.getByTestId("conjuge-da-certidao-erro").textContent).toContain("Já existe");
    fireEvent.click(screen.getByTestId("conjuge-da-certidao-vincular-c-9"));
    expect(mutate.mock.calls[1][0]).toMatchObject({ cliente_id: "c-9" });
    fireEvent.click(screen.getByTestId("conjuge-da-certidao-criar-novo"));
    expect(mutate.mock.calls[2][0]).toMatchObject({ criar_novo: true });
  });
});
