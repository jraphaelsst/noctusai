/**
 * QualificacaoContratoForm — identidade tipo (RG/RNE/RNM) and the pacto
 * antenupcial citation with provenance (contrato-partes-CONTRACT §3,
 * migration 193). Synthetic data only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { QualificacaoContratoForm } from "./QualificacaoContratoForm";
import type { QualificacaoContratoRegistro } from "@/hooks/useQualificacaoContrato";

function registro(over: Partial<QualificacaoContratoRegistro> = {}): QualificacaoContratoRegistro {
  return { id: "cl1", regime_bens: "Comunhão universal de bens", estado_civil: "Casado(a)", ...over };
}

async function render(over: Record<string, unknown> = {}) {
  const rtl = await import("@testing-library/react");
  const onSalvar = vi.fn();
  rtl.render(
    <QualificacaoContratoForm
      registro={registro()}
      showSkeleton={false}
      isRefreshing={false}
      isError={false}
      onRetry={vi.fn()}
      salvando={false}
      erro={null}
      onSalvar={onSalvar}
      testId="qc"
      {...over}
    />,
  );
  return { ...rtl, onSalvar };
}

describe("QualificacaoContratoForm", () => {
  it("skeleton only while nothing loaded", async () => {
    const { screen } = await render({ registro: undefined, showSkeleton: true });
    expect(screen.getByTestId("qc-skeleton")).toBeTruthy();
  });

  it("🔴 a pacto value read from the document shows its provenance and that it awaits confirmation", async () => {
    const { screen } = await render({
      registro: registro({
        pacto_antenupcial_data: "2015-03-20",
        pacto_antenupcial_data_origem: "pacto_antenupcial",
        pacto_antenupcial_data_confirmado_em: null,
        pacto_antenupcial_tabelionato: "2º Tabelião de Notas de Exemplo",
        pacto_antenupcial_tabelionato_origem: "manual",
      }),
    });
    const data = screen.getByTestId("qc-pacto_antenupcial_data").textContent ?? "";
    expect(data).toContain("20/03/2015");
    expect(data).toContain("lido do pacto antenupcial — aguardando confirmação");
    expect(screen.getByTestId("qc-pacto_antenupcial_tabelionato").textContent).toContain("digitado");
    expect(screen.getByTestId("qc-pacto_antenupcial_livro").textContent).toContain("falta");
  });

  it("no pacto block for a regime without pacto (and nothing on file)", async () => {
    const { screen } = await render({ registro: registro({ regime_bens: "Comunhão parcial de bens" }) });
    expect(screen.queryByTestId("qc-pacto")).toBeNull();
    expect(screen.getByTestId("qc-identidade").textContent).toContain("RG");
  });

  it("🔴 saves only what changed — a foreign party's RNE and the pacto livro", async () => {
    const { screen, fireEvent, onSalvar } = await render({
      registro: registro({ pacto_antenupcial_folha: "12" }),
    });
    fireEvent.click(screen.getByTestId("qc-editar"));
    fireEvent.change(screen.getByTestId("qc-identidade-tipo"), { target: { value: "rne" } });
    fireEvent.change(screen.getByTestId("qc-pacto_antenupcial_livro-input"), { target: { value: "3" } });
    fireEvent.click(screen.getByTestId("qc-salvar"));
    expect(onSalvar).toHaveBeenCalledWith({ identidade_tipo: "rne", pacto_antenupcial_livro: "3" });
  });
});
