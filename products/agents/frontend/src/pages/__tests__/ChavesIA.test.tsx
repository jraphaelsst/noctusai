import React from "react";
import { cleanup, render, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mockAdmin = vi.fn();
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => mockAdmin() }));
vi.mock("@/hooks/useOrgApiKeys", () => ({ orgApiKeysHooks: { marker: true } }));
vi.mock("@noctusai/lib/components", () => ({
  ApiKeysPanel: ({ hooks }: { hooks: { marker: boolean } }) => (
    <div data-testid="api-keys-panel-stub">{String(hooks.marker)}</div>
  ),
}));

import ChavesIA from "../ChavesIA";

afterEach(cleanup);

describe("ChavesIA", () => {
  it("admin: consumes the canonical ApiKeysPanel organ", () => {
    mockAdmin.mockReturnValue(true);
    const { container } = render(<ChavesIA />);
    expect(within(container).getByTestId("api-keys-panel-stub").textContent).toBe("true");
  });

  it("non-admin: shows the forbidden notice and no panel", () => {
    mockAdmin.mockReturnValue(false);
    const { container } = render(<ChavesIA />);
    expect(within(container).getByTestId("chaves-ia-forbidden")).toBeTruthy();
    expect(within(container).queryByTestId("api-keys-panel-stub")).toBeNull();
  });
});
