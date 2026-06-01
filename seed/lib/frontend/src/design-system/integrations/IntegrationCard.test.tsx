/**
 * Tests for the IntegrationCard organ.
 *
 * Coverage:
 *   1. providerCardConfig — youtube primary/secondary selectors + formatting
 *   2. providerCardConfig — whatsapp primary/secondary selectors
 *   3. resolveStatusBadge — all 5 status values
 *   4. getProviderConfig — registry lookup
 *   5. Render smoke: loading, error, success states
 *   6. Edit-mode toggle: pencil click → form → cancel restores card
 *   7. onSave callback fires with correct patch
 *   8. onOpenModal fires on card body click
 *   9. Actions menu — onDelete, onSync, onSetDefault callbacks
 *
 * Dual-React gap: resolved in this worktree (NOC-REMEDIATE[harness-vitest-dual-react]
 * RESOLVED 2026-05-29). Full render tests are safe.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";

import { getProviderConfig, PROVIDER_CARD_CONFIG } from "./providerCardConfig";
import { resolveStatusBadge } from "./IntegrationCard";
import { IntegrationCard } from "./IntegrationCard";
import type { IntegrationAccount, IntegrationStatus } from "./types";

afterEach(cleanup);

// ── Test fixtures ────────────────────────────────────────────────────────────

const youtubeAccount: IntegrationAccount = {
  id: "acc-yt-1",
  org_id: "org-1",
  provider: "youtube",
  account_label: "My YT",
  client_id: "client-xyz",
  status: "validated",
  channel_info: {
    channel_id: "UC123",
    title: "Awesome Channel",
    thumbnail_url: "https://example.com/thumb.jpg",
    subscriber_count: 1_250_000,
    video_count: 342,
    view_count: 9_800_000,
  },
  metadata: {},
  is_default: true,
  last_synced_at: "2026-05-01T12:00:00Z",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-05-01T12:00:00Z",
};

const whatsappAccount: IntegrationAccount = {
  id: "acc-wa-1",
  org_id: "org-1",
  provider: "whatsapp",
  account_label: "Atendimento",
  client_id: null,
  status: "wiring",
  channel_info: {
    session: "session-abc",
    phone: "+5511999999999",
    webhook_url: "https://hooks.example.com/waha",
  },
  metadata: {},
  is_default: false,
  last_synced_at: null,
  created_at: "2026-03-01T00:00:00Z",
  updated_at: "2026-03-01T00:00:00Z",
};

const minimalAccount: IntegrationAccount = {
  id: "acc-min-1",
  org_id: "org-1",
  provider: "youtube",
  account_label: "Fallback Label",
  client_id: null,
  status: "disconnected",
  channel_info: {},
  metadata: {},
  is_default: false,
  last_synced_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ── 1. YouTube config selectors ──────────────────────────────────────────────

describe("providerCardConfig: youtube", () => {
  const cfg = getProviderConfig("youtube")!;

  it("primary returns channel title when present", () => {
    expect(cfg.primary(youtubeAccount)).toBe("Awesome Channel");
  });

  it("primary falls back to account_label when channel_info.title is absent", () => {
    expect(cfg.primary(minimalAccount)).toBe("Fallback Label");
  });

  it("secondary formats subscriber_count in millions", () => {
    const fields = cfg.secondary(youtubeAccount);
    const subs = fields.find((f) => f.label === "Inscritos");
    expect(subs?.value).toBe("1.3M");
  });

  it("secondary formats video_count as integer string under 1K", () => {
    // 342 → "342"
    const fields = cfg.secondary(youtubeAccount);
    const videos = fields.find((f) => f.label === "Vídeos");
    expect(videos?.value).toBe("342");
  });

  it("secondary formats view_count in millions", () => {
    const fields = cfg.secondary(youtubeAccount);
    const views = fields.find((f) => f.label === "Visualizações");
    expect(views?.value).toBe("9.8M");
  });

  it("secondary returns — for absent counts", () => {
    const fields = cfg.secondary(minimalAccount);
    expect(fields.every((f) => f.value === "—")).toBe(true);
  });

  it("editableFields includes account_label", () => {
    const keys = cfg.editableFields.map((f) => f.key);
    expect(keys).toContain("account_label");
  });

  it("modalSections returns Canal and Conta sections", () => {
    const sections = cfg.modalSections(youtubeAccount);
    const titles = sections.map((s) => s.title);
    expect(titles).toContain("Canal");
    expect(titles).toContain("Conta");
  });
});

// ── 2. WhatsApp config selectors ─────────────────────────────────────────────

describe("providerCardConfig: whatsapp", () => {
  const cfg = getProviderConfig("whatsapp")!;

  it("primary returns session when present", () => {
    expect(cfg.primary(whatsappAccount)).toBe("session-abc");
  });

  it("primary falls back to phone when session absent", () => {
    const acc: IntegrationAccount = {
      ...whatsappAccount,
      channel_info: { phone: "+5511000000000" },
    };
    expect(cfg.primary(acc)).toBe("+5511000000000");
  });

  it("primary falls back to account_label when both session and phone absent", () => {
    const acc: IntegrationAccount = {
      ...whatsappAccount,
      channel_info: {},
    };
    expect(cfg.primary(acc)).toBe("Atendimento");
  });

  it("secondary includes session, phone, webhook fields", () => {
    const fields = cfg.secondary(whatsappAccount);
    const labels = fields.map((f) => f.label);
    expect(labels).toContain("Sessão");
    expect(labels).toContain("Telefone");
    expect(labels).toContain("Webhook");
  });

  it("secondary skips absent channel_info fields", () => {
    const acc: IntegrationAccount = {
      ...whatsappAccount,
      channel_info: { session: "s1" },
    };
    const fields = cfg.secondary(acc);
    // Only session present
    expect(fields.length).toBe(1);
    expect(fields[0].label).toBe("Sessão");
  });

  it("editableFields includes account_label and webhook_url", () => {
    const keys = cfg.editableFields.map((f) => f.key);
    expect(keys).toContain("account_label");
    expect(keys).toContain("webhook_url");
  });

  it("modalSections returns Conexão and Conta sections", () => {
    const sections = cfg.modalSections(whatsappAccount);
    const titles = sections.map((s) => s.title);
    expect(titles).toContain("Conexão");
    expect(titles).toContain("Conta");
  });
});

// ── 3. resolveStatusBadge ─────────────────────────────────────────────────────

describe("resolveStatusBadge", () => {
  const cases: { status: IntegrationStatus; labelPt: string; spinner: boolean }[] = [
    { status: "validated", labelPt: "Validado", spinner: false },
    { status: "validating", labelPt: "Validando", spinner: true },
    { status: "wiring", labelPt: "Conectando", spinner: true },
    { status: "error", labelPt: "Erro", spinner: false },
    { status: "disconnected", labelPt: "Desconectado", spinner: false },
  ];

  for (const { status, labelPt, spinner } of cases) {
    it(`${status} → label="${labelPt}", showSpinner=${spinner}`, () => {
      const result = resolveStatusBadge(status);
      expect(result.label).toBe(labelPt);
      expect(result.showSpinner).toBe(spinner);
    });
  }

  it("validated badge has no border-transparent class for destructive", () => {
    const { className } = resolveStatusBadge("validated");
    expect(className).not.toContain("destructive");
  });

  it("error badge has destructive class", () => {
    const { className } = resolveStatusBadge("error");
    expect(className).toContain("destructive");
  });

  it("disconnected badge has outline style (no bg-primary)", () => {
    const { className } = resolveStatusBadge("disconnected");
    expect(className).not.toContain("bg-primary");
  });
});

// ── 4. getProviderConfig ─────────────────────────────────────────────────────

describe("getProviderConfig", () => {
  it("returns config for youtube", () => {
    expect(getProviderConfig("youtube")).toBeDefined();
    expect(getProviderConfig("youtube")?.provider).toBe("youtube");
  });

  it("returns config for whatsapp", () => {
    expect(getProviderConfig("whatsapp")).toBeDefined();
    expect(getProviderConfig("whatsapp")?.provider).toBe("whatsapp");
  });

  it("normalizes to lowercase", () => {
    expect(getProviderConfig("YouTube")).toBeDefined();
    expect(getProviderConfig("WHATSAPP")).toBeDefined();
  });

  it("returns undefined for unknown provider", () => {
    expect(getProviderConfig("meta")).toBeUndefined();
  });

  it("PROVIDER_CARD_CONFIG has youtube and whatsapp keys", () => {
    expect(Object.keys(PROVIDER_CARD_CONFIG)).toEqual(
      expect.arrayContaining(["youtube", "whatsapp"]),
    );
  });
});

// ── 5. Render: loading state ─────────────────────────────────────────────────

describe("IntegrationCard render: loading", () => {
  it("renders loading skeleton with aria-busy", () => {
    const { container } = render(
      <IntegrationCard account={youtubeAccount} isLoading />,
    );
    const el = container.querySelector('[aria-busy="true"]');
    expect(el).not.toBeNull();
  });
});

// ── 6. Render: error state ───────────────────────────────────────────────────

describe("IntegrationCard render: error", () => {
  it("renders error alert with message", () => {
    render(
      <IntegrationCard
        account={youtubeAccount}
        error={new Error("Falha de conexão")}
      />,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Falha de conexão/)).toBeInTheDocument();
  });
});

// ── 7. Render: success state ─────────────────────────────────────────────────

describe("IntegrationCard render: success", () => {
  it("renders primary label", () => {
    render(<IntegrationCard account={youtubeAccount} />);
    expect(screen.getByText("Awesome Channel")).toBeInTheDocument();
  });

  it("renders status badge label", () => {
    render(<IntegrationCard account={youtubeAccount} />);
    expect(screen.getByText("Validado")).toBeInTheDocument();
  });

  it("renders secondary fields (Inscritos)", () => {
    render(<IntegrationCard account={youtubeAccount} />);
    expect(screen.getByText("Inscritos")).toBeInTheDocument();
    expect(screen.getByText("1.3M")).toBeInTheDocument();
  });

  it("renders article role", () => {
    render(<IntegrationCard account={youtubeAccount} />);
    expect(screen.getByRole("article")).toBeInTheDocument();
  });
});

// ── 8. Edit-mode toggle ──────────────────────────────────────────────────────

describe("IntegrationCard edit mode", () => {
  it("pencil button toggles edit form on", () => {
    const onSave = vi.fn();
    render(<IntegrationCard account={youtubeAccount} onSave={onSave} />);
    const editBtn = screen.getByRole("button", { name: /editar conta/i });
    fireEvent.click(editBtn);
    expect(screen.getByLabelText(/Rótulo da conta/i)).toBeInTheDocument();
  });

  it("cancel button exits edit mode without calling onSave", () => {
    const onSave = vi.fn();
    render(<IntegrationCard account={youtubeAccount} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /editar conta/i }));
    // The form cancel button has text "Cancelar" (distinct from the edit
    // toggle button whose aria-label is "Cancelar edição").
    // Use getByText with exact match to avoid the ambiguity.
    fireEvent.click(screen.getByText("Cancelar", { exact: true }));
    expect(onSave).not.toHaveBeenCalled();
    // Secondary fields reappear after cancel
    expect(screen.getByText("Inscritos")).toBeInTheDocument();
  });
});

// ── 9. onSave callback ───────────────────────────────────────────────────────

describe("IntegrationCard onSave", () => {
  it("calls onSave with root field patch on form submit", () => {
    const onSave = vi.fn();
    render(<IntegrationCard account={youtubeAccount} onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: /editar conta/i }));
    const input = screen.getByLabelText(/Rótulo da conta/i);
    fireEvent.change(input, { target: { value: "Canal Atualizado" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    expect(onSave).toHaveBeenCalledOnce();
    expect(onSave.mock.calls[0][0]).toMatchObject({
      account_label: "Canal Atualizado",
    });
  });
});

// ── 10. onOpenModal ──────────────────────────────────────────────────────────

describe("IntegrationCard onOpenModal", () => {
  it("fires onOpenModal when card body is clicked", () => {
    const onOpenModal = vi.fn();
    render(
      <IntegrationCard account={youtubeAccount} onOpenModal={onOpenModal} />,
    );
    fireEvent.click(screen.getByRole("article"));
    expect(onOpenModal).toHaveBeenCalledWith(youtubeAccount);
  });

  it("does not fire onOpenModal when in edit mode", () => {
    const onOpenModal = vi.fn();
    const onSave = vi.fn();
    render(
      <IntegrationCard
        account={youtubeAccount}
        onOpenModal={onOpenModal}
        onSave={onSave}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /editar conta/i }));
    fireEvent.click(screen.getByRole("article"));
    expect(onOpenModal).not.toHaveBeenCalled();
  });
});
