/**
 * ClienteCardFace.test.tsx — screenshot 11's rule: badges render ONLY when
 * non-zero, and the due pill's state colouring (done/overdue/soon/upcoming).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { ClienteCardFace, resolveDueState } from "./ClienteCardFace";

async function render(props: React.ComponentProps<typeof ClienteCardFace>) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(ClienteCardFace, props));
}

describe("resolveDueState", () => {
  const now = new Date("2026-08-18T12:00:00Z");

  it("is done when entrega_concluida, regardless of date", () => {
    expect(resolveDueState("2020-01-01T00:00:00Z", true, now)).toBe("done");
  });

  it("is overdue when the due date is in the past and not complete", () => {
    expect(resolveDueState("2026-08-01T00:00:00Z", false, now)).toBe("overdue");
  });

  it("is soon when due within the next 24h", () => {
    expect(resolveDueState("2026-08-19T00:00:00Z", false, now)).toBe("soon");
  });

  it("is upcoming when due further out", () => {
    expect(resolveDueState("2026-09-01T00:00:00Z", false, now)).toBe("upcoming");
  });
});

describe("ClienteCardFace — badges render only when non-zero", () => {
  it("renders no badge row at all when every badge is falsy/zero", async () => {
    const { queryByTestId } = await render({ nome: "Maria Silva", badges: null, datas: null });
    expect(queryByTestId("cliente-card-face-badges")).toBeNull();
    expect(queryByTestId("cliente-card-face-strip")).toBeNull();
  });

  it("omits the anexos badge when documentos is 0", async () => {
    const { queryByTestId } = await render({
      nome: "Maria Silva",
      badges: {
        notas: 0,
        documentos: 0,
        touches: 0,
        checklist_total: 0,
        checklist_concluidos: 0,
        tem_descricao: false,
        temperatura: null,
      },
    });
    expect(queryByTestId("cliente-card-face-anexos")).toBeNull();
    expect(queryByTestId("cliente-card-face-badges")).toBeNull();
  });

  it("shows the anexos count when non-zero", async () => {
    const { getByTestId } = await render({
      nome: "Maria Silva",
      badges: {
        notas: 0,
        documentos: 3,
        touches: 0,
        checklist_total: 0,
        checklist_concluidos: 0,
        tem_descricao: false,
        temperatura: null,
      },
    });
    expect(getByTestId("cliente-card-face-anexos").textContent).toContain("3");
  });

  it("shows the checklist progress when checklist_total is non-zero, including a genuine 0/N", async () => {
    const { getByTestId } = await render({
      nome: "Maria Silva",
      badges: {
        notas: 0,
        documentos: 0,
        touches: 0,
        checklist_total: 6,
        checklist_concluidos: 0,
        tem_descricao: false,
        temperatura: null,
      },
    });
    expect(getByTestId("cliente-card-face-checklist").textContent).toContain("0/6");
  });

  it("renders the colour strip only when a colour is given", async () => {
    const { getByTestId } = await render({ nome: "Maria Silva", corFaixa: "#eb5a46" });
    expect(getByTestId("cliente-card-face-strip")).toBeTruthy();
  });

  it("fires onClick when clicked", async () => {
    const onClick = vi.fn();
    const { getByTestId } = await render({ nome: "Maria Silva", onClick });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("cliente-card-face"));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
