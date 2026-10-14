/** ImovelAvaliacaoSection — valuation characteristics (migration 264). */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelAvaliacaoSection, { mostraLote } from "./ImovelAvaliacaoSection";
import type { ImovelDados } from "@/hooks/useImovelDados";

function dados(over: Partial<ImovelDados> = {}): ImovelDados {
  return {
    codigo: "ONE9001",
    padrao_construtivo: null,
    estado_conservacao: null,
    area_terreno_m2: null,
    area_construida_m2: null,
    testada_m: null,
    profundidade_m: null,
    topografia: null,
    posicao_lote: null,
    avaliacao_campos_atualizado_em: null,
    avaliacao_campos_atualizado_por: null,
    ...over,
  } as ImovelDados;
}

async function render(
  p: Partial<React.ComponentProps<typeof ImovelAvaliacaoSection>> = {},
) {
  const rtl = await import("@testing-library/react");
  const view = rtl.render(
    <ImovelAvaliacaoSection
      dados={dados()}
      categoria="Casa"
      loading={false}
      saving={false}
      error={null}
      onSave={vi.fn()}
      {...p}
    />,
  );
  return { ...view, ...rtl };
}

describe("ImovelAvaliacaoSection", () => {
  it("shows a skeleton while loading, not an empty state", async () => {
    const { screen } = await render({ dados: undefined, loading: true });
    expect(screen.getByTestId("imovel-avaliacao-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("imovel-avaliacao-erro")).toBeNull();
  });

  it("shows an error when the data failed to load", async () => {
    const { screen } = await render({ dados: undefined });
    expect(screen.getByTestId("imovel-avaliacao-erro")).toBeTruthy();
  });

  it("shows the empty hint when nothing is filled", async () => {
    const { screen } = await render();
    expect(screen.getByTestId("imovel-avaliacao-vazio")).toBeTruthy();
    expect(screen.getByTestId("v-padrao").textContent).toBe("Não informado");
  });

  it("shows values and who/when", async () => {
    const { screen } = await render({
      dados: dados({
        padrao_construtivo: "superior",
        estado_conservacao: "reparos_simples",
        area_terreno_m2: 250.5,
        avaliacao_campos_atualizado_em: "2026-10-01T12:00:00Z",
        avaliacao_campos_atualizado_por: { id: "u1", nome: "Ana" },
      }),
    });
    expect(screen.getByTestId("v-padrao").textContent).toBe("Superior");
    expect(screen.getByTestId("v-conservacao").textContent).toBe("Necessita de reparos simples");
    expect(screen.getByTestId("v-area-terreno").textContent).toContain("m²");
    expect(screen.getByTestId("imovel-avaliacao-autoria").textContent).toContain("Preenchido por Ana");
  });

  it("hides lot fields for apartamento but keeps terreno area", async () => {
    const { screen } = await render({ categoria: "Apartamento" });
    expect(screen.queryByTestId("v-testada")).toBeNull();
    expect(screen.getByTestId("v-area-terreno")).toBeTruthy();
    expect(mostraLote("Apartamento")).toBe(false);
    expect(mostraLote("Terreno")).toBe(true);
    expect(mostraLote(null)).toBe(true);
  });

  it("saves a patch with parsed numbers and nulls for blanks", async () => {
    const onSave = vi.fn();
    const { screen, fireEvent } = await render({ onSave });
    fireEvent.click(screen.getByTestId("imovel-avaliacao-editar"));
    fireEvent.change(screen.getByTestId("avaliacao-padrao"), { target: { value: "fino" } });
    fireEvent.change(screen.getByTestId("avaliacao-area_terreno_m2"), { target: { value: "300,5" } });
    fireEvent.change(screen.getByTestId("avaliacao-topografia"), { target: { value: "plano" } });
    fireEvent.click(screen.getByTestId("imovel-avaliacao-salvar"));
    expect(onSave).toHaveBeenCalledWith({
      padrao_construtivo: "fino",
      estado_conservacao: null,
      area_terreno_m2: 300.5,
      area_construida_m2: null,
      testada_m: null,
      profundidade_m: null,
      topografia: "plano",
      posicao_lote: null,
    });
  });

  it("rejects a non-positive measure without calling save", async () => {
    const onSave = vi.fn();
    const { screen, fireEvent } = await render({ onSave });
    fireEvent.click(screen.getByTestId("imovel-avaliacao-editar"));
    fireEvent.change(screen.getByTestId("avaliacao-testada_m"), { target: { value: "-3" } });
    fireEvent.click(screen.getByTestId("imovel-avaliacao-salvar"));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByTestId("imovel-avaliacao-msg-erro")).toBeTruthy();
  });

  it("surfaces a save error", async () => {
    const { screen, fireEvent } = await render({ error: "falhou" });
    fireEvent.click(screen.getByTestId("imovel-avaliacao-editar"));
    expect(screen.getByTestId("imovel-avaliacao-msg-erro").textContent).toBe("falhou");
  });
});
