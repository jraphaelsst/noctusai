/**
 * RoteirosSection — the card's Roteiros tab, one test per row of the roteiro
 * lifecycle state matrix (mockup NOTES §2) plus the standing guarantees:
 *
 *  - the LOADING GATE (an empty state must never render over roteiros that exist —
 *    `KB § PATTERNS/frontend/lying-loading-state.md`);
 *  - everything is rendered from the server's `permissoes` (never re-derived);
 *  - "Baixar PDF" exists ONLY on a gerado roteiro, never on a draft.
 *
 * Fixtures are built to the contract's shapes (`roteiroFixtures.ts`).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { RoteirosSection, type RoteirosSectionProps } from "./RoteirosSection";
import type { Roteiro, Visita } from "@/types/cardHub";
import {
  imovelFx as imovel,
  permissoesGerado,
  roteiroFx,
  visitaFx as visita,
} from "./roteiroFixtures";

/** A GERADO roteiro by default — the state outcomes live in. */
function roteiro(over: Partial<Roteiro> = {}): Roteiro {
  return roteiroFx({ status: "gerado", ...over });
}
/** A draft. */
const rascunho = (over: Partial<Roteiro> = {}): Roteiro => roteiroFx({ status: "rascunho", ...over });

function baseProps(overrides: Partial<RoteirosSectionProps> = {}): RoteirosSectionProps {
  return {
    roteiros: [],
    onCriar: vi.fn(),
    onEditarRascunho: vi.fn(),
    onRemover: vi.fn(),
    onBaixarPdf: vi.fn(),
    onReabrir: vi.fn(),
    onPatchRoteiro: vi.fn(),
    onPatchVisita: vi.fn(),
    onReagendar: vi.fn(),
    ...overrides,
  };
}

async function render(props: RoteirosSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(RoteirosSection, props));
}

/** Same as `render`, plus `fireEvent` for the interaction tests below. */
async function renderWith(props: RoteirosSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return {
    ...rtl.render(React.createElement(RoteirosSection, props)),
    fireEvent: rtl.fireEvent,
  };
}

describe("RoteirosSection — states", () => {
  it("offers Criar Roteiro even with nothing to show", async () => {
    // You come to this tab to ADD; an empty state with no way out is a dead end.
    const { getByTestId } = await render(baseProps());
    expect(getByTestId("roteiros-empty")).toBeTruthy();
    expect(getByTestId("roteiro-criar-trigger")).toBeTruthy();
  });

  it("🔴 never renders the empty state while loading", async () => {
    // The lying-loading-state class: the caller gates on `isPending ||
    // isFetching`, so a background refetch must show the skeleton, NOT
    // "nenhum roteiro criado" over roteiros that exist.
    const { getByTestId, queryByTestId } = await render(
      baseProps({ loading: true, roteiros: [] }),
    );
    expect(getByTestId("roteiros-loading")).toBeTruthy();
    expect(queryByTestId("roteiros-empty")).toBeNull();
  });

  it("shows an error instead of an empty list", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({ error: "Não foi possível carregar os roteiros." }),
    );
    expect(getByTestId("roteiros-erro")).toBeTruthy();
    expect(queryByTestId("roteiros-empty")).toBeNull();
  });

  it("🔴 keeps roteiros mounted while `loading` is true AND they already exist", async () => {
    // The bug a screen recording caught, reproduced here: patching a visita's
    // outcome invalidates this SAME list, and a stale `loading=true` mid-
    // refetch must never unmount roteiros that are already on screen.
    const { getByTestId, queryByTestId } = await render(
      baseProps({ loading: true, roteiros: [roteiro()] }),
    );
    expect(getByTestId("roteiro-r1")).toBeTruthy();
    expect(queryByTestId("roteiros-loading")).toBeNull();
  });

  it("shows the subtle refreshing indicator beside the heading, not over the list", async () => {
    const { getByTestId } = await render(baseProps({ refreshing: true, roteiros: [roteiro()] }));
    expect(getByTestId("roteiros-refreshing")).toBeTruthy();
    expect(getByTestId("roteiro-r1")).toBeTruthy();
  });
});


