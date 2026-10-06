/// <reference types="@testing-library/jest-dom" />
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { mockRechartsLayout } from "../charts/_recharts-test-utils";
import {
  MediaInsightsModal,
  formatMediaInsightValue,
  MEDIA_INSIGHTS_EMPTY_MESSAGE,
  type MediaInsightsModalProps,
} from "./MediaInsightsModal";

beforeAll(() => mockRechartsLayout());
afterEach(cleanup);

const SERIES = {
  metrics: [
    { key: "views", label: "Visualizações" },
    { key: "likes", label: "Curtidas" },
    { key: "comments", label: "Comentários" },
    { key: "saved", label: "Salvos" },
  ],
  points: [
    { date: "2026-05-01", views: 100, likes: 10, comments: 2, saved: null },
    { date: "2026-05-02", views: 200, likes: 15, comments: 3, saved: null },
  ],
};

function setup(over: Partial<MediaInsightsModalProps> = {}) {
  const props: MediaInsightsModalProps = {
    open: true,
    onOpenChange: vi.fn(),
    media: {
      title: "Meu reel",
      caption: "Legenda curta",
      mediaType: "Reel",
      publishedAt: "2026-05-01T12:00:00Z",
      permalink: "https://example.com/p/1",
      permalinkLabel: "Abrir no Instagram",
      thumbnailUrl: "https://example.com/t.jpg",
    },
    kpis: [
      { key: "views", label: "Visualizações", value: 1500 },
      { key: "saved", label: "Salvos", value: null },
    ],
    series: SERIES,
    ...over,
  };
  return { props, ...render(<MediaInsightsModal {...props} />) };
}

const pressed = (name: string) =>
  screen.getByRole("button", { name }).getAttribute("aria-pressed");

describe("MediaInsightsModal", () => {
  it("renders nothing when closed", () => {
    setup({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is a labelled dialog with title, type, permalink label/href and KPIs", () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAccessibleName("Meu reel");
    expect(screen.getByText("Reel")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Abrir no Instagram/ });
    expect(link).toHaveAttribute("href", "https://example.com/p/1");
    expect(screen.getByText("1.5K")).toBeInTheDocument();
    // null KPI renders an em dash, never 0
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("closes on Escape via onOpenChange(false)", () => {
    const { props } = setup();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(props.onOpenChange).toHaveBeenCalledWith(false);
  });

  it("selects the top-2 metrics by default and toggles others, keeping >= 1", () => {
    setup();
    expect(pressed("Visualizações")).toBe("true");
    expect(pressed("Curtidas")).toBe("true");
    expect(pressed("Comentários")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Comentários" }));
    expect(pressed("Comentários")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Curtidas" }));
    fireEvent.click(screen.getByRole("button", { name: "Visualizações" }));
    // last remaining series cannot be deselected
    fireEvent.click(screen.getByRole("button", { name: "Comentários" }));
    expect(pressed("Comentários")).toBe("true");
  });

  it("skips metrics with no data when choosing defaults", () => {
    setup({
      series: {
        ...SERIES,
        metrics: [{ key: "saved", label: "Salvos" }, ...SERIES.metrics.slice(0, 2)],
      },
    });
    expect(pressed("Salvos")).toBe("false");
    expect(pressed("Visualizações")).toBe("true");
    expect(pressed("Curtidas")).toBe("true");
  });

  it("draws a chart (svg paths) when history exists", () => {
    const { container } = setup();
    expect(container.ownerDocument.querySelectorAll("path.recharts-line-curve").length).toBe(2);
  });

  it("shows the empty-history message when there are no points", () => {
    setup({ series: { ...SERIES, points: [] } });
    expect(screen.getByText(MEDIA_INSIGHTS_EMPTY_MESSAGE)).toBeInTheDocument();
  });

  it("shows a skeleton only while loading with no series yet", () => {
    setup({ series: null, loading: true });
    expect(screen.getByRole("status", { name: "Carregando" })).toBeInTheDocument();
  });

  it("keeps the chart and shows 'Atualizando…' on a refetch over data", () => {
    setup({ loading: true });
    expect(screen.queryByRole("status", { name: "Carregando" })).toBeNull();
    expect(screen.getByText("Atualizando…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Visualizações" })).toBeInTheDocument();
  });

  it("shows the error with a working retry", () => {
    const onRetry = vi.fn();
    setup({ series: null, error: "Falhou", onRetry });
    expect(screen.getByRole("alert")).toHaveTextContent("Falhou");
    fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("clamps a long caption and expands it on demand", () => {
    setup({ media: { title: "T", caption: "x".repeat(300) } });
    const btn = screen.getByRole("button", { name: "Ver mais" });
    expect(btn).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(btn);
    expect(screen.getByRole("button", { name: "Ver menos" })).toHaveAttribute("aria-expanded", "true");
  });

  it("renders the product `extra` slot", () => {
    setup({ extra: <div>acoes do produto</div> });
    expect(screen.getByText("acoes do produto")).toBeInTheDocument();
  });
});

describe("formatMediaInsightValue", () => {
  it("formats by kind and renders null as an em dash", () => {
    expect(formatMediaInsightValue(null)).toBe("—");
    expect(formatMediaInsightValue(1234, "int")).toBe((1234).toLocaleString("pt-BR"));
    expect(formatMediaInsightValue(12.34, "percent")).toBe("12,3%");
    expect(formatMediaInsightValue(45_000, "duration_ms")).toBe("45 s");
    expect(formatMediaInsightValue(125_000, "duration_ms")).toBe("2:05 min");
  });
});
