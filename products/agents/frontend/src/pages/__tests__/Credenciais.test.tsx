/**
 * Credenciais.tsx + ConfiguracoesAgente.tsx page tests — rendering only
 * (hooks stubbed; the hooks have their own tests).
 *
 * Isolation: every query is scoped to THIS test's own `render()` result
 * (`within(container)`), never the ambient `screen` (= the whole
 * `document.body`). `screen` matches across every node currently attached
 * to the document, so under a full parallel run — many files, some sharing
 * a worker — a still-mounting/unmounting neighbour can transiently leave a
 * second node with the same `data-testid` in the body between this file's
 * own `cleanup()` calls; the flake this fixes ("multiple elements found")
 * is exactly that cross-render ambiguity, not a bug in either page.
 * Scoping to the container makes the assertion correct regardless of what
 * else is attached to `document.body` at that instant.
 */
import React from "react";
import { cleanup, render, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@noctusai/lib";

const mockUseCredentials = vi.fn();
const idle = () => ({ mutateAsync: vi.fn(), isPending: false });

vi.mock("@/hooks/useCredentials", () => ({
  useCredentials: () => mockUseCredentials(),
  useImportCredential: idle,
  useProbeCredential: idle,
  useRenewCredential: idle,
  useRingAction: idle,
  useSetCredential: idle,
}));

const mockUseAgentSettings = vi.fn();
vi.mock("@/hooks/useAgentSettings", () => ({
  useAgentSettings: () => mockUseAgentSettings(),
  useUpdateAgentSettings: idle,
}));

vi.mock("@/hooks/useAgents", () => ({
  useAgents: () => ({ data: [] }),
  useToggleAgent: idle,
}));

const TOKEN = {
  name: "academia_api_token",
  label: "Token da API academia-de-reciclagem",
  kind: "product_token",
  env_var: "ACADEMIA_API_TOKEN",
  configured: true,
  source: "env",
  prefix: "pk_aaaaaaaa",
  fingerprint: null,
  value: null,
  expires_at: "2026-10-01T00:00:00Z",
  days_left: 15,
  last_used_at: null,
  revoked: false,
  scopes: [],
  renewable: true,
  probeable: true,
  writable: true,
  ring: [],
  warnings: ["Expira em 15 dia(s) — renove."],
  severity: "warning",
};

const RING = {
  ...TOKEN,
  name: "approval_assertion_secrets",
  kind: "key_ring",
  source: "db",
  prefix: null,
  fingerprint: "abc123def456",
  expires_at: null,
  days_left: null,
  renewable: false,
  probeable: false,
  warnings: [],
  severity: "info",
  ring: [
    { fingerprint: "abc123def456", active_from: "2026-09-01T00:00:00Z", retire_at: null, signing: true, state: "active" },
  ],
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

/** Renders and returns queries SCOPED to this render's own container (see
 * file header) — never the ambient `screen`. */
async function renderCredenciais() {
  const Page = (await import("@/pages/Credenciais")).default;
  const { container } = render(React.createElement(MemoryRouter, null, React.createElement(Page)));
  return within(container);
}

describe("Credenciais", () => {
  it("shows prefix, days left, warning and the renew action", async () => {
    mockUseCredentials.mockReturnValue({
      data: { items: [TOKEN, RING], total: 2, alerts: 1 },
      showSkeleton: false,
      isError: false,
    });
    const view = await renderCredenciais();
    expect(view.getByTestId("credential-prefix-academia_api_token").textContent).toBe("pk_aaaaaaaa");
    expect(view.getByTestId("credential-days-academia_api_token").textContent).toBe("15");
    expect(view.getByTestId("credential-warnings-academia_api_token").textContent).toContain("15 dia");
    expect(view.getByTestId("credential-renew-academia_api_token")).toBeTruthy();
    expect(view.getByTestId("credentials-alert-banner")).toBeTruthy();
    expect(view.getByTestId("ring-keys").textContent).toContain("assinando");
    expect(view.getByTestId("ring-rotate")).toBeTruthy();
  });

  it("shows the skeleton only while nothing is loaded", async () => {
    mockUseCredentials.mockReturnValue({ data: undefined, showSkeleton: true, isError: false });
    const view = await renderCredenciais();
    expect(view.getByTestId("credentials-skeleton")).toBeTruthy();
    expect(view.queryByTestId("credentials-list")).toBeNull();
  });

  it("explains a 403 as platform-admin only", async () => {
    mockUseCredentials.mockReturnValue({
      data: undefined,
      error: new ApiError(403, "Restrito", { detail: "Restrito", code: "platform_admin_required" }),
      showSkeleton: false,
      isError: true,
    });
    const view = await renderCredenciais();
    expect(view.getByTestId("credentials-error").textContent).toContain("administradores da plataforma");
  });
});

describe("ConfiguracoesAgente", () => {
  it("renders editable settings and the read-only slot count", async () => {
    mockUseAgentSettings.mockReturnValue({
      data: [
        { key: "approval_timeout_seconds", value: 300, default: 300, source: "env", editable: true, min: 30, max: 570 },
        { key: "julia_cli_slots", value: 3, default: 3, source: "env", editable: false, min: null, max: null },
      ],
      showSkeleton: false,
      isError: false,
    });
    const Page = (await import("@/pages/ConfiguracoesAgente")).default;
    const { container } = render(React.createElement(MemoryRouter, null, React.createElement(Page)));
    const view = within(container);
    const slots = view.getByLabelText("Conversas simultâneas (slots)") as HTMLInputElement;
    expect(slots.disabled).toBe(true);
    expect(slots.value).toBe("3");
    const timeout = view.getByLabelText("Tempo limite de aprovação (segundos)") as HTMLInputElement;
    expect(timeout.disabled).toBe(false);
    expect(timeout.value).toBe("300");
  });
});
