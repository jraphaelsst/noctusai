/** Container wiring: confirming a certidão uses the DOCUMENT's own código;
 *  the migration-306 manual entries reach their own mutations. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

const m = vi.hoisted(() => ({
  confirmar: vi.fn(),
  salvarManual: vi.fn(),
  removerManual: vi.fn(),
  confirmarDescricao: vi.fn(),
}));
const q = (data: unknown) => ({ data, isPending: false, isFetching: false, isError: false });
vi.mock("@/hooks/useImovelContrato", () => ({
  useTituloAquisitivo: () => q(undefined),
  useEnderecoRegistro: () => q(undefined),
  useOnusCredor: () => q(undefined),
  useAntigosProprietarios: () => q(undefined),
  useImovelCertidoes: () => q({ certidoes: [] }),
  useConfirmarTitulo: () => ({ mutate: vi.fn(), isPending: false }),
  useConfirmarEnderecoRegistro: () => ({ mutate: vi.fn(), isPending: false }),
  useConfirmarOnusCredor: () => ({ mutate: vi.fn(), isPending: false }),
  useConfirmarUltimaTransferenciaManual: () => ({ mutate: vi.fn(), isPending: false }),
  useConfirmarDocumentoExtracao: () => ({ mutate: m.confirmar, isPending: false }),
  useDescricaoImovel: () => q(undefined),
  useConfirmarDescricaoImovel: () => ({ mutate: m.confirmarDescricao, isPending: false }),
  useSalvarCertidaoManual: () => ({ mutate: m.salvarManual, isPending: false }),
  useRemoverCertidaoManual: () => ({ mutate: m.removerManual, isPending: false }),
}));
vi.mock("@/hooks/useImovelDados", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useImovelDados")>()),
  useImovelDados: () => q({ vinculo_legal: null }),
  useImovelDocumentos: () =>
    q([{ id: "doc-m", codigo: "SW-0001", fonte_codigo: "SW-0001" }, { id: "doc-v", codigo: "ONE1234" }]),
  useImovelDocumentoMutations: () => ({ upload: { isPending: false } }),
}));
vi.mock("@/components/imovel/ImovelContratoCard", () => ({
  default: (p: { onConfirmarDescricao: (t: string | null) => void }) => (
    <button data-testid="d" onClick={() => p.onConfirmarDescricao("Casa ficticia")} />
  ),
}));
vi.mock("@/components/imovel/ImovelCertidoesCard", () => ({
  default: (p: {
    onConfirmar: (id: string, t: string, patch: object) => void;
    onSalvarManual: (t: string, v: object) => void;
    onRemoverManual: (t: string) => void;
  }) => (
    <>
      <button data-testid="s" onClick={() => p.onSalvarManual("cnd_iptu", { resultado: "negativa" })} />
      <button data-testid="r" onClick={() => p.onRemoverManual("cnd_iptu")} />
      <button data-testid="c-m" onClick={() => p.onConfirmar("doc-m", "cnd", {})} />
      <button data-testid="c-v" onClick={() => p.onConfirmar("doc-v", "cnd", {})} />
      <button data-testid="c-x" onClick={() => p.onConfirmar("doc-x", "cnd", {})} />
    </>
  ),
}));

import { ImovelContratoContainer } from "./ImovelContratoContainer";

afterEach(() => {
  cleanup();
  m.confirmar.mockReset();
  m.salvarManual.mockReset();
  m.removerManual.mockReset();
  m.confirmarDescricao.mockReset();
});

describe("ImovelContratoContainer — confirmar certidão", () => {
  it("PATCH carries the document's own código (manual record's doc), else the page's", () => {
    const { getByTestId } = render(<ImovelContratoContainer codigo="ONE1234" />);
    fireEvent.click(getByTestId("c-m"));
    expect(m.confirmar).toHaveBeenLastCalledWith({ documentoId: "doc-m", patch: {}, codigo: "SW-0001" });
    fireEvent.click(getByTestId("c-v"));
    expect(m.confirmar).toHaveBeenLastCalledWith({ documentoId: "doc-v", patch: {}, codigo: "ONE1234" });
    fireEvent.click(getByTestId("c-x"));
    expect(m.confirmar).toHaveBeenLastCalledWith({ documentoId: "doc-x", patch: {}, codigo: "ONE1234" });
  });
});

describe("ImovelContratoContainer — typed entries (migration 306)", () => {
  it("routes the typed certidão and the typed description to their own mutations", () => {
    const { getByTestId } = render(<ImovelContratoContainer codigo="ONE1234" />);
    fireEvent.click(getByTestId("s"));
    expect(m.salvarManual).toHaveBeenLastCalledWith({
      tipo: "cnd_iptu",
      valores: { resultado: "negativa" },
    });
    fireEvent.click(getByTestId("r"));
    expect(m.removerManual).toHaveBeenLastCalledWith({ tipo: "cnd_iptu" });
    fireEvent.click(getByTestId("d"));
    expect(m.confirmarDescricao).toHaveBeenLastCalledWith("Casa ficticia");
    expect(m.confirmar).not.toHaveBeenCalled();
  });
});
