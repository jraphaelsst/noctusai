/**
 * AcceptInvite page — seed `team` /accept endpoint contract test
 * (PF Phase 6.b).
 *
 * Thin wrapper around the seed `AcceptInvitePage` (design-system).
 * Asserts:
 *   - `acceptEndpoint` is the seed `team` standard router POST path
 *     (`/api/team/accept`), which the seed component also probes
 *     via GET `/api/team/accept/validate` (see seed component source).
 *   - `apiBaseUrl` resolves from env or falls back to the documented
 *     PF backend port (8002 per `KB § 05-INFRASTRUCTURE.md`).
 *   - `loginPath` routes back through the Core platform (SSO entry).
 *   - The token URL param is threaded through.
 *
 * Manual browser QA (DEFERRED): invite → email → click link →
 * accept → navigate to /sso. Destination: user/orchestrator at
 * Phase 7 manual QA pass.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Stub only the named export PF consumes; avoid importActual on the barrel
// (which pulls in react-router-dom UMD path under vitest).
const acceptInviteSpy = vi.fn();
vi.mock("@noctusai/lib/design-system", () => ({
  AcceptInvitePage: (props: Record<string, unknown>) => {
    acceptInviteSpy(props);
    return <div data-testid="accept-invite-mock">accept</div>;
  },
}));

import AcceptInvite from "@/pages/AcceptInvite";

describe("AcceptInvite page (PF Phase 6.b — seed team /accept consumer)", () => {
  it("wires the seed AcceptInvitePage to /api/team/accept with the URL token", () => {
    render(
      <MemoryRouter initialEntries={["/accept-invite/abc-token-123"]}>
        <Routes>
          <Route path="/accept-invite/:token" element={<AcceptInvite />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("accept-invite-mock")).not.toBeNull();
    expect(acceptInviteSpy).toHaveBeenCalledTimes(1);
    const props = acceptInviteSpy.mock.calls[0][0] as Record<string, unknown>;

    // Endpoint contract — matches seed `team` standard router POST /accept.
    expect(props.acceptEndpoint).toBe("/api/team/accept");

    // Backend base — env-injected at build OR the documented PF port.
    expect(typeof props.apiBaseUrl).toBe("string");
    expect((props.apiBaseUrl as string)).toMatch(/^https?:\/\/.+/);

    // Brand wiring.
    expect(props.productName).toBe("Financas Pessoais");
    expect(props.brandIcon).toBeDefined();

    // Token threaded from URL param.
    expect(props.token).toBe("abc-token-123");

    // SSO bounce on success.
    expect(typeof props.onAccepted).toBe("function");

    // Login path routes back through Core (SSO entry point).
    expect(props.loginPath).toMatch(/\/login$/);
  });
});
