/**
 * ForgotPassword page — seed consumer contract test (PF Phase 6.a).
 *
 * Thin wrapper around the seed `ForgotPasswordPage` (design-system).
 * Asserts the brand + supabase props plus the renderLink seam.
 *
 * Manual browser QA (DEFERRED): real reset-email round-trip, success/error
 * UX states. Destination: user/orchestrator at Phase 7 manual QA pass.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("@noctusai/seed/infra", () => ({
  supabase: { auth: { resetPasswordForEmail: vi.fn() } },
}));

// Stub only the named export PF consumes; avoid importActual on the barrel
// (which pulls in react-router-dom UMD path under vitest).
const forgotPasswordSpy = vi.fn();
vi.mock("@noctusai/lib/design-system", () => ({
  ForgotPasswordPage: (props: Record<string, unknown>) => {
    forgotPasswordSpy(props);
    return <div data-testid="forgot-password-mock">forgot</div>;
  },
}));

import ForgotPassword from "@/pages/ForgotPassword";

describe("ForgotPassword page (PF Phase 6.a — seed consumer)", () => {
  it("renders the seed ForgotPasswordPage with the PF brand + supabase client", () => {
    render(
      <MemoryRouter>
        <ForgotPassword />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("forgot-password-mock")).not.toBeNull();
    expect(forgotPasswordSpy).toHaveBeenCalledTimes(1);
    const props = forgotPasswordSpy.mock.calls[0][0] as Record<string, unknown>;

    expect(props.brandTitle).toBe("Financas Pessoais");
    expect(props.brandIcon).toBeDefined();
    expect(props.supabase).toBeDefined();
    expect(typeof props.renderLink).toBe("function");
  });
});
