/** AI-draft attribution label + "Revisão por desuso" badge + the admin 24-month filter wiring. */
import * as rtl from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

afterEach(() => rtl.cleanup());

import { resumo } from "@/test/estruturasFixtures";
import { estruturasQuery } from "@/hooks/geracao/useEstruturas";
import { AtribuicaoIAChip, AtribuicaoIAFrase, RevisaoDesusoBadge, fraseAtribuicaoIA, formatarDataPtBR } from "./atribuicao";
import { EstruturaCard } from "./EstruturaCard";
import { FILTROS_ESTRUTURAS_VAZIOS, contarFiltros, filtrosDeParams, filtrosParaParams } from "./filtros";

describe("AI attribution", () => {
  it("full sentence with handle", () => {
    expect(fraseAtribuicaoIA("criador.exemplo")).toBe(
      "Estrutura gerada por IA a partir de um vídeo público de @criador.exemplo; não é texto do criador.",
    );
    rtl.render(<AtribuicaoIAFrase gerada handle="criador.exemplo" />);
    expect(rtl.screen.getByTestId("atribuicao-ia-frase").textContent).toContain("de @criador.exemplo;");
  });

  it("fallback without handle", () => {
    expect(fraseAtribuicaoIA(null)).toBe("Estrutura gerada por IA a partir de um vídeo público; não é texto do criador.");
    expect(fraseAtribuicaoIA("")).not.toContain("@");
  });

  it("chip on the card when gerada_por_ia (every role), the sentence as accessible name; absent otherwise", () => {
    const { rerender } = rtl.render(
      <MemoryRouter>
        <EstruturaCard estrutura={resumo({ gerada_por_ia: true })} />
      </MemoryRouter>,
    );
    const chip = rtl.screen.getByTestId("atribuicao-ia-chip");
    expect(chip.textContent).toBe("Gerada por IA");
    expect(chip.getAttribute("aria-label")).toContain("de @criador.exemplo; não é texto do criador.");
    // the admin-only raw origem never drives the label: only the all-roles flag does
    for (const extra of [{ gerada_por_ia: false }, { gerada_por_ia: false, origem: "viral_auto" as const }]) {
      rerender(
        <MemoryRouter>
          <EstruturaCard estrutura={resumo(extra)} />
        </MemoryRouter>,
      );
      expect(rtl.screen.queryByTestId("atribuicao-ia-chip")).toBeNull();
    }
  });

  it("renders nothing when not AI-generated, on chip and sentence", () => {
    const a = rtl.render(<AtribuicaoIAChip gerada={false} handle="x" />);
    expect(a.container.textContent).toBe("");
    const b = rtl.render(<AtribuicaoIAFrase gerada={undefined} handle="x" />);
    expect(b.container.textContent).toBe("");
  });
});

describe("Revisão por desuso", () => {
  it("badge formats the date in pt-BR and is absent when null", () => {
    expect(formatarDataPtBR("2026-11-10T12:00:00Z")).toBe("10/11/2026");
    rtl.render(<RevisaoDesusoBadge desde="2026-11-10T12:00:00Z" />);
    expect(rtl.screen.getByText("Revisão por desuso desde 10/11/2026")).toBeTruthy();
    rtl.cleanup();
    const r = rtl.render(<RevisaoDesusoBadge desde={null} />);
    expect(r.container.textContent).toBe("");
  });

  it("the card shows the badge only when the server sent the field", () => {
    rtl.render(
      <MemoryRouter>
        <EstruturaCard estrutura={resumo({ revisao_por_desuso: "2026-11-10T12:00:00Z" })} />
      </MemoryRouter>,
    );
    expect(rtl.screen.getByText(/Revisão por desuso desde 10\/11\/2026/)).toBeTruthy();
  });

  it("filter sends revisao=pendente only when on; round-trips through the URL", () => {
    expect(estruturasQuery({ revisaoPorDesuso: true })).toContain("revisao=pendente");
    expect(estruturasQuery({ revisaoPorDesuso: false })).not.toContain("revisao");
    const f = { ...FILTROS_ESTRUTURAS_VAZIOS, desuso: true };
    expect(filtrosDeParams(filtrosParaParams(f)).desuso).toBe(true);
    expect(contarFiltros(f)).toBe(1);
  });
});
