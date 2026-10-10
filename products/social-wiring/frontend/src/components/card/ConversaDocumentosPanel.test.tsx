/**
 * ConversaDocumentosPanel — "Pedir documentos" + the a_classificar triage list
 * (CONTRACT §2.2/§2.3), hooks mocked at the boundary.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
  conversa: vi.fn(),
  aClassificar: vi.fn(),
  pedir: vi.fn(),
  classificar: vi.fn(),
}));
vi.mock("@/hooks/useConversaDocumentos", () => ({
  useConversa: m.conversa,
  useDocumentosAClassificar: m.aClassificar,
  usePedirDocumentos: () => ({ mutate: m.pedir, isPending: false }),
  useClassificarDocumento: () => ({ mutate: m.classificar, isPending: false }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { ConversaDocumentosPanel } from "./ConversaDocumentosPanel";

const q = (data: unknown, over: Record<string, unknown> = {}) => ({
  data,
  isPending: data === undefined,
  isFetching: false,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  m.conversa.mockReturnValue(q({ chat_id: null, connection_id: null, mensagens: [] }));
  m.aClassificar.mockReturnValue(q({ items: [], total: 0 }));
});

describe("ConversaDocumentosPanel", () => {
  it("a failed first load renders an error with retry, not 'Nenhuma conversa'", () => {
    const refetch = vi.fn();
    m.conversa.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true, refetch });
    render(<ConversaDocumentosPanel clienteId="c1" />);
    expect(screen.getByTestId("conversa-error")).toBeTruthy();
    expect(screen.queryByTestId("conversa-skeleton")).toBeNull();
    expect(screen.queryByText("Nenhuma conversa ainda.")).toBeNull();
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalled();
  });

  it("skeletons only while there is no data", () => {
    m.conversa.mockReturnValue(q(undefined));
    render(<ConversaDocumentosPanel clienteId="c1" />);
    expect(screen.getByTestId("conversa-skeleton")).toBeTruthy();
  });

  it("keeps the messages mounted during a background refetch", () => {
    m.conversa.mockReturnValue(
      q(
        {
          chat_id: "x@c.us",
          connection_id: "k",
          mensagens: [
            { id: "1", direcao: "in", texto: "oi", enviada_em: null, anexo: null },
          ],
        },
        { isFetching: true },
      ),
    );
    render(<ConversaDocumentosPanel clienteId="c1" />);
    expect(screen.getByText("oi")).toBeTruthy();
    expect(screen.queryByTestId("conversa-skeleton")).toBeNull();
    expect(screen.getByTestId("conversa-refreshing")).toBeTruthy();
  });

  it("asks for the documents", () => {
    render(<ConversaDocumentosPanel clienteId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Pedir documentos" }));
    expect(m.pedir).toHaveBeenCalledTimes(1);
  });

  it("lists a_classificar documents and classifies one", () => {
    m.aClassificar.mockReturnValue(
      q({
        total: 1,
        items: [
          {
            id: "d1",
            nome_original: "foto.jpg",
            mime_type: "image/jpeg",
            tamanho_bytes: 10,
            created_at: "2026-10-09T10:00:00Z",
            origem_entrada: "whatsapp",
            classificacao_tipo_provavel: null,
            classificacao_confianca: "nenhuma",
          },
        ],
      }),
    );
    render(<ConversaDocumentosPanel clienteId="c1" />);
    const botao = screen.getByRole("button", { name: "Classificar" }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Tipo de foto.jpg"), { target: { value: "cnh" } });
    fireEvent.click(botao);
    expect(m.classificar.mock.calls[0][0]).toEqual({ documentoId: "d1", tipo: "cnh" });
  });
});
