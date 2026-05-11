/**
 * StaleBadge unit tests — PF Phase 5 PF-6 yfinance degraded-mode UX.
 *
 * Covers the pure `computeStaleness` decision function and the rendered
 * `<StaleBadge>` shape across the four-way decision tree
 * (dry-run / no-timestamp / old / fresh).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { StaleBadge, computeStaleness } from "@/components/StaleBadge";

// Anchor "now" to a deterministic instant so age computations are stable.
const NOW_ISO = "2026-05-10T12:00:00.000Z";
const NOW_MS = new Date(NOW_ISO).getTime();
const fixedNow = () => NOW_MS;

function minutesAgo(minutes: number): string {
  return new Date(NOW_MS - minutes * 60_000).toISOString();
}

describe("computeStaleness", () => {
  it("returns null when cotacao is missing", () => {
    expect(computeStaleness(undefined, "acao", fixedNow)).toBeNull();
    expect(computeStaleness(null, "acao", fixedNow)).toBeNull();
  });

  it("flags dry-run fonte unconditionally", () => {
    expect(
      computeStaleness({ fonte: "dry-run", timestamp: NOW_ISO }, "acao", fixedNow),
    ).toEqual({ reason: "dry-run" });
  });

  it("flags missing timestamp", () => {
    expect(
      computeStaleness({ fonte: "yfinance" }, "acao", fixedNow),
    ).toEqual({ reason: "no-timestamp" });
  });

  it("flags malformed timestamp", () => {
    expect(
      computeStaleness({ fonte: "yfinance", timestamp: "not-a-date" }, "acao", fixedNow),
    ).toEqual({ reason: "no-timestamp" });
  });

  it("returns null for a fresh quote inside the stocks 15min window", () => {
    expect(
      computeStaleness(
        { fonte: "yfinance", timestamp: minutesAgo(10) },
        "acao",
        fixedNow,
      ),
    ).toBeNull();
  });

  it("flags a stocks quote older than 15 minutes", () => {
    expect(
      computeStaleness(
        { fonte: "yfinance", timestamp: minutesAgo(20) },
        "acao",
        fixedNow,
      ),
    ).toEqual({ reason: "old", ageMinutes: 20 });
  });

  it("uses the 30-minute window for funds (fundo / fii)", () => {
    expect(
      computeStaleness(
        { fonte: "yfinance", timestamp: minutesAgo(25) },
        "fundo",
        fixedNow,
      ),
    ).toBeNull();
    expect(
      computeStaleness(
        { fonte: "yfinance", timestamp: minutesAgo(35) },
        "fii",
        fixedNow,
      ),
    ).toEqual({ reason: "old", ageMinutes: 35 });
  });
});

describe("<StaleBadge />", () => {
  it("renders nothing when the quote is fresh", () => {
    const { container } = render(
      <StaleBadge
        cotacao={{ fonte: "yfinance", timestamp: minutesAgo(5) }}
        kind="acao"
        now={fixedNow}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders the dry-run badge when fonte is dry-run", () => {
    render(
      <StaleBadge
        cotacao={{ fonte: "dry-run", timestamp: NOW_ISO }}
        kind="acao"
        now={fixedNow}
      />,
    );
    const badge = screen.getByTestId("stale-badge-dry-run");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toContain("Dados simulados");
  });

  it("renders the no-timestamp badge when timestamp is missing", () => {
    render(
      <StaleBadge
        cotacao={{ fonte: "yfinance" }}
        kind="acao"
        now={fixedNow}
      />,
    );
    const badge = screen.getByTestId("stale-badge-no-timestamp");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toContain("Idade desconhecida");
  });

  it("renders the old-quote badge with computed age in minutes", () => {
    render(
      <StaleBadge
        cotacao={{ fonte: "yfinance", timestamp: minutesAgo(45) }}
        kind="acao"
        now={fixedNow}
      />,
    );
    const badge = screen.getByTestId("stale-badge-old");
    expect(badge).not.toBeNull();
    expect(badge.textContent).toContain("45min");
  });
});
