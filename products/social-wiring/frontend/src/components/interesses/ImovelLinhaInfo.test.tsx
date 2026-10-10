/** ImovelLinhaInfo — a manual imóvel (no foto, no preço) renders neutrally with a Manual badge. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { ImovelLinhaInfo } from "./ImovelLinhaInfo";
import { imovelResumo } from "./fixtures";

afterEach(cleanup);

describe("ImovelLinhaInfo — manual imóvel", () => {
  it("shows placeholder thumb, '—' valor and the Manual badge", () => {
    const { getByTestId } = render(
      <ImovelLinhaInfo
        imovel={imovelResumo("SW-0001", {
          fonte: "manual",
          foto_destaque: null,
          valor: null,
          valor_venda: null,
          valor_locacao: null,
          endereco: null,
          logradouro: null,
          numero: null,
          complemento: null,
          bairro: null,
          cidade: null,
          uf: null,
        })}
      />,
    );
    expect(getByTestId("imovel-thumb-vazio")).toBeTruthy();
    expect(getByTestId("imovel-valor").textContent).toBe("—");
    expect(getByTestId("imovel-manual-badge").textContent).toBe("Manual");
    expect(getByTestId("imovel-endereco").textContent).toBe(
      "Endereço não informado",
    );
  });

  it("a Vista imóvel has no badge", () => {
    const { queryByTestId } = render(
      <ImovelLinhaInfo imovel={imovelResumo("ONE1")} />,
    );
    expect(queryByTestId("imovel-manual-badge")).toBeNull();
  });
});
