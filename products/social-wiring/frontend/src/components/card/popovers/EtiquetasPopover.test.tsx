/**
 * EtiquetasPopover.test.tsx — screenshot 05. The mandatory, non-optional
 * bit per the brief: "modo compatível para usuários com daltonismo" must
 * exist and be wired, plus the basic search/toggle/create affordances.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

import { EtiquetasPopover } from "./EtiquetasPopover";

const TAGS = [
  { id: "t1", nome: "Claude", cor: "#d29034" },
  { id: "t2", nome: "Urgente", cor: "#eb5a46" },
];

async function render(props: Partial<React.ComponentProps<typeof EtiquetasPopover>> = {}) {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const merged: React.ComponentProps<typeof EtiquetasPopover> = {
    open: true,
    onOpenChange: vi.fn(),
    allTags: TAGS,
    selectedTagIds: [],
    onToggleTag: vi.fn(),
    onCreateTag: vi.fn(),
    onEditTag: vi.fn(),
    colorBlindMode: false,
    onToggleColorBlindMode: vi.fn(),
    ...props,
  };
  return { ...rtl.render(React.createElement(EtiquetasPopover, merged)), props: merged };
}

describe("EtiquetasPopover — colour-blind toggle (mandatory, in the shot)", () => {
  it("renders the exact pt-BR label from the screenshot", async () => {
    const { getByText } = await render();
    expect(getByText("Habilitar o modo compatível para usuários com daltonismo")).toBeTruthy();
  });

  it("fires onToggleColorBlindMode when flipped", async () => {
    const onToggleColorBlindMode = vi.fn();
    const { getByTestId } = await render({ onToggleColorBlindMode });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("etiquetas-daltonismo-switch"));
    expect(onToggleColorBlindMode).toHaveBeenCalledWith(true);
  });

  it("shows a non-colour indicator on a checked tag when colour-blind mode is on", async () => {
    const { getByTestId } = await render({ selectedTagIds: ["t1"], colorBlindMode: true });
    expect(getByTestId("etiqueta-colorblind-check-t1")).toBeTruthy();
  });

  it("shows no non-colour indicator when colour-blind mode is off", async () => {
    const { queryByTestId } = await render({ selectedTagIds: ["t1"], colorBlindMode: false });
    expect(queryByTestId("etiqueta-colorblind-check-t1")).toBeNull();
  });
});

describe("EtiquetasPopover — search and toggle", () => {
  it("filters the list by the search box", async () => {
    const { getByTestId, queryByText, getByText } = await render();
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(getByTestId("etiquetas-search"), { target: { value: "urg" } });
    expect(getByText("Urgente")).toBeTruthy();
    expect(queryByText("Claude")).toBeNull();
  });

  it("fires onToggleTag with the tag id when a swatch is clicked", async () => {
    const onToggleTag = vi.fn();
    const { getByTestId } = await render({ onToggleTag });
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(getByTestId("etiqueta-swatch-t2"));
    expect(onToggleTag).toHaveBeenCalledWith("t2");
  });
});

describe("EtiquetasPopover — create a new tag", () => {
  it("reveals the create form and submits name+colour", async () => {
    const onCreateTag = vi.fn();
    const { getByTestId } = await render({ onCreateTag });
    const { fireEvent } = await import("@testing-library/react");

    fireEvent.click(getByTestId("etiquetas-criar-btn"));
    fireEvent.change(getByTestId("etiquetas-nova-nome"), { target: { value: "Follow-up" } });
    fireEvent.click(getByTestId("etiquetas-nova-salvar"));

    expect(onCreateTag).toHaveBeenCalledWith("Follow-up", expect.any(String));
  });
});