// ── State matrix rows (NOTES §2) ───────────────────────────────────────────

describe("RoteirosSection — Rascunho (state matrix: salvo / salvando / erro / falta data share this card)", () => {
  it("shows the Rascunho chip, 'Continuar editando', and NO PDF control", async () => {
    const onEditarRascunho = vi.fn();
    const { getByTestId, queryByTestId, queryByText, fireEvent } = await renderWith(
      baseProps({ roteiros: [rascunho()], onEditarRascunho }),
    );
    expect(getByTestId("roteiro-status-r1").textContent).toBe("Rascunho");
    // 🔴 the PDF gate: no draft state has a PDF control
    expect(queryByTestId("roteiro-pdf-r1")).toBeNull();
    expect(queryByText("Baixar PDF")).toBeNull();
    expect(queryByText("Gerar Roteiro")).toBeNull();
    // Reabrir is a GERADO action
    expect(queryByTestId("roteiro-reabrir-r1")).toBeNull();
    fireEvent.click(getByTestId("roteiro-continuar-r1"));
    expect(onEditarRascunho).toHaveBeenCalledWith("r1");
  });

  it("offers no outcome controls and no list editing on a draft (the editor owns those)", async () => {
    const { queryByTestId, getByTestId } = await render(
      baseProps({ roteiros: [rascunho({ visitas: [visita("v1", "ONE9001")] })] }),
    );
    expect(queryByTestId("visita-status-realizada-v1")).toBeNull();
    expect(queryByTestId("visita-observacao-v1")).toBeNull();
    expect(getByTestId("rascunho-visita-v1").textContent).toContain("ONE9001");
  });

  it("a draft is never 'due' for 'a visita aconteceu?'", async () => {
    const { queryByTestId } = await render(
      baseProps({
        roteiros: [rascunho({ data_visita: "2020-01-01", feedback_status: "pendente" })],
        onResponderFeedback: vi.fn(),
      }),
    );
    expect(queryByTestId("visita-feedback-banner-r1")).toBeNull();
  });

  it("can be deleted (R4) from the list", async () => {
    const onRemover = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [rascunho()], onRemover }),
    );
    expect(getByTestId("roteiro-remover-r1").getAttribute("aria-label")).toBe("Excluir rascunho");
    fireEvent.click(getByTestId("roteiro-remover-r1"));
    expect(onRemover).toHaveBeenCalledWith("r1");
  });
});

