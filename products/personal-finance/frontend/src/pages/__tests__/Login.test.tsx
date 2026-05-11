/**
 * Login page — seed-SSO consumer contract test (PF Phase 6.a).
 *
 * The page is a thin wrapper around the seed `LoginForm` (design-system).
 * We exercise the wiring contract — brand props, supabase client, the
 * `/sso` callback path is mounted by the seed factory automatically when
 * the supabase client is provided (see `seed/framework/frontend/src/app.tsx`
 * AppRoutes — `/sso` is gated on `supabase &&`).
 *
 * Manual browser QA (DEFERRED — no browser in worktree, per Phase 6
 * brief): real Supabase login round-trip, SSO redirect, logout. Destination:
 * user/orchestrator at Phase 7 manual QA pass.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Mock the seed/infra supabase client — Login uses it as a prop only.
vi.mock("@noctusai/seed/infra", () => ({
  supabase: { auth: { signInWithPassword: vi.fn() } },
}));

// Spy on LoginForm to assert the props PF passes (brand, supabase, etc).
// Avoid vi.importActual on design-system — pulls in the full barrel which
// transitively bridges to react-router-dom + UMD module resolution. Stubs
// suffice: Login.tsx only consumes the `LoginForm` named export.
const loginFormSpy = vi.fn();
vi.mock("@noctusai/lib/design-system", () => ({
  LoginForm: (props: Record<string, unknown>) => {
    loginFormSpy(props);
    return <div data-testid="login-form-mock">login</div>;
  },
}));

import Login from "@/pages/Login";

describe("Login page (PF Phase 6.a — seed-SSO consumer)", () => {
  it("renders the seed LoginForm with the PF brand props + supabase client", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("login-form-mock")).not.toBeNull();
    expect(loginFormSpy).toHaveBeenCalledTimes(1);
    const props = loginFormSpy.mock.calls[0][0] as Record<string, unknown>;

    // Brand wiring
    expect(props.brandTitle).toBe("Financas Pessoais");
    expect(props.brandSubtitle).toBe("Controle financeiro inteligente");
    expect(props.brandIcon).toBeDefined();

    // SSO/auth wiring
    expect(props.supabase).toBeDefined();
    expect(typeof props.onSuccess).toBe("function");
    expect(props.showForgotPassword).toBe(true);
    expect(typeof props.renderLink).toBe("function");
  });

  it("renders the 'Acesse pelo NoctusAI' link back to the core platform", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );
    const link = screen.getByText(/Acesse pelo NoctusAI/i);
    expect(link).not.toBeNull();
    expect(link.tagName).toBe("A");
    // Either the env-injected URL or the localhost default.
    expect((link as HTMLAnchorElement).getAttribute("href")).toMatch(
      /^https?:\/\/.+/,
    );
  });
});
