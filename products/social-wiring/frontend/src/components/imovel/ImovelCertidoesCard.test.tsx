/**
 * ImovelCertidoesCard — two things are load-bearing here.
 *
 * 1. THE 30-DAY OFFICE RULE. A certidão must be less than 30 days old at
 *    signing. `hoje` is a prop precisely so this is testable without faking
 *    timers, and the boundary (29 vs 30) is asserted on both sides: an
 *    off-by-one here means either a nagging warning on a fresh certidão or
 *    silence on a stale one.
 * 2. THE PATCH BODY per tipo. `confirmar_extracao` 400s a field the tipo does
 *    not carry, so the editor must offer exactly `CAMPOS_ESTRUTURA_POR_TIPO`
 *    — and an unedited confirmation must send `{}`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import ImovelCertidoesCard from "./ImovelCertidoesCard";
import type { ImovelCertidao } from "@/hooks/useImovelContrato";

/** Fixed "today" so the age assertions never depend on the wall clock. */
const HOJE = new Date("2026-03-31T12:00:00Z");

function certidao(over: Partial<ImovelCertidao> = {}): ImovelCertidao {
  return {
    tipo: "cnd_iptu",
    documento_id: "doc-1",
    numero: "123456",
    emitida_em: "2026-03-20",
    validade_ate: "2026-06-20",
    resultado: "negativa",
    inscricao_imobiliaria: "111.222.333",
    confirmado: false,
    ...over,
  };
}

async function render(props: Partial<Parameters<typeof ImovelCertidoesCard>[0]> = {}) {
  const rtl = await import("@testing-library/react");
  const onUpload = vi.fn();
  const onConfirmar = vi.fn();
  const onSalvarManual = vi.fn();
  const onRemoverManual = vi.fn();
  const view = rtl.render(
    <ImovelCertidoesCard
      certidoes={[certidao()]}
      showSkeleton={false}
      isRefreshing={false}
      isError={false}
      uploading={false}
      savingDocumentoId={null}
      savingManualTipo={null}
      onUpload={onUpload}
      onConfirmar={onConfirmar}
      onSalvarManual={onSalvarManual}
      onRemoverManual={onRemoverManual}
      hoje={HOJE}
      {...props}
    />,
  );
  return { ...rtl, ...view, onUpload, onConfirmar, onSalvarManual, onRemoverManual };
}

describe("ImovelCertidoesCard — the 30-day office rule", () => {
  it("🔴 warns when the certidão is exactly 30 days old", async () => {
    // "Less than 30 days" — so 30 is already too old. The boundary is the
    // whole rule; a `>` here would pass a certidão the office refuses.
    const { getByTestId } = await render({
      certidoes: [certidao({ emitida_em: "2026-03-01" })],
    });
    const aviso = getByTestId("certidao-cnd_iptu-idade");
    expect(aviso.textContent).toContain("30 dias");
    expect(aviso.textContent).toContain("peça uma nova");
  });

  it("does NOT warn at 29 days", async () => {
    const { getByTestId, queryByTestId } = await render({
      certidoes: [certidao({ emitida_em: "2026-03-02" })],
    });
    expect(queryByTestId("certidao-cnd_iptu-idade")).toBeNull();
    expect(getByTestId("certidao-cnd_iptu-idade-ok").textContent).toContain("29");
  });

  it("asks for the emission date when the read did not find one", async () => {
    // Without it the 30-day rule cannot be checked at all, which is a
    // different situation from "checked and fine".
    const { getByTestId, queryByTestId } = await render({
      certidoes: [certidao({ emitida_em: null })],
    });
    expect(getByTestId("certidao-cnd_iptu-sem-data")).toBeTruthy();
    expect(queryByTestId("certidao-cnd_iptu-idade")).toBeNull();
  });
});