describe("RoteirosSection — Gerado · com resultados (gestor)", () => {
  const comResultados = () =>
    roteiro({
      visitas: [
        visita("v1", "ONE9001", { status: "realizada", resultado_em: "2026-11-14T10:00:00+00:00" }),
        visita("v2", "ONE9002", {
          status: "cancelada",
          cancelada_por: "proprietario",
          cancelada_motivo: "imovel_indisponivel",
        }),
        visita("v3", "ONE9003", { status: "reagendada" }),
      ],
      permissoes: permissoesGerado({
        reabrir: false,
        motivo_reabrir: "Já tem 2 resultados registrados.",
      }),
    });

  it("shows Gerado, Baixar PDF, a locked list, and Reabrir DISABLED with the server's reason", async () => {
    const { getByTestId, queryByTestId, getByText } = await render(
      baseProps({ roteiros: [comResultados()] }),
    );
    expect(getByTestId("roteiro-status-r1").textContent).toBe("Gerado");
    expect(getByText("Baixar PDF")).toBeTruthy();
    const reabrir = getByTestId("roteiro-reabrir-r1") as HTMLButtonElement;
    expect(reabrir.disabled).toBe(true);
    // the reason is the SERVER's copy, wired as the button's description
    const motivo = getByTestId("roteiro-reabrir-motivo-r1");
    expect(motivo.textContent).toBe("Já tem 2 resultados registrados.");
    expect(reabrir.getAttribute("aria-describedby")).toBe(motivo.id);
    // locked: no add / remove / reorder controls anywhere
    expect(getByTestId("roteiro-travado-r1").textContent).toContain(
      "a lista de imóveis está travada",
    );
    expect(queryByTestId("roteiro-add-codigo-r1")).toBeNull();
    expect(queryByTestId("visita-remover-v1")).toBeNull();
    expect(queryByTestId("imovel-visita-handle-ONE9001")).toBeNull();
  });

  it("counts: realizada consolidated, cancelada lost, reagendada NEUTRAL ('não conta')", async () => {
    const { getByTestId } = await render(baseProps({ roteiros: [comResultados()] }));
    const texto = getByTestId("roteiro-contagem").textContent ?? "";
    expect(texto).toContain("1 realizadas");
    expect(texto).toContain("1 perdidas");
    expect(texto).toContain("1 reagendadas · não conta");
    expect(texto).toContain("0 pendentes");
  });

  it("renders from `permissoes`, not from the visitas: results present but server says reabrir=true → enabled", async () => {
    // The FE must not re-derive "no results ⇒ can reopen" — it obeys the flag.
    const r = comResultados();
    r.permissoes = permissoesGerado({ reabrir: true });
    const { getByTestId } = await render(baseProps({ roteiros: [r] }));
    expect((getByTestId("roteiro-reabrir-r1") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("RoteirosSection — Gerado · sem resultados (gestor)", () => {
  it("Reabrir is enabled and asks the caller to confirm", async () => {
    const onReabrir = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [roteiro()], onReabrir }),
    );
    const btn = getByTestId("roteiro-reabrir-r1") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    expect(onReabrir).toHaveBeenCalledWith("r1");
  });

  it("a user who may not reopen and has no reason to show sees no Reabrir at all", async () => {
    const r = roteiro({
      permissoes: permissoesGerado({ reabrir: false, motivo_reabrir: null }),
    });
    const { queryByTestId } = await render(baseProps({ roteiros: [r] }));
    expect(queryByTestId("roteiro-reabrir-r1")).toBeNull();
  });

  it("a member who may not reopen sees the disabled button with the server's role reason", async () => {
    const motivo = "Só supervisores, administradores e o proprietário da conta podem reabrir.";
    const r = roteiro({
      permissoes: permissoesGerado({ reabrir: false, motivo_reabrir: motivo }),
    });
    const { getByTestId } = await render(baseProps({ roteiros: [r] }));
    expect((getByTestId("roteiro-reabrir-r1") as HTMLButtonElement).disabled).toBe(true);
    expect(getByTestId("roteiro-reabrir-motivo-r1").textContent).toBe(motivo);
  });

  it("🔴 Baixar PDF is gated by `permissoes.baixar_pdf` alone", async () => {
    const onBaixarPdf = vi.fn();
    const sem = roteiro({ permissoes: permissoesGerado({ baixar_pdf: false }) });
    const a = await renderWith(baseProps({ roteiros: [sem] }));
    expect(a.queryByTestId("roteiro-pdf-r1")).toBeNull();
    a.unmount();

    const b = await renderWith(baseProps({ roteiros: [roteiro()], onBaixarPdf }));
    b.fireEvent.click(b.getByTestId("roteiro-pdf-r1"));
    expect(onBaixarPdf).toHaveBeenCalledWith("r1");
  });

  it("spins only the roteiro whose PDF is being downloaded", async () => {
    const dois = [roteiro(), roteiro({ id: "r2", visitas: [visita("v9", "ONE9009", { roteiro_id: "r2" })] })];
    const { getByTestId } = await render(baseProps({ roteiros: dois, pdfPendingId: "r1" }));
    expect((getByTestId("roteiro-pdf-r1") as HTMLButtonElement).disabled).toBe(true);
    expect((getByTestId("roteiro-pdf-r2") as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("RoteirosSection — Reaberto (back to Rascunho)", () => {
  it("the PDF control is absent again and the draft offers 'Continuar editando'", async () => {
    const reaberto = rascunho({
      reaberto_em: "2026-11-13T09:00:00+00:00",
      reaberto_por: "u-cindy",
      gerado_em: "2026-11-12T15:42:00+00:00",
    });
    const { queryByTestId, getByTestId } = await render(baseProps({ roteiros: [reaberto] }));
    expect(getByTestId("roteiro-status-r1").textContent).toBe("Rascunho");
    expect(queryByTestId("roteiro-pdf-r1")).toBeNull();
    expect(getByTestId("roteiro-continuar-r1")).toBeTruthy();
  });
});

describe("RoteirosSection — outcomes on a gerado roteiro", () => {
  it("offers exactly the five outcomes as a labelled pressed-group", async () => {
    const { getByTestId, getByRole } = await render(baseProps({ roteiros: [roteiro()] }));
    expect(getByRole("group", { name: "Resultado da visita a ONE9001" })).toBeTruthy();
    for (const o of ["pendente", "realizada", "cancelada", "nao_compareceu", "reagendada"]) {
      expect(getByTestId(`visita-status-${o}-v1`)).toBeTruthy();
    }
    expect(getByTestId("visita-status-pendente-v1").getAttribute("aria-pressed")).toBe("true");
  });

  it("records Realizada / Não compareceu / Pendente with the visita id", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [roteiro()], onPatchVisita }),
    );
    fireEvent.click(getByTestId("visita-status-realizada-v1"));
    expect(onPatchVisita).toHaveBeenLastCalledWith("r1", "v1", { status: "realizada" });
    fireEvent.click(getByTestId("visita-status-nao_compareceu-v1"));
    expect(onPatchVisita).toHaveBeenLastCalledWith("r1", "v1", { status: "nao_compareceu" });
    fireEvent.click(getByTestId("visita-status-pendente-v1"));
    expect(onPatchVisita).toHaveBeenLastCalledWith("r1", "v1", { status: "pendente" });
  });

  it("🔴 Cancelada asks for motivo AND quem cancelou, and sends nothing until both are set", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId, fireEvent, getByText } = await renderWith(
      baseProps({ roteiros: [roteiro()], onPatchVisita }),
    );
    fireEvent.click(getByTestId("visita-status-cancelada-v1"));
    expect(onPatchVisita).not.toHaveBeenCalled();
    expect(getByText(/Informe o motivo e quem cancelou/)).toBeTruthy();

    fireEvent.change(getByTestId("visita-motivo-v1"), { target: { value: "imovel_indisponivel" } });
    expect(onPatchVisita).not.toHaveBeenCalled();

    fireEvent.change(getByTestId("visita-cancelada-por-v1"), { target: { value: "proprietario" } });
    expect(onPatchVisita).toHaveBeenCalledTimes(1);
    expect(onPatchVisita).toHaveBeenCalledWith("r1", "v1", {
      status: "cancelada",
      cancelada_motivo: "imovel_indisponivel",
      cancelada_por: "proprietario",
    });
  });

  it("an already-cancelada visita shows its motivo and who cancelled", async () => {
    const { getByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE9001", {
                status: "cancelada",
                cancelada_por: "cliente",
                cancelada_motivo: "cliente_desistiu",
              }),
            ],
          }),
        ],
      }),
    );
    expect((getByTestId("visita-motivo-v1") as HTMLSelectElement).value).toBe("cliente_desistiu");
    expect((getByTestId("visita-cancelada-por-v1") as HTMLSelectElement).value).toBe("cliente");
  });

  it("🔴 Reagendada is NEUTRAL and never PATCHed (R11 refuses it): it offers 'Criar novo roteiro com ONExxxx' (R12)", async () => {
    const onPatchVisita = vi.fn();
    const onReagendar = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({
        roteiros: [roteiro({ visitas: [visita("v1", "ONE10702")] })],
        onPatchVisita,
        onReagendar,
      }),
    );
    fireEvent.click(getByTestId("visita-status-reagendada-v1"));
    expect(onPatchVisita).not.toHaveBeenCalled();
    expect(getByTestId("visita-reagendada-v1").textContent).toContain(
      "Reagendada não conta como perdida.",
    );
    const criar = getByTestId("visita-reagendar-v1");
    expect(criar.textContent).toContain("Criar novo roteiro com ONE10702");
    fireEvent.click(criar);
    expect(onReagendar).toHaveBeenCalledWith("r1", "v1");
  });

  it("an already-reagendada visita links to the roteiro that replaced it", async () => {
    const onEditarRascunho = vi.fn();
    const antigo = roteiro({
      visitas: [visita("v1", "ONE10702", { status: "reagendada", reagendada_para_visita_id: "vn" })],
    });
    const novo = rascunho({
      id: "r2",
      visitas: [visita("vn", "ONE10702", { roteiro_id: "r2" })],
    });
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [novo, antigo], onEditarRascunho }),
    );
    fireEvent.click(getByTestId("visita-abrir-novo-v1"));
    expect(onEditarRascunho).toHaveBeenCalledWith("r2");
  });

  it("saves the observação on blur (any status), not on every keystroke", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [roteiro()], onPatchVisita }),
    );
    const campo = getByTestId("visita-observacao-v1");
    fireEvent.change(campo, { target: { value: "não atendeu" } });
    expect(onPatchVisita).not.toHaveBeenCalled();
    fireEvent.blur(campo);
    expect(onPatchVisita).toHaveBeenCalledWith("r1", "v1", { observacao: "não atendeu" });
  });

  it("does not PATCH an unchanged observação", async () => {
    const onPatchVisita = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({
        roteiros: [roteiro({ visitas: [visita("v1", "ONE9001", { observacao: "já escrito" })] })],
        onPatchVisita,
      }),
    );
    fireEvent.blur(getByTestId("visita-observacao-v1"));
    expect(onPatchVisita).not.toHaveBeenCalled();
  });
});

