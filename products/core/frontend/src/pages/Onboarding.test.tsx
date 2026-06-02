/**
 * Onboarding org-type conditional field tests.
 *
 * Covers:
 *  - org-type picker renders "Individual" and "Empresa" options
 *  - "Numero de funcionarios" field is hidden when org_type = 'individual' (default)
 *  - "Numero de funcionarios" field is visible when org_type = 'company' is selected
 *  - Switching back to 'individual' hides the field again and resets to 1
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Onboarding } from "./Onboarding";

afterEach(() => cleanup());

// ---------------------------------------------------------------------------
// Minimal mocks — just enough for the component to render the company_details
// step without hitting real APIs.
// vi.mock factories are hoisted, so all values must be inlined (no top-level
// variables accessible inside factory scope).
// ---------------------------------------------------------------------------

vi.mock("../lib/auth-context", () => ({
  useAuth: () => ({ user: { id: "u1" }, organization: { id: "org-test" } }),
}));

vi.mock("../lib/api", () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url === "/api/onboarding/status") {
        return Promise.resolve({
          data: {
            org_id: "org-test",
            org_nome: "Test Corp",
            onboarding_completed: false,
            steps: {
              company_details: false,
              choose_plan: false,
              invite_team: false,
              enable_product: false,
            },
            progress: { completed: 0, total: 4, percentage: 0 },
          },
        });
      }
      if (url === "/api/plans") return Promise.resolve({ data: [] });
      if (url === "/api/auth/me") return Promise.resolve({ products: [] });
      return Promise.resolve({ data: null });
    }),
    patch: vi.fn().mockResolvedValue({
      data: {
        step: "company_details",
        onboarding_completed: false,
        steps: {
          company_details: false,
          choose_plan: false,
          invite_team: false,
          enable_product: false,
        },
        progress: { completed: 0, total: 4, percentage: 0 },
      },
    }),
  },
}));

vi.mock("../lib/product-icon", () => ({
  ProductIcon: () => null,
}));

// react-router-dom useNavigate mock
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderOnboarding() {
  return render(
    <MemoryRouter>
      <Onboarding />
    </MemoryRouter>
  );
}

// Wait for the async fetchStatus to resolve
async function waitForStep() {
  // The component sets loading=false after fetchStatus resolves
  await vi.waitFor(() => {
    expect(screen.queryByText("Carregando onboarding...")).toBeNull();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Onboarding org-type UX", () => {
  it("renders org-type options: Individual and Empresa", async () => {
    renderOnboarding();
    await waitForStep();

    // Both choices must be present
    expect(screen.getByTestId("org-type-individual")).toBeTruthy();
    expect(screen.getByTestId("org-type-company")).toBeTruthy();
    expect(screen.getByText("Individual")).toBeTruthy();
    expect(screen.getByText("Empresa")).toBeTruthy();
  });

  it("hides number-of-users field by default (individual is default)", async () => {
    renderOnboarding();
    await waitForStep();

    const field = screen.getByTestId("number-of-users-field");
    // Field is rendered but visually hidden via CSS opacity/max-height transition
    // The element must exist in DOM but carry the hidden classes
    expect(field.className).toContain("max-h-0");
    expect(field.className).toContain("opacity-0");
  });

  it("shows number-of-users field when Empresa is selected", async () => {
    renderOnboarding();
    await waitForStep();

    const companyBtn = screen.getByTestId("org-type-company");
    fireEvent.click(companyBtn);

    const field = screen.getByTestId("number-of-users-field");
    expect(field.className).toContain("max-h-24");
    expect(field.className).toContain("opacity-100");
  });

  it("hides number-of-users field when switching back to Individual", async () => {
    renderOnboarding();
    await waitForStep();

    // Select company first
    fireEvent.click(screen.getByTestId("org-type-company"));
    // Then switch back
    fireEvent.click(screen.getByTestId("org-type-individual"));

    const field = screen.getByTestId("number-of-users-field");
    expect(field.className).toContain("max-h-0");
    expect(field.className).toContain("opacity-0");
  });

  it("resets number-of-users to 1 when switching back to Individual", async () => {
    renderOnboarding();
    await waitForStep();

    // Select company and set a value
    fireEvent.click(screen.getByTestId("org-type-company"));
    const input = screen.getByTestId("number-of-users-input");
    fireEvent.change(input, { target: { value: "25" } });
    expect((input as HTMLInputElement).value).toBe("25");

    // Switch back to individual
    fireEvent.click(screen.getByTestId("org-type-individual"));
    // Input value is reset to 1 via the onClick handler
    expect((input as HTMLInputElement).value).toBe("1");
  });

  it("number-of-users input enforces minimum of 1", async () => {
    renderOnboarding();
    await waitForStep();

    fireEvent.click(screen.getByTestId("org-type-company"));
    const input = screen.getByTestId("number-of-users-input") as HTMLInputElement;

    // Setting to 0 should be clamped to 1
    fireEvent.change(input, { target: { value: "0" } });
    expect(input.value).toBe("1");
  });
});
