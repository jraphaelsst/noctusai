/** FormMePublico + EstruturaPicker: estrutura_ids on the wire, ambiguity candidates rendered and re-submitted. */
import * as rtl from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

rtl.configure({ asyncUtilTimeout: 20_000 });
vi.setConfig({ testTimeout: 40_000 });
afterEach(() => rtl.cleanup());

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const m = vi.hoisted(() => ({ criar: vi.fn() }));
vi.mock("@/hooks/geracao/useHeadlines", () => ({
  useCriarLote: () => ({ mutateAsync: m.criar, isPending: false }),
  useContagemEstruturas: () => ({ data: undefined }),
  useItensAprovados: () => ({ data: [], showSkeleton: false, isError: false }),
}));
vi.mock("@/hooks/geracao/useBiblioteca", () => ({
  usePerfisMonitorados: () => ({ data: [{ id: "p1", handle: "ana", status: "ativo", virais: 1 }] }),
}));
vi.mock("@/hooks/geracao/useTaxonomias", () => ({ useTaxonomias: () => ({ data: { formatos: [], gatilhos: [], tons: [] }, showSkeleton: false, isError: false }) }));
vi.mock("@/hooks/usePesquisa", () => ({
  usePesquisaVariaveis: () => ({
    data: [{ slug: "crencas", label: "Crenças", grupo: "especialista", description: "d", sort_order: 1 }],
    showSkeleton: false,
    isError: false,
  }),
}));
// The real picker is covered by EstruturaPicker.test; here it is a stub that picks one Estrutura.
vi.mock("@/components/geracao/estruturas/EstruturaPicker", () => ({
  EstruturaPicker: (p: { onChange: (v: unknown[]) => void }) => (
    <button type="button" onClick={() => p.onChange([{ id: "e1", codigo: 1, formula_headline: "F", formato: "reels", perfil: { id: "p1", handle: "ana", nome: null, foto_url: null } }])}>
      escolher estrutura
    </button>
  ),
}));

import { toast } from "sonner";

import { FormMePublico } from "./FormMePublico";

const lote = { id: "l1" } as never;

async function preparar() {
  const onCriado = vi.fn();
  rtl.render(<FormMePublico who="me" marcaId="m1" onCriado={onCriado} />);
  await userEvent.click(rtl.screen.getByRole("checkbox", { name: "Crenças" }));
  return onCriado;
}

beforeEach(() => vi.clearAllMocks());

describe("FormMePublico + estruturas", () => {
  it("sends estrutura_ids (and no referencia) when Estruturas are picked", async () => {
    m.criar.mockResolvedValue(lote);
    await preparar();
    await userEvent.click(rtl.screen.getByRole("button", { name: "escolher estrutura" }));
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalled());
    const body = m.criar.mock.calls[0]![0];
    expect(body.estrutura_ids).toEqual(["e1"]);
    expect(body.referencia).toBeUndefined();
  });

  it("without Estruturas the body has no estrutura_ids", async () => {
    m.criar.mockResolvedValue(lote);
    await preparar();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalled());
    expect("estrutura_ids" in m.criar.mock.calls[0]![0]).toBe(false);
  });

  it("renders the ambiguity candidates and re-submits with referencia: perfil", async () => {
    const cand = [
      { perfil_id: "p1", handle: "ana.a", nome: "Ana A" },
      { perfil_id: "p2", handle: "ana.b", nome: "Ana B" },
    ];
    m.criar.mockRejectedValueOnce(Object.assign(new Error("[422] x"), { code: "perfil_ambiguo", status: 422, body: { code: "perfil_ambiguo", candidatos: cand } }));
    m.criar.mockResolvedValueOnce(lote);
    const onCriado = await preparar();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    const painel = await rtl.screen.findByTestId("candidatos-perfil");
    expect(rtl.within(painel).getByRole("button", { name: /@ana\.b/ })).toBeTruthy();
    expect((toast.error as ReturnType<typeof vi.fn>).mock.calls.flat().join(" ")).toContain("Mais de um perfil");
    await userEvent.click(rtl.within(painel).getByRole("button", { name: /@ana\.b/ }));
    await rtl.waitFor(() => expect(m.criar).toHaveBeenCalledTimes(2));
    expect(m.criar.mock.calls[1]![0].referencia).toEqual({ tipo: "perfil", perfil_ids: ["p2"] });
    await rtl.waitFor(() => expect(onCriado).toHaveBeenCalled());
    expect(rtl.screen.queryByTestId("candidatos-perfil")).toBeNull();
  });

  it("a refused generation is toasted with the catalogue sentence, never silent", async () => {
    m.criar.mockRejectedValue(Object.assign(new Error("[422] x"), { code: "estrutura_obrigatoria_invalida", status: 422 }));
    await preparar();
    await userEvent.click(rtl.screen.getByRole("button", { name: "Gerar Headlines" }));
    await rtl.waitFor(() => expect(toast.error).toHaveBeenCalledWith("Uma das estruturas escolhidas não está disponível."));
  });
});
