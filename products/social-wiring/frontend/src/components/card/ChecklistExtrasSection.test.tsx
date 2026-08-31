/**
 * ChecklistExtrasSection — the rows the OPERATOR creates.
 *
 * 🔴 THE LOAD-BEARING TEST is "keeps every extra row mounted during a
 * background refetch" — same class of bug as `DocumentoChecklistSection`
 * (see its docblock): renaming, saving text, or uploading a file on ONE row
 * invalidates this whole list, and the section used to treat the caller's
 * `isPending || isFetching` as "replace everything with a skeleton bar".
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import {
  ChecklistExtrasSection,
  type ChecklistExtrasSectionProps,
} from "./ChecklistExtrasSection";
import type { ChecklistExtra } from "@/types/cardHub";

function extra(id: string, over: Partial<ChecklistExtra> = {}): ChecklistExtra {
  return {
    id,
    label: `Comprovante ${id}`,
    tipo: "texto",
    valor_texto: "Aprovado",
    documento: null,
    concluido: true,
    ordem: 0,
    ...over,
  };
}

function baseProps(over: Partial<ChecklistExtrasSectionProps> = {}): ChecklistExtrasSectionProps {
  return {
    items: [],
    onCriar: vi.fn(),
    onRenomear: vi.fn(),
    onSalvarTexto: vi.fn(),
    onRemover: vi.fn(),
    onUploadDocumento: vi.fn(),
    onRemoverDocumento: vi.fn(),
    ...over,
  };
}

async function render(props: ChecklistExtrasSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(ChecklistExtrasSection, props));
}

describe("ChecklistExtrasSection — background refetch never unmounts rows", () => {
  it("🔴 keeps every row mounted while `loading` is true AND rows already exist", async () => {
    const { getByTestId, queryByTestId } = await render(
      baseProps({ items: [extra("e1"), extra("e2")], loading: true }),
    );
    expect(getByTestId("checklist-extras-e1-row")).toBeTruthy();
    expect(getByTestId("checklist-extras-e2-row")).toBeTruthy();
    expect(queryByTestId("checklist-extras-empty")).toBeNull();
  });

  it("shows the skeleton only when there is genuinely nothing to render yet", async () => {
    const { getByTestId, queryByTestId } = await render(baseProps({ items: [], loading: true }));
    expect(getByTestId("checklist-extras-loading")).toBeTruthy();
    expect(queryByTestId("checklist-extras-lista")).toBeNull();
  });

  it("shows the subtle refreshing indicator beside the heading, not over the rows", async () => {
    const { getByTestId } = await render(baseProps({ items: [extra("e1")], refreshing: true }));
    expect(getByTestId("checklist-extras-refreshing")).toBeTruthy();
    expect(getByTestId("checklist-extras-e1-row")).toBeTruthy();
  });

  it("says so when the server sends an empty list (not loading)", async () => {
    const { getByTestId } = await render(baseProps({ items: [] }));
    expect(getByTestId("checklist-extras-empty")).toBeTruthy();
  });
});
