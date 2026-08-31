/**
 * DocumentoChecklistSection — the mandatory "Dados obrigatórios" list.
 *
 * 🔴 THE LOAD-BEARING TEST is "keeps every row mounted during a background
 * refetch": a screen recording caught all 8 rows vanishing behind a single
 * skeleton bar on every unrelated card edit (clearing the Email field, for
 * instance) because the caller correctly gated `loading` on
 * `isPending || isFetching` (never `isLoading` — v5's is false during a
 * background refetch) but this component then treated that ONE boolean as
 * "hide everything". A mocked query object that never transitions through a
 * background refetch — `loading` always paired with an empty `items` array —
 * is exactly why that shape was invisible to any existing suite; this file's
 * first describe block simulates the transition explicitly.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import {
  DocumentoChecklistSection,
  type DocumentoChecklistSectionProps,
} from "./DocumentoChecklistSection";
import type { DocumentoChecklistItem } from "@/types/cardHub";

/** A derived, unticked checklist item — the ordinary shape. */
function item(key: string, label: string, over: Partial<DocumentoChecklistItem> = {}): DocumentoChecklistItem {
  return {
    key,
    label,
    concluido: false,
    origem: "derivado",
    derivado: false,
    sugestao: null,
    concluido_em: null,
    concluido_por: null,
    ...over,
  };
}

const ITENS: DocumentoChecklistItem[] = [
  item("rg", "RG"),
  item("cpf", "CPF"),
  item("email", "E-mail", { concluido: true, derivado: true }),
];

function baseProps(over: Partial<DocumentoChecklistSectionProps> = {}): DocumentoChecklistSectionProps {
  return {
    items: [],
    onToggle: vi.fn(),
    ...over,
  };
}

async function renderSection(props: DocumentoChecklistSectionProps) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  return rtl.render(React.createElement(DocumentoChecklistSection, props));
}

describe("DocumentoChecklistSection — background refetch never unmounts rows", () => {
  it("🔴 keeps every row mounted while `loading` is true AND `items` already has data", async () => {
    // This is exactly what the OLD caller sent mid-refetch: `documentoChecklist
    // .isPending || documentoChecklist.isFetching` stays true through the
    // whole background fetch even though `documentoChecklist.data.items` is
    // still the last-good array. Before the fix this rendered ONLY the
    // skeleton bar, dropping all 8 (here 3) rows.
    const { getByTestId, queryByTestId } = await renderSection(
      baseProps({ items: ITENS, loading: true }),
    );
    expect(getByTestId(`documento-checklist-section`)).toBeTruthy();
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-cpf-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-email-row")).toBeTruthy();
    expect(queryByTestId("documento-checklist-loading")).toBeNull();
  });

  it("shows the skeleton only when there is genuinely nothing to render yet", async () => {
    const { getByTestId, queryByTestId } = await renderSection(
      baseProps({ items: [], loading: true }),
    );
    expect(getByTestId("documento-checklist-loading")).toBeTruthy();
    expect(queryByTestId("documento-checklist-section")).toBeNull();
  });

  it("never renders the empty state over rows that exist mid-refetch", async () => {
    // The `lying-loading-state` class this whole file guards against: an
    // empty/skeleton branch must never outrank live data.
    const { queryByTestId, getByTestId } = await renderSection(
      baseProps({ items: ITENS, loading: true }),
    );
    expect(queryByTestId("documento-checklist-loading")).toBeNull();
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
  });

  it("shows the subtle refreshing indicator beside the count, not over the rows", async () => {
    const { getByTestId } = await renderSection(
      baseProps({ items: ITENS, refreshing: true }),
    );
    expect(getByTestId("documento-checklist-refreshing")).toBeTruthy();
    // The count itself stays an exact match — the indicator lives beside it,
    // never inside the text a test (or an operator's eye) reads as the tally.
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
  });

  it("does not show the refreshing indicator when nothing is in flight", async () => {
    const { queryByTestId } = await renderSection(baseProps({ items: ITENS }));
    expect(queryByTestId("documento-checklist-refreshing")).toBeNull();
  });
});

describe("DocumentoChecklistSection — progress + rows", () => {
  it("renders one row per item and counts completion", async () => {
    const { getByTestId } = await renderSection(baseProps({ items: ITENS }));
    expect(getByTestId("documento-checklist-progresso").textContent).toBe("1/3");
    expect(getByTestId("documento-checklist-rg-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-cpf-row")).toBeTruthy();
    expect(getByTestId("documento-checklist-email-row")).toBeTruthy();
  });

  it("says so when the server sends an empty list (not loading)", async () => {
    const { getByTestId } = await renderSection(baseProps({ items: [] }));
    expect(getByTestId("documento-checklist-empty")).toBeTruthy();
  });
});
