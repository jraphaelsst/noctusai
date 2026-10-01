/** RoteirosSection × the new roteiro flow: the interest list mounts only when a
 *  `clienteId` is passed, and a saved roteiro shows its `data_visita`. */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/interesses/ImovelInteressesList", () => ({
  ImovelInteressesList: (p: { clienteId: string; atendimentoId?: string | null }) => (
    <div data-testid="lista-interesses" data-cliente={p.clienteId} data-at={p.atendimentoId ?? ""} />
  ),
}));

import { cleanup, render } from "@testing-library/react";

import { RoteirosSection, type RoteirosSectionProps } from "./RoteirosSection";

afterEach(cleanup);

const noop = vi.fn();
function props(over: Partial<RoteirosSectionProps> = {}): RoteirosSectionProps {
  return {
    roteiros: [],
    onCriar: noop,
    onRemover: noop,
    onGerarPdf: noop,
    onPatchVisita: noop,
    onAddVisita: noop,
    onRemoveVisita: noop,
    onPatchProposta: noop,
    ...over,
  };
}

describe("RoteirosSection — interesses + data_visita", () => {
  it("stays presentational without clienteId", () => {
    expect(render(<RoteirosSection {...props()} />).queryByTestId("lista-interesses")).toBeNull();
  });

  it("mounts the interest list with clienteId/atendimentoId", () => {
    const { getByTestId } = render(
      <RoteirosSection {...props({ clienteId: "c1", atendimentoId: "at1" })} />,
    );
    const el = getByTestId("lista-interesses");
    expect(el.getAttribute("data-cliente")).toBe("c1");
    expect(el.getAttribute("data-at")).toBe("at1");
  });

  it("shows the visit date (dd/mm/aaaa, no timezone shift)", () => {
    const { getByTestId } = render(
      <RoteirosSection
        {...props({
          roteiros: [
            {
              id: "r1",
              atendimento_id: "at1",
              titulo: "Terça",
              created_at: "2026-09-30T12:00:00Z",
              data_visita: "2026-10-01",
              visitas: [],
              contagem: { total: 0, realizadas: 0, nao_realizadas: 0, pendentes: 0 },
            },
          ],
        })}
      />,
    );
    expect(getByTestId("roteiro-data-visita-chip").textContent).toBe("visita em 01/10/2026");
  });
});
