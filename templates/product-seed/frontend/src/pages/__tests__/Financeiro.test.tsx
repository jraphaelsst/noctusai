import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockAdmin = vi.fn();
vi.mock("@/lib/api", () => ({ api: { marker: "api" } }));
vi.mock("@noctusai/lib/design-system", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@noctusai/lib/design-system")>()),
  useIsOrgAdmin: () => mockAdmin(),
}));
vi.mock("@noctusai/lib", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@noctusai/lib")>()),
  createFinanceHooks: (api: unknown) => ({ api }),
  FinanceShell: ({
    isAdmin,
    section,
    onSectionChange,
  }: {
    isAdmin: boolean;
    section: string;
    onSectionChange: (key: string) => void;
  }) => (
    <div>
      <span data-testid="section">{section}</span>
      <span data-testid="admin">{String(isAdmin)}</span>
      <button onClick={() => onSectionChange("payable")}>go-payable</button>
      <button onClick={() => onSectionChange("overview")}>go-overview</button>
    </div>
  ),
}));

import Financeiro from "../Financeiro";

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/financeiro/*" element={<><Financeiro /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("Financeiro route", () => {
  it("maps the URL segment to the shell section and passes the admin gate", () => {
    mockAdmin.mockReturnValue(true);
    renderAt("/financeiro/receber");
    expect(screen.getByTestId("section").textContent).toBe("receivable");
    expect(screen.getByTestId("admin").textContent).toBe("true");
  });

  it("the bare route is the overview; a non-admin gets isAdmin=false", () => {
    mockAdmin.mockReturnValue(false);
    renderAt("/financeiro");
    expect(screen.getByTestId("section").textContent).toBe("overview");
    expect(screen.getByTestId("admin").textContent).toBe("false");
  });

  it("section changes write the URL back (and the overview returns to /financeiro)", () => {
    mockAdmin.mockReturnValue(true);
    renderAt("/financeiro/dre");
    fireEvent.click(screen.getByText("go-payable"));
    expect(screen.getByTestId("where").textContent).toBe("/financeiro/pagar");
    expect(screen.getByTestId("section").textContent).toBe("payable");
    fireEvent.click(screen.getByText("go-overview"));
    expect(screen.getByTestId("where").textContent).toBe("/financeiro");
  });
});
