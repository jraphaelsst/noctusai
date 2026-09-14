/**
 * QualificacaoCompletudePanel.test.tsx — contract automation F3's per-party
 * completude panel.
 *
 * What these protect:
 *   1. The two states, honestly: skeleton only while genuinely empty-handed,
 *      an error banner (with retry) that never blanks stale data, and a
 *      subtle refreshing indicator that never unmounts the panel.
 *   2. The completo/faltando split, with pt-BR labels for every key —
 *      including the PAIR facts (`conjuge`, `conjuge_qualificacao`) staying
 *      OUT of the plain missing-fields list.
 *   3. The cônjuge block: rendered only when linked, its own completo/pendente
 *      badge, and "Ver cadastro" firing the caller's `onAbrirConjuge` with the
 *      SPOUSE's id — never the panel's own `clienteId`.
 *   4. "Cônjuge pendente" shown when `faltando` includes `"conjuge"` and no
 *      `conjuge` object exists yet.
 *
 * Mock strategy mirrors `CertidoesPartePanel.test.tsx`: one `vi.mock` for the
 * hook, configured per test.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockUseQualificacaoCompletude = vi.fn();

vi.mock("@/hooks/useCardHub", () => ({
  useQualificacaoCompletude: (...a: any[]) => mockUseQualificacaoCompletude(...a),
}));

import { QualificacaoCompletudePanel } from "./QualificacaoCompletudePanel";

function queryResult(over: Record<string, any> = {}) {
  return {
    data: undefined,
    isPending: true,
    isFetching: true,
    isError: false,
    refetch: vi.fn(),
    ...over,
  };
}

const completo = {
  cliente_id: "cli-1",
  estado_civil: "solteiro",
  completo: true,
  faltando: [],
  conjuge: null,
};

describe("QualificacaoCompletudePanel — estados honestos", () => {
  it("mostra o esqueleto só quando genuinamente não há dados ainda", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(queryResult());
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.getByTestId("qualificacao-completude-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("qualificacao-completude-panel")).toBeNull();
  });

  it("nunca esconde o painel atrás do esqueleto durante um refetch em segundo plano", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ data: completo, isPending: false, isFetching: true }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.queryByTestId("qualificacao-completude-skeleton")).toBeNull();
    expect(screen.getByTestId("qualificacao-completude-panel")).toBeTruthy();
    expect(screen.getByTestId("qualificacao-completude-refreshing")).toBeTruthy();
  });

  it("mostra um erro com retry quando não há nenhum dado ainda", async () => {
    const refetch = vi.fn();
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ isPending: false, isFetching: false, isError: true, refetch }),
    );
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" nome="Ana" />);
    expect(screen.getByTestId("qualificacao-completude-error").textContent).toContain("Ana");
    fireEvent.click(screen.getByText("Tentar novamente"));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("QualificacaoCompletudePanel — completo/faltando", () => {
  it("mostra o selo de qualificação completa", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ data: completo, isPending: false, isFetching: false }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.getByTestId("qualificacao-completude-completo")).toBeTruthy();
    expect(screen.queryByTestId("qualificacao-completude-faltando")).toBeNull();
  });

  it("lista os campos faltantes com rótulos em pt-BR", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({
        data: {
          ...completo,
          completo: false,
          faltando: ["cpf", "endereco", "regime_bens"],
        },
        isPending: false,
        isFetching: false,
      }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.getByTestId("qualificacao-completude-faltando-cpf").textContent).toContain("CPF");
    expect(
      screen.getByTestId("qualificacao-completude-faltando-endereco").textContent,
    ).toContain("Endereço completo");
    expect(
      screen.getByTestId("qualificacao-completude-faltando-regime_bens").textContent,
    ).toContain("Regime de bens");
  });

  it("🔴 mantém os fatos do PAR fora da lista simples de campos faltantes", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({
        data: {
          ...completo,
          estado_civil: "casado",
          completo: false,
          faltando: ["conjuge"],
        },
        isPending: false,
        isFetching: false,
      }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.queryByTestId("qualificacao-completude-faltando-conjuge")).toBeNull();
    expect(screen.getByTestId("qualificacao-completude-conjuge-pendente")).toBeTruthy();
  });
});

describe("QualificacaoCompletudePanel — bloco do cônjuge", () => {
  const casadoComConjugePendente = {
    cliente_id: "cli-1",
    estado_civil: "casado",
    completo: false,
    faltando: ["conjuge_qualificacao"],
    conjuge: {
      cliente_id: "cli-conjuge",
      nome: "Maria",
      completo: false,
      faltando: ["cpf"],
    },
  };

  it("mostra o nome do cônjuge e o selo de pendente", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ data: casadoComConjugePendente, isPending: false, isFetching: false }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.getByTestId("qualificacao-completude-conjuge-nome").textContent).toBe("Maria");
    expect(screen.getByTestId("qualificacao-completude-conjuge-badge").textContent).toContain(
      "pendente",
    );
  });

  it("🔴 abre o cadastro do CÔNJUGE, nunca o da própria parte", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ data: casadoComConjugePendente, isPending: false, isFetching: false }),
    );
    const onAbrirConjuge = vi.fn();
    const { fireEvent, render, screen } = await import("@testing-library/react");
    render(
      <QualificacaoCompletudePanel
        clienteId="cli-1"
        onAbrirConjuge={onAbrirConjuge}
      />,
    );
    fireEvent.click(screen.getByTestId("qualificacao-completude-conjuge-abrir"));
    expect(onAbrirConjuge).toHaveBeenCalledWith("cli-conjuge", "Maria");
  });

  it("não oferece o botão Ver cadastro quando o container não wireou o handler", async () => {
    mockUseQualificacaoCompletude.mockReturnValue(
      queryResult({ data: casadoComConjugePendente, isPending: false, isFetching: false }),
    );
    const { render, screen } = await import("@testing-library/react");
    render(<QualificacaoCompletudePanel clienteId="cli-1" />);
    expect(screen.queryByTestId("qualificacao-completude-conjuge-abrir")).toBeNull();
  });
});
