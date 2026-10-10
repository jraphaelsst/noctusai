/** Container wiring: confirming a certidão uses the DOCUMENT's own código. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";

const m = vi.hoisted(() => ({ confirmar: vi.fn() }));
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
}));
vi.mock("@/hooks/useImovelDados", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useImovelDados")>()),
  useImovelDados: () => q({ vinculo_legal: null }),
  useImovelDocumentos: () =>
    q([{ id: "doc-m", codigo: "SW-0001", fonte_codigo: "SW-0001" }, { id: "doc-v", codigo: "ONE1234" }]),
  useImovelDocumentoMutations: () => ({ upload: { isPending: false } }),
}));
vi.mock("@/components/imovel/ImovelContratoCard", () => ({ default: () => null }));
vi.mock("@/components/imovel/ImovelCertidoesCard", () => ({
  default: (p: { onConfirmar: (id: string, t: string, patch: object) => void }) => (
    <>
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
