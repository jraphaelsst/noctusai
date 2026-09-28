/**
 * `<StageRolePanel/>` — board-agnostic "Papéis das etapas" control (comercial
 * achado #14): one dropdown per role, pre-selected to whichever stage
 * currently holds it, calling `onAssign(etapaId, papel)` on a new pick.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { StageRolePanel } from "../StageRolePanel";

const STAGES = [
  { id: "s1", label: "Leads", papel: null },
  { id: "s2", label: "Negociação", papel: null },
  { id: "s3", label: "Fechado", papel: "fechado" },
];

afterEach(cleanup);

describe("StageRolePanel", () => {
  it("is collapsed by default; expanding shows one select per role, pre-selected to its current holder", () => {
    render(<StageRolePanel roleLabels={{ fechado: "Fechado (exige orçamento aceito)" }} stages={STAGES} onAssign={vi.fn()} />);
    expect(screen.queryByLabelText("Etapa com o papel Fechado (exige orçamento aceito)")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Papéis das etapas/ }));
    const select = screen.getByLabelText("Etapa com o papel Fechado (exige orçamento aceito)") as HTMLSelectElement;
    expect(select.value).toBe("s3");
  });

  it("calls onAssign with the new stage id and the role slug on a pick", () => {
    const onAssign = vi.fn();
    render(<StageRolePanel roleLabels={{ fechado: "Fechado" }} stages={STAGES} onAssign={onAssign} />);
    fireEvent.click(screen.getByRole("button", { name: /Papéis das etapas/ }));
    fireEvent.change(screen.getByLabelText("Etapa com o papel Fechado"), { target: { value: "s2" } });
    expect(onAssign).toHaveBeenCalledWith("s2", "fechado");
  });

  it("disables every select while a reassignment is pending", () => {
    render(<StageRolePanel roleLabels={{ fechado: "Fechado" }} stages={STAGES} onAssign={vi.fn()} isPending />);
    fireEvent.click(screen.getByRole("button", { name: /Papéis das etapas/ }));
    expect(screen.getByLabelText("Etapa com o papel Fechado")).toBeDisabled();
  });
});