describe("ImovelCertidoesCard — review and confirm", () => {
  it("🔴 confirms with an EMPTY patch when nothing was edited", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.click(getByTestId("certidao-cnd_iptu-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith("doc-1", "cnd_iptu", {});
  });

  it("sends only the corrected field", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId("certidao-cnd_iptu-numero"), {
      target: { value: "999" },
    });
    fireEvent.click(getByTestId("certidao-cnd_iptu-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith("doc-1", "cnd_iptu", { numero: "999" });
  });

  it("🔴 sends `null` for a field the operator emptied", async () => {
    const { getByTestId, fireEvent, onConfirmar } = await render();
    fireEvent.change(getByTestId("certidao-cnd_iptu-numero"), { target: { value: "" } });
    fireEvent.click(getByTestId("certidao-cnd_iptu-confirmar"));
    expect(onConfirmar).toHaveBeenCalledWith("doc-1", "cnd_iptu", { numero: null });
  });

  it("🔴 offers only the fields the tipo carries", async () => {
    // A `numero` on a condomínio declaration is a 400, not a blank field.
    const { getByTestId, queryByTestId } = await render({
      certidoes: [
        certidao({ tipo: "cnd_condominio", documento_id: "doc-2", numero: null }),
      ],
    });
    expect(getByTestId("certidao-cnd_condominio-emitida_em")).toBeTruthy();
    expect(getByTestId("certidao-cnd_condominio-resultado")).toBeTruthy();
    expect(queryByTestId("certidao-cnd_condominio-numero")).toBeNull();
    expect(queryByTestId("certidao-cnd_condominio-validade_ate")).toBeNull();
  });

  it("distinguishes a confirmed certidão from an automatic read", async () => {
    const { getByTestId, queryByTestId } = await render({
      certidoes: [certidao({ confirmado: true })],
    });
    expect(getByTestId("certidao-cnd_iptu-confirmada")).toBeTruthy();
    expect(queryByTestId("certidao-cnd_iptu-sugestao")).toBeNull();
  });

  it("says which certidões of the group are missing", async () => {
    const { getByTestId } = await render({ certidoes: [] });
    expect(getByTestId("certidao-cnd_iptu-ausente")).toBeTruthy();
    expect(getByTestId("certidao-cnd_condominio-ausente")).toBeTruthy();
    // The matrícula is uploaded on the documents card — so its absence points
    // there rather than at this card's own upload.
    expect(getByTestId("certidao-matricula-ausente").textContent).toContain(
      "Documentos do imóvel",
    );
  });

  it("uploads the selected tipo", async () => {
    const { getByTestId, fireEvent, onUpload } = await render({ certidoes: [] });
    const file = new File(["x"], "cnd.pdf", { type: "application/pdf" });
    fireEvent.change(getByTestId("imovel-certidao-input"), { target: { files: [file] } });
    expect(onUpload).toHaveBeenCalledWith(file, "cnd_iptu");
  });

  it("owns its own file input, so uploads cannot land on another card", async () => {
    const { container } = await render();
    expect(container.querySelectorAll('input[type="file"]').length).toBe(1);
  });

  it("🔴 keeps the list mounted while refreshing (no lying loading state)", async () => {
    // `isRefreshing` is an indicator, never an early return.
    // KB § PATTERNS/frontend/lying-loading-state.md
    const { getByTestId } = await render({ isRefreshing: true });
    expect(getByTestId("imovel-certidoes-refreshing")).toBeTruthy();
    expect(getByTestId("certidao-cnd_iptu")).toBeTruthy();
  });

  it("shows the skeleton only on a genuine first load", async () => {
    const { getByTestId } = await render({ certidoes: undefined, showSkeleton: true });
    expect(getByTestId("imovel-certidoes-skeleton")).toBeTruthy();
  });
});

describe("ImovelCertidoesCard — typed with no file (migration 306)", () => {
  it("🔴 a tipo with no document offers 'Preencher manualmente' and saves the FULL record", async () => {
    const { getByTestId, queryByTestId, fireEvent, onSalvarManual } = await render({
      certidoes: [],
    });
    expect(queryByTestId("certidao-cnd_condominio")).toBeNull();
    fireEvent.click(getByTestId("certidao-cnd_condominio-preencher-manual"));

    const salvar = getByTestId("certidao-cnd_condominio-salvar-manual") as HTMLButtonElement;
    // An all-empty record is refused by the backend — never sent.
    expect(salvar.disabled).toBe(true);
    // Only the tipo's own fields are offered (condomínio: emissão + resultado).
    expect(queryByTestId("certidao-cnd_condominio-numero")).toBeNull();

    fireEvent.change(getByTestId("certidao-cnd_condominio-emitida_em"), {
      target: { value: "2026-03-25" },
    });
    expect(salvar.disabled).toBe(false);
    fireEvent.click(salvar);
    expect(onSalvarManual).toHaveBeenCalledWith("cnd_condominio", {
      emitida_em: "2026-03-25",
      resultado: null,
    });
  });

  it("cancelling a new typed entry returns to the empty state", async () => {
    const { getByTestId, queryByTestId, fireEvent } = await render({ certidoes: [] });
    fireEvent.click(getByTestId("certidao-matricula-preencher-manual"));
    fireEvent.click(getByTestId("certidao-matricula-cancelar-manual"));
    expect(queryByTestId("certidao-matricula-salvar-manual")).toBeNull();
    expect(getByTestId("certidao-matricula-ausente")).toBeTruthy();
  });

  it("a typed reading is marked 'sem arquivo', edits through the manual route and can be removed", async () => {
    const { getByTestId, queryByTestId, fireEvent, onSalvarManual, onConfirmar, onRemoverManual } =
      await render({
        certidoes: [
          certidao({
            tipo: "matricula",
            documento_id: null,
            numero: null,
            validade_ate: null,
            resultado: null,
            inscricao_imobiliaria: null,
            emitida_em: "2026-03-20",
            confirmado: true,
            sem_arquivo: true,
            manual_id: "m-1",
          }),
        ],
      });
    expect(getByTestId("certidao-matricula-manual").textContent).toContain("sem arquivo");
    expect(queryByTestId("certidao-matricula-confirmar")).toBeNull();
    // Unchanged → nothing to save.
    const salvar = getByTestId("certidao-matricula-salvar-manual") as HTMLButtonElement;
    expect(salvar.disabled).toBe(true);

    fireEvent.change(getByTestId("certidao-matricula-emitida_em"), {
      target: { value: "2026-03-28" },
    });
    fireEvent.click(salvar);
    expect(onSalvarManual).toHaveBeenCalledWith("matricula", { emitida_em: "2026-03-28" });
    expect(onConfirmar).not.toHaveBeenCalled();

    fireEvent.click(getByTestId("certidao-matricula-remover-manual"));
    expect(onRemoverManual).toHaveBeenCalledWith("matricula");
  });

  it("shows the in-flight state on the typed entry being saved", async () => {
    const { getByTestId } = await render({
      certidoes: [
        certidao({ tipo: "cnd_condominio", documento_id: null, sem_arquivo: true, manual_id: "m-2" }),
      ],
      savingManualTipo: "cnd_condominio",
    });
    expect((getByTestId("certidao-cnd_condominio-remover-manual") as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});