describe("RoteirosSection — date and time stay editable on a gerado roteiro", () => {
  it("patches the date on blur and never sends a cleared date", async () => {
    const onPatchRoteiro = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [roteiro()], onPatchRoteiro }),
    );
    const data = getByTestId("roteiro-data-r1") as HTMLInputElement;
    fireEvent.change(data, { target: { value: "2026-11-20" } });
    fireEvent.blur(data);
    expect(onPatchRoteiro).toHaveBeenCalledWith("r1", { data_visita: "2026-11-20" });

    onPatchRoteiro.mockClear();
    fireEvent.change(data, { target: { value: "" } });
    fireEvent.blur(data);
    expect(onPatchRoteiro).not.toHaveBeenCalled(); // R3 would 422 a null on a gerado
  });

  it("patches the time (HH:MM) and may clear it", async () => {
    const onPatchRoteiro = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [roteiro({ hora_visita: "10:00" })], onPatchRoteiro }),
    );
    const hora = getByTestId("roteiro-hora-r1") as HTMLInputElement;
    expect(hora.value).toBe("10:00");
    fireEvent.change(hora, { target: { value: "11:15" } });
    fireEvent.blur(hora);
    expect(onPatchRoteiro).toHaveBeenLastCalledWith("r1", { hora_visita: "11:15" });
    fireEvent.change(hora, { target: { value: "" } });
    fireEvent.blur(hora);
    expect(onPatchRoteiro).toHaveBeenLastCalledWith("r1", { hora_visita: null });
  });
});

