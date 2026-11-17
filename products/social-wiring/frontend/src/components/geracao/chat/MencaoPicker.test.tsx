/** MencaoPicker: opens on the Estruturas tab (the one tab populated for every brand) and switches the query per tab. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => rtl.cleanup());

const men = vi.hoisted(() => ({ q: vi.fn() }));
vi.mock("@/hooks/geracao/useChat", () => ({
  useMencoes: (marcaId: string | null, tipo: string, busca: string, enabled: boolean) => men.q(marcaId, tipo, busca, enabled),
}));

import { ABAS_MENCAO, MencaoPicker } from "./MencaoPicker";

function renderPicker() {
  men.q.mockReturnValue({ data: [], isPending: false, isError: false });
  return rtl.render(
    <MencaoPicker open onOpenChange={() => {}} marcaId="m1" anexados={[]} limiteAtingido={false} onEscolher={() => {}} />,
  );
}

describe("MencaoPicker", () => {
  it("lists Estruturas first and opens on it", () => {
    expect(ABAS_MENCAO[0].tipo).toBe("estrutura");
    renderPicker();
    expect(rtl.screen.getByRole("tab", { name: "Estruturas" }).getAttribute("aria-selected")).toBe("true");
    expect(men.q).toHaveBeenLastCalledWith("m1", "estrutura", "", true);
  });

  it("queries the tab the user picks", async () => {
    renderPicker();
    await userEvent.click(rtl.screen.getByRole("tab", { name: "Minha Pesquisa" }));
    expect(men.q).toHaveBeenLastCalledWith("m1", "pesquisa", "", true);
  });
});
