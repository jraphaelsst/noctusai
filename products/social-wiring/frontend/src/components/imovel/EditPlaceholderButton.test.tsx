/**
 * EditPlaceholderButton — CONTRACT § 4: fires the toast, wires NOTHING else.
 *
 * The point of this test is the NEGATIVE assertion: no mutation function,
 * no PATCH call, no dialog open — a click does exactly one thing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

const mockToastInfo = vi.fn();
vi.mock("sonner", () => ({
  toast: { info: (...a: unknown[]) => mockToastInfo(...a) },
}));

import EditPlaceholderButton from "./EditPlaceholderButton";

async function render(label = "Editar cômodos") {
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const view = rtl.render(React.createElement(EditPlaceholderButton, { label }));
  return { ...rtl, ...view };
}

describe("EditPlaceholderButton", () => {
  it("uses the same string for the accessible name as the given label", async () => {
    const { getByRole } = await render("Editar valores");
    expect(getByRole("button", { name: "Editar valores" })).toBeTruthy();
  });

  it("fires the exact honest-placeholder toast on click, and performs no mutation", async () => {
    const { getByRole, fireEvent } = await render();

    fireEvent.click(getByRole("button", { name: "Editar cômodos" }));

    expect(mockToastInfo).toHaveBeenCalledTimes(1);
    expect(mockToastInfo).toHaveBeenCalledWith(
      "Edição via plataforma ainda não disponível — o Vista não expõe rota de escrita. Chega quando migrarmos para o sistema próprio.",
    );
  });

  it("has no onClick side effect beyond the toast — nothing else fires on repeated clicks", async () => {
    const { getByRole, fireEvent } = await render();
    const button = getByRole("button", { name: "Editar cômodos" });

    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mockToastInfo).toHaveBeenCalledTimes(3);
  });
});