describe("RoteirosSection — a delisted imóvel", () => {
  it("says so, and still renders what the registry snapshot holds", async () => {
    // `imovel` is never null (the FK guarantees a registry row), but a sold
    // property carries no street — the badge is what explains the blanks.
    const { getByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE4770", {
                imovel: imovel("ONE4770", {
                  ativo_no_vista: false,
                  fonte: "registry",
                  empreendimento: null,
                  logradouro: null,
                  numero: null,
                  corretores: [],
                }),
              }),
            ],
          }),
        ],
      }),
    );
    expect(getByTestId("imovel-fora-do-catalogo")).toBeTruthy();
    expect(getByTestId("imovel-visita-ONE4770").textContent).toContain("Centro");
  });
});

describe("RoteirosSection — owner data (D1)", () => {
  it("renders the labels with an em-dash rather than hiding them", async () => {
    // User-ratified 2026-08-25: Vista exposes no proprietário, so the slot
    // ships empty. The LABEL still prints.
    const { getByTestId } = await render(baseProps({ roteiros: [roteiro()] }));
    const texto = getByTestId("imovel-proprietario").textContent ?? "";
    expect(texto).toContain("Proprietário");
    expect(texto).toContain("Celular");
    expect(texto).toContain("—");
  });
});

/**
 * 🔴 THE PROPOSTA AXIS (migration 104) — orthogonal to `status`, and visible.
 * Recording a proposta never touches the did-it-happen fact the contabilização
 * is built on, and the accepted visita is unmistakable among several.
 */
