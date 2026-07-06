/**
 * Tests for the SocialDashboardShell organ.
 *
 * Coverage:
 *   1. Header: title + subtitle + accountSwitcher slot render.
 *   2. No network toggle when `networks` is omitted (YouTube shape).
 *   3. Network toggle renders + `onNetworkChange` fires on click (Meta shape).
 *   4. Subtabs: trigger + content render; clicking a trigger switches the
 *      visible panel; `render()` receives no stale content.
 *   5. `defaultSubtab` is respected on first mount.
 *   6. Self-heal: when the `subtabs` set changes underneath the active key
 *      (the MetaDashboard "FB has no dms" case), the shell falls back to a
 *      valid subtab instead of rendering a dead panel.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { useState } from "react";
import { BarChart3, Grid3x3, Instagram, Facebook } from "lucide-react";

import { SocialDashboardShell } from "./SocialDashboardShell";
import type { SocialDashboardSubtab } from "./SocialDashboardShell";

afterEach(cleanup);

const OVERVIEW: SocialDashboardSubtab = {
  key: "overview",
  label: "Visão geral",
  icon: BarChart3,
  render: () => <div>Painel de visão geral</div>,
};

const CONTENT: SocialDashboardSubtab = {
  key: "content",
  label: "Conteúdo",
  icon: Grid3x3,
  render: () => <div>Painel de conteúdo</div>,
};

const DMS: SocialDashboardSubtab = {
  key: "dms",
  label: "DMs",
  icon: Grid3x3,
  render: () => <div>Painel de DMs</div>,
};

// ── 1-2. Single-network (YouTube) shape ──────────────────────────────────────

describe("SocialDashboardShell — single-network shape", () => {
  it("renders title, subtitle and the accountSwitcher slot", () => {
    render(
      <SocialDashboardShell
        title="YouTube"
        subtitle="Visão geral, catálogo do canal e envios de vídeo."
        accountSwitcher={<div data-testid="switcher-stub">Switcher</div>}
        subtabs={[OVERVIEW, CONTENT]}
      />,
    );

    expect(screen.getByText("YouTube")).toBeInTheDocument();
    expect(
      screen.getByText("Visão geral, catálogo do canal e envios de vídeo."),
    ).toBeInTheDocument();
    expect(screen.getByTestId("switcher-stub")).toBeInTheDocument();
  });

  it("renders no network toggle when `networks` is omitted", () => {
    render(<SocialDashboardShell title="YouTube" subtabs={[OVERVIEW, CONTENT]} />);

    expect(
      screen.queryByTestId("social-dashboard-network-toggle"),
    ).not.toBeInTheDocument();
  });
});

// ── 3. Multi-network (Meta) shape ────────────────────────────────────────────

describe("SocialDashboardShell — multi-network shape", () => {
  it("renders the network toggle and fires onNetworkChange on click", () => {
    const onNetworkChange = vi.fn();
    render(
      <SocialDashboardShell
        title="Meta"
        networks={[
          { key: "instagram", label: "Instagram", icon: Instagram },
          { key: "facebook", label: "Facebook", icon: Facebook },
        ]}
        activeNetwork="instagram"
        onNetworkChange={onNetworkChange}
        subtabs={[OVERVIEW, CONTENT]}
      />,
    );

    expect(screen.getByTestId("social-dashboard-network-toggle")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("social-dashboard-network-facebook"));
    expect(onNetworkChange).toHaveBeenCalledWith("facebook");
  });
});

// ── 4-5. Subtab switching + defaultSubtab ───────────────────────────────────

describe("SocialDashboardShell — subtab switching", () => {
  it("respects defaultSubtab and switches panels on trigger click", () => {
    render(
      <SocialDashboardShell
        title="YouTube"
        subtabs={[OVERVIEW, CONTENT]}
        defaultSubtab="content"
      />,
    );

    expect(screen.getByText("Painel de conteúdo")).toBeInTheDocument();
    expect(screen.queryByText("Painel de visão geral")).not.toBeInTheDocument();

    // Radix `Tabs.Trigger` wires selection to `onMouseDown` (+ `onFocus` for
    // roving-tabindex activation), not `onClick` — see
    // `@radix-ui/react-tabs`'s `TabsTrigger` implementation.
    fireEvent.mouseDown(screen.getByText("Visão geral"));

    expect(screen.getByText("Painel de visão geral")).toBeInTheDocument();
    expect(screen.queryByText("Painel de conteúdo")).not.toBeInTheDocument();
  });
});

// ── 6. Self-heal when the active subtab drops out of the current set ───────

function NetworkSwitchingHarness() {
  const [subtabs, setSubtabs] = useState<SocialDashboardSubtab[]>([
    OVERVIEW,
    CONTENT,
    DMS,
  ]);

  return (
    <>
      <button onClick={() => setSubtabs([OVERVIEW, CONTENT])}>
        Trocar para Facebook
      </button>
      <SocialDashboardShell title="Meta" subtabs={subtabs} defaultSubtab="dms" />
    </>
  );
}

describe("SocialDashboardShell — self-heal on subtabs change", () => {
  it("falls back to a valid subtab instead of rendering a dead panel", () => {
    render(<NetworkSwitchingHarness />);

    // defaultSubtab="dms" is honored while "dms" is present.
    expect(screen.getByText("Painel de DMs")).toBeInTheDocument();

    // Simulate MetaDashboard's network switch dropping the "dms" subtab.
    fireEvent.click(screen.getByText("Trocar para Facebook"));

    // No dead "dms" panel; falls back to defaultSubtab's nearest valid
    // sibling — here the first remaining subtab.
    expect(screen.queryByText("Painel de DMs")).not.toBeInTheDocument();
    expect(screen.getByText("Painel de visão geral")).toBeInTheDocument();
  });
});
