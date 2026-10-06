import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

afterEach(cleanup);

const h = vi.hoisted(() => ({ active: vi.fn(), meta: vi.fn() }));
vi.mock("@noctusai/seed/infra", () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock("@/hooks/useInstagramInsights", () => ({ useActiveInstagramAccount: h.active }));
vi.mock("@/hooks/useMeta", () => ({ useActiveMetaAccountId: h.meta }));
vi.mock("@/components/instagram/InstagramProfileView", () => ({
  InstagramProfileView: ({ accountId, showPosts }: any) => (
    <div data-testid="profile-view">{accountId}:{String(showPosts)}</div>
  ),
}));
vi.mock("@/components/instagram/InstagramPostGrid", () => ({
  InstagramPostGrid: ({ accountId }: any) => <div data-testid="post-grid">{accountId}</div>,
}));
vi.mock("@/pages/meta/IgVisaoGeral", () => ({ default: () => <div data-testid="legacy-overview" /> }));

import { IgOverview, IgPublicacoes } from "./IgOverview";

describe("Instagram subtab wiring", () => {
  it("overview renders the shared profile view (no grid) for the instagram account", () => {
    h.active.mockReturnValue({ accountId: "ig1", isPending: false });
    h.meta.mockReturnValue(null);
    render(<IgOverview />);
    expect(screen.getByTestId("profile-view").textContent).toBe("ig1:false");
  });

  it("publicações renders the grid", () => {
    h.active.mockReturnValue({ accountId: "ig1", isPending: false });
    render(<IgPublicacoes />);
    expect(screen.getByTestId("post-grid").textContent).toBe("ig1");
  });

  it("overview falls back to the legacy Facebook-Login view when only Meta is connected", async () => {
    h.active.mockReturnValue({ accountId: null, isPending: false });
    h.meta.mockReturnValue("meta1");
    render(<IgOverview />);
    expect(await screen.findByTestId("legacy-overview")).toBeTruthy();
  });

  it("empty and loading states", () => {
    h.active.mockReturnValue({ accountId: null, isPending: false });
    h.meta.mockReturnValue(null);
    const a = render(<IgPublicacoes />);
    expect(screen.getByTestId("ig-no-instagram-account")).toBeTruthy();
    a.unmount();
    h.active.mockReturnValue({ accountId: null, isPending: true });
    render(<IgPublicacoes />);
    expect(screen.getByTestId("ig-accounts-loading")).toBeTruthy();
  });
});
