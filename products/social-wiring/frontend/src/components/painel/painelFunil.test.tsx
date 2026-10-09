import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

const pendentes = vi.fn();
const metricas = vi.fn();
vi.mock("@/hooks/useRoteirosFeedback", () => ({ useRoteirosPendentesFeedback: () => pendentes() }));
vi.mock("@/hooks/useMetricasFunil", () => ({ useMetricasFunil: () => metricas() }));
vi.mock("react-router-dom", () => ({
  Link: ({ to, children, ...rest }: any) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

import { FunilAtendimentoCard } from "./FunilAtendimentoCard";
import { VisitasSemResposta } from "./VisitasSemResposta";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("VisitasSemResposta", () => {
  it("lists due roteiros with a badge and a link to the card", () => {
    pendentes.mockReturnValue({
      data: [{ roteiro_id: "r1", cliente_id: "c1", atendimento_id: "a1", cliente_nome: "Ana", data_visita: "2026-10-09", visitas: [] }],
      isPending: false,
      isFetching: false,
      isError: false,
    });
    const { getByTestId } = render(<VisitasSemResposta />);
    expect(getByTestId("painel-visitas-sem-resposta-badge").textContent).toBe("1");
    const link = getByTestId("painel-visita-pendente-r1");
    expect(link.textContent).toContain("Visita de Ana aconteceu?");
    expect(link.getAttribute("href")).toBe("/clientes?cliente=c1&aba=roteiros");
  });

  it("never claims 'nenhuma' while the first load is pending", () => {
    pendentes.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    const { getByTestId, queryByText } = render(<VisitasSemResposta />);
    expect(getByTestId("painel-visitas-sem-resposta-loading")).toBeTruthy();
    expect(queryByText(/Nenhuma visita/)).toBeNull();
  });
});

describe("FunilAtendimentoCard", () => {
  it("renders the counts, the motivos and the averages (dash when unknown)", () => {
    metricas.mockReturnValue({
      data: {
        leads: 10, com_roteiro: 4, visitas_agendadas: 6, visitas_realizadas: 3,
        visitas_nao_realizadas: { reagendada: 2 },
        propostas_criadas: 2, propostas_aceitas: 1, propostas_recusadas: 1,
        tempo_medio_dias: { lead_a_roteiro: 2.5, roteiro_a_visita: null, visita_a_proposta: 1, proposta_a_aceite: null },
      },
      isPending: false, isFetching: false, isError: false,
    });
    const { getByTestId } = render(<FunilAtendimentoCard />);
    const card = getByTestId("painel-funil-atendimento");
    expect(card.textContent).toContain("Leads");
    expect(getByTestId("painel-funil-nao-realizadas").textContent).toContain("Reagendada: 2");
    expect(card.textContent).toContain("Lead → roteiro: 2,5 d");
    expect(card.textContent).toContain("Roteiro → visita: —");
  });

  it("skeletons without data, error on failure", () => {
    metricas.mockReturnValue({ data: undefined, isPending: true, isFetching: true, isError: false });
    expect(render(<FunilAtendimentoCard />).getByTestId("painel-funil-atendimento-loading")).toBeTruthy();
    cleanup();
    metricas.mockReturnValue({ data: undefined, isPending: false, isFetching: false, isError: true });
    expect(render(<FunilAtendimentoCard />).getByText(/Não foi possível/)).toBeTruthy();
  });
});
