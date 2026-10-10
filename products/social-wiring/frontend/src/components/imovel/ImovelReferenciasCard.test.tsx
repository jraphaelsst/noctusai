/** ImovelReferenciasCard — view, inline edit, client-side Drive URL validation. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";

const { mutateAsync } = vi.hoisted(() => ({ mutateAsync: vi.fn() }));
vi.mock("@/hooks/useImovelManual", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/useImovelManual")>();
  return {
    ...actual,
    useAtualizarReferencias: () => ({ mutateAsync, isPending: false }),
  };
});
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import ImovelReferenciasCard from "./ImovelReferenciasCard";

const DRIVE =
  "https://drive.google.com/drive/folders/1vfD3HHF7jN8EiMwhcHkKYrvuxz5GDlEK";
const refs = {
  processo_atual_numero: "876",
  drive_folder_url: DRIVE,
  drive_folder_id: "1vf",
};

beforeEach(() => mutateAsync.mockReset());
afterEach(cleanup);

describe("ImovelReferenciasCard", () => {
  it("views processo and an external, noopener Drive link", () => {
    const { getByTestId } = render(
      <ImovelReferenciasCard codigo="SW-0001" referencias={refs} />,
    );
    expect(getByTestId("imovel-referencias-processo-valor").textContent).toBe(
      "876",
    );
    const a = getByTestId("imovel-referencias-drive-link") as HTMLAnchorElement;
    expect(a.href).toBe(DRIVE);
    expect(a.target).toBe("_blank");
    expect(a.rel).toContain("noopener");
    expect(a.textContent).toContain("Abrir pasta no Drive");
  });

  it("shows dashes and no link when there are no referências", () => {
    const { queryByTestId, getByTestId } = render(
      <ImovelReferenciasCard
        codigo="ONE1"
        referencias={{
          processo_atual_numero: null,
          drive_folder_url: null,
          drive_folder_id: null,
        }}
      />,
    );
    expect(queryByTestId("imovel-referencias-drive-link")).toBeNull();
    expect(getByTestId("imovel-referencias-processo-valor").textContent).toBe(
      "—",
    );
  });

  it("edits inline and PATCHes only what changed", async () => {
    mutateAsync.mockResolvedValue({});
    const { getByTestId, queryByTestId } = render(
      <ImovelReferenciasCard codigo="SW-0001" referencias={refs} />,
    );
    fireEvent.click(getByTestId("imovel-referencias-editar"));
    fireEvent.change(getByTestId("imovel-referencias-processo"), {
      target: { value: "877" },
    });
    fireEvent.click(getByTestId("imovel-referencias-salvar"));
    await waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith({
        processo_atual_numero: "877",
      }),
    );
    await waitFor(() =>
      expect(queryByTestId("imovel-referencias-salvar")).toBeNull(),
    );
  });

  it("rejects a non-folder Drive URL without calling the API", () => {
    const { getByTestId } = render(
      <ImovelReferenciasCard codigo="SW-0001" referencias={refs} />,
    );
    fireEvent.click(getByTestId("imovel-referencias-editar"));
    fireEvent.change(getByTestId("imovel-referencias-drive"), {
      target: { value: "https://example.com/x" },
    });
    fireEvent.click(getByTestId("imovel-referencias-salvar"));
    expect(getByTestId("imovel-referencias-erro").textContent).toContain(
      "drive.google.com",
    );
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it("surfaces a server error and stays in edit mode", async () => {
    mutateAsync.mockRejectedValueOnce(new Error("drive_url_invalida"));
    const { getByTestId } = render(
      <ImovelReferenciasCard codigo="SW-0001" referencias={refs} />,
    );
    fireEvent.click(getByTestId("imovel-referencias-editar"));
    fireEvent.change(getByTestId("imovel-referencias-processo"), {
      target: { value: "1" },
    });
    fireEvent.click(getByTestId("imovel-referencias-salvar"));
    await waitFor(() =>
      expect(getByTestId("imovel-referencias-erro").textContent).toContain(
        "drive_url_invalida",
      ),
    );
  });
});