describe("RoteirosSection — visita → proposta → o imóvel do negócio", () => {
  it("makes the accepted visita unmistakable among several", async () => {
    const { getByTestId, getAllByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE9001"),
              visita("v2", "ONE9002", {
                proposta_em: "2026-09-01T00:00:00+00:00",
                proposta_aceita_em: "2026-09-02T00:00:00+00:00",
              }),
              visita("v3", "ONE9003"),
            ],
          }),
        ],
      }),
    );
    expect(getAllByTestId("imovel-proposta-aceita")).toHaveLength(1);
    expect(getByTestId("roteiro-contagem").textContent).toContain("proposta aceita: ONE9002");
  });

  it("distinguishes an offer that was made from one that was accepted", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [visita("v1", "ONE9001", { proposta_em: "2026-09-01T00:00:00+00:00" })],
          }),
        ],
      }),
    );
    expect(getByTestId("imovel-proposta-feita")).toBeTruthy();
    expect(queryByTestId("imovel-proposta-aceita")).toBeNull();
    expect(getByTestId("roteiro-contagem").textContent).not.toContain("proposta aceita");
  });

  it("leaves the contabilização alone — a proposta is not a status", async () => {
    const { getByTestId } = await render(
      baseProps({
        roteiros: [
          roteiro({
            visitas: [
              visita("v1", "ONE9001", {
                status: "realizada",
                proposta_em: "2026-09-01T00:00:00+00:00",
                proposta_aceita_em: "2026-09-02T00:00:00+00:00",
              }),
            ],
          }),
        ],
      }),
    );
    expect(getByTestId("roteiro-contagem").textContent).toContain("1 realizadas");
    expect(getByTestId("visita-status-realizada-v1").getAttribute("aria-pressed")).toBe("true");
  });
});

describe("RoteirosSection — a visita aconteceu? (sw-lead-to-contract §3, R14)", () => {
  const pendente = () =>
    roteiro({
      data_visita: "2020-01-01",
      feedback_status: "pendente",
      visitas: [visita("v1", "ONE9001"), visita("v2", "ONE9002")],
    });

  it("shows the banner only while the GERADO roteiro is due and a handler exists", async () => {
    const React = (await import("react")).default;
    const rtl = await import("@testing-library/react");
    const r = rtl.render(
      React.createElement(
        RoteirosSection,
        baseProps({ roteiros: [pendente()], onResponderFeedback: vi.fn() }),
      ),
    );
    expect(r.getByTestId("visita-feedback-banner-r1")).toBeTruthy();
    const re = (p: RoteirosSectionProps) => r.rerender(React.createElement(RoteirosSection, p));
    re(baseProps({ roteiros: [roteiro({ data_visita: "2999-01-01" })], onResponderFeedback: vi.fn() }));
    expect(r.queryByTestId("visita-feedback-banner-r1")).toBeNull();
    re(baseProps({ roteiros: [roteiro({ data_visita: "2020-01-01", feedback_status: "respondido" })], onResponderFeedback: vi.fn() }));
    expect(r.queryByTestId("visita-feedback-banner-r1")).toBeNull();
  });

  it("answering 'não' sends every visita with ONE resultado (default cancelada needs motivo + quem)", async () => {
    const onResponderFeedback = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [pendente()], onResponderFeedback }),
    );
    fireEvent.click(getByTestId("visita-feedback-abrir-r1"));
    fireEvent.click(getByTestId("visita-feedback-nao"));
    // cancelada is the default and is incomplete: the submit is blocked, not a 422
    expect((getByTestId("visita-feedback-enviar") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(getByTestId("visita-feedback-geral-motivo"), { target: { value: "outro" } });
    fireEvent.change(getByTestId("visita-feedback-geral-por"), { target: { value: "cliente" } });
    fireEvent.click(getByTestId("visita-feedback-enviar"));
    expect(onResponderFeedback).toHaveBeenCalledWith("r1", {
      aconteceu: false,
      visitas: [
        {
          visita_id: "v1",
          realizada: false,
          resultado: "cancelada",
          cancelada_por: "cliente",
          cancelada_motivo: "outro",
          observacao: null,
        },
        {
          visita_id: "v2",
          realizada: false,
          resultado: "cancelada",
          cancelada_por: "cliente",
          cancelada_motivo: "outro",
          observacao: null,
        },
      ],
    });
  });

  it("'não aconteceu' as Reagendada needs no motivo and sends the neutral resultado", async () => {
    const onResponderFeedback = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [pendente()], onResponderFeedback }),
    );
    fireEvent.click(getByTestId("visita-feedback-abrir-r1"));
    fireEvent.click(getByTestId("visita-feedback-nao"));
    fireEvent.change(getByTestId("visita-feedback-geral-resultado"), { target: { value: "reagendada" } });
    fireEvent.click(getByTestId("visita-feedback-enviar"));
    const body = onResponderFeedback.mock.calls[0][1];
    expect(
      body.visitas.map((v: { resultado: string; realizada: boolean }) => [v.resultado, v.realizada]),
    ).toEqual([
      ["reagendada", false],
      ["reagendada", false],
    ]);
  });

  it("answering 'sim' lists every visita; a cancelada one blocks the submit until motivo + quem are set", async () => {
    const onResponderFeedback = vi.fn();
    const { getByTestId, fireEvent } = await renderWith(
      baseProps({ roteiros: [pendente()], onResponderFeedback }),
    );
    fireEvent.click(getByTestId("visita-feedback-abrir-r1"));
    fireEvent.click(getByTestId("visita-feedback-sim"));
    fireEvent.change(getByTestId("visita-feedback-v2-resultado"), { target: { value: "cancelada" } });
    expect((getByTestId("visita-feedback-enviar") as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(getByTestId("visita-feedback-v2-motivo"), { target: { value: "imovel_indisponivel" } });
    fireEvent.change(getByTestId("visita-feedback-v2-por"), { target: { value: "proprietario" } });
    fireEvent.click(getByTestId("visita-feedback-enviar"));
    expect(onResponderFeedback).toHaveBeenCalledWith("r1", {
      aconteceu: true,
      visitas: [
        { visita_id: "v1", realizada: true, resultado: "realizada", observacao: null },
        {
          visita_id: "v2",
          realizada: false,
          resultado: "cancelada",
          cancelada_por: "proprietario",
          cancelada_motivo: "imovel_indisponivel",
          observacao: null,
        },
      ],
    });
  });

  it("mounts the visited-list slot only on an answered GERADO roteiro", async () => {
    const renderVisitadas = vi.fn(() => <div data-testid="slot-visitadas" />);
    const React = (await import("react")).default;
    const rtl = await import("@testing-library/react");
    const r = rtl.render(
      React.createElement(RoteirosSection, baseProps({ roteiros: [pendente()], renderVisitadas })),
    );
    expect(r.queryByTestId("slot-visitadas")).toBeNull();
    r.rerender(
      React.createElement(
        RoteirosSection,
        baseProps({ roteiros: [roteiro({ feedback_status: "respondido" })], renderVisitadas }),
      ),
    );
    expect(r.queryByTestId("slot-visitadas")).toBeTruthy();
  });
});
