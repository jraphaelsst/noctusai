/**
 * Settings page tests — Meta App + Instagram App credentials sections
 * (Chaves API tab).
 *
 * Coverage (Meta App):
 *   1. Meta App section is hidden for a non-admin/dev user
 *   2. Meta App section renders for an admin/dev user (status badges)
 *   3. Save flow: fills App ID + App Secret, submits, calls useSaveMetaApp
 *      with the right payload, then clears both fields (secret never echoed)
 *   4. Validation: empty App ID blocks submit (no save() call)
 *
 * Coverage (Instagram App — mirrors Meta App):
 *   5. Instagram App section is hidden for a non-admin/dev user
 *   6. Instagram App section renders for an admin/dev user (status badges)
 *   7. Save flow calls useSaveInstagramApp with the right payload, clears
 *      both fields after success
 *   8. Validation: empty App ID blocks submit (no save() call)
 *
 * Mock strategy:
 *   · @noctusai/seed/infra — useAuthStore returns a fixture user
 *   · @noctusai/lib — resolveSSOContext (real role-resolution logic mirrored
 *     inline) + StatusPaginaPanel stubbed (Visibilidade tab, out of scope)
 *   · @/hooks/useSettings — all hooks mocked (recipients/keys/meta-app/instagram-app)
 *   · @/components/ui/tabs — stubbed as a structural pass-through (renders
 *     every TabsContent unconditionally) so the test doesn't depend on Radix's
 *     real activation semantics; Card/Badge/Input/etc stay real (thin shadcn
 *     wrappers, safe to render as-is).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// jsdom has no ResizeObserver — the default-active "Notificacoes" tab renders
// a real (unmocked) Radix Switch, whose thumb-sizing hook requires it.
// Local polyfill scoped to this file (no other suite in this product mounts
// a real Radix Switch yet — see the scoped-improvement footer).
if (typeof (globalThis as any).ResizeObserver === "undefined") {
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

afterEach(async () => {
  (await import("@testing-library/react")).cleanup();
});

// ─── @noctusai/seed/infra ────────────────────────────────────────────────
const mockUseAuthStore = vi.fn();
vi.mock("@noctusai/seed/infra", () => ({
  useAuthStore: mockUseAuthStore,
}));

// ─── @noctusai/lib ───────────────────────────────────────────────────────
vi.mock("@noctusai/lib", () => ({
  resolveSSOContext: (metadata: any) => {
    const m = metadata || {};
    const isProductAdmin =
      m.org_role === "owner" || m.org_role === "admin" || m.noctus_role === "admin";
    return {
      isSSO: !!m.noctus_role || !!m.org_role,
      isProductAdmin,
      plan: { slug: null, maxUsers: null, maxProducts: null, features: null },
      subscription: { status: null, expiresAt: null },
      license: { expiresAt: null },
      org: { name: null, logoUrl: null, role: m.org_role ?? "member" },
    };
  },
  StatusPaginaPanel: () => <div data-testid="status-pagina-panel" />,
}));

// ─── @/lib/api ───────────────────────────────────────────────────────────
vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

// ─── @/hooks/useSettings ─────────────────────────────────────────────────
const mockUseRecipients = vi.fn();
const mockUseKeysStatus = vi.fn();
const mockUseMetaAppStatus = vi.fn();
const mockSave = vi.fn();
const mockRefresh = vi.fn();
const mockUseInstagramAppStatus = vi.fn();
const mockSaveInstagram = vi.fn();
const mockRefreshInstagram = vi.fn();

vi.mock("@/hooks/useSettings", () => ({
  useRecipients: mockUseRecipients,
  useKeysStatus: mockUseKeysStatus,
  useMetaAppStatus: mockUseMetaAppStatus,
  useSaveMetaApp: () => ({ save: mockSave, saving: false }),
  useInstagramAppStatus: mockUseInstagramAppStatus,
  useSaveInstagramApp: () => ({ save: mockSaveInstagram, saving: false }),
}));

// `useClients` calls TanStack's `useQuery` directly, so without a
// QueryClientProvider it throws for the whole tab. Mocked with the two real
// clients so the recipient scope selector has something to render.
vi.mock("@/hooks/useClients", () => ({
  useClients: () => ({
    data: [
      { id: "client-one", name: "One Consultoria" },
      { id: "client-joao", name: "João Raphael" },
    ],
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ─── @/components/ui/tabs — structural pass-through ─────────────────────
// Renders every TabsContent unconditionally so tests don't depend on Radix's
// real click/keyboard activation semantics — only content correctness
// (Meta App section visibility + save flow) is under test here.
vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children }: any) => <div>{children}</div>,
  TabsList: ({ children }: any) => <div>{children}</div>,
  TabsTrigger: ({ children }: any) => <button type="button">{children}</button>,
  TabsContent: ({ children }: any) => <div>{children}</div>,
}));

// ─── Fixtures ────────────────────────────────────────────────────────────

const keyEntry = (label: string) => ({
  label,
  health: "configured" as const,
  description: `Descrição de ${label}`,
});

const KEYS_STATUS_FIXTURE = {
  youtube_client_id: keyEntry("YouTube Client ID"),
  youtube_client_secret: keyEntry("YouTube Client Secret"),
  youtube_redirect_uri: keyEntry("YouTube Redirect URI"),
  frontend_base_url: keyEntry("Frontend Base URL"),
  encryption_key: keyEntry("Encryption Key"),
  smtp_user: keyEntry("SMTP user"),
  smtp_password: keyEntry("SMTP password"),
  waha_base_url: keyEntry("WAHA base URL"),
  waha_api_key: keyEntry("WAHA API key"),
  waha_webhook_hmac_secret: keyEntry("WAHA webhook HMAC secret"),
  vista_base_url: keyEntry("Vista base URL"),
  vista_api_key: keyEntry("Vista API key"),
  database_backend: keyEntry("Database backend"),
  supabase_url: keyEntry("Supabase URL"),
  supabase_service_role_key: keyEntry("Supabase service role key"),
};

beforeEach(() => {
  mockUseRecipients.mockReturnValue({
    data: [],
    loading: false,
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  });
  mockUseKeysStatus.mockReturnValue({ data: KEYS_STATUS_FIXTURE, loading: false });
  mockUseMetaAppStatus.mockReturnValue({
    data: { app_id_configured: false, app_secret_configured: false },
    loading: false,
    refresh: mockRefresh,
  });
  mockSave.mockReset();
  mockSave.mockResolvedValue(undefined);
  mockRefresh.mockReset();
  mockUseInstagramAppStatus.mockReturnValue({
    data: { app_id_configured: false, app_secret_configured: false },
    loading: false,
    refresh: mockRefreshInstagram,
  });
  mockSaveInstagram.mockReset();
  mockSaveInstagram.mockResolvedValue(undefined);
  mockRefreshInstagram.mockReset();
});

// ─── Helpers ─────────────────────────────────────────────────────────────

function setUser(orgRole: string | null) {
  mockUseAuthStore.mockReturnValue({
    user: orgRole ? { user_metadata: { org_role: orgRole } } : { user_metadata: {} },
  });
}

async function renderSettingsOnKeysTab() {
  const { default: Settings } = await import("./Settings");
  const React = (await import("react")).default;
  const rtl = await import("@testing-library/react");
  const utils = rtl.render(React.createElement(Settings));
  return { ...utils, fireEvent: rtl.fireEvent };
}

// ─── Tests ───────────────────────────────────────────────────────────────

describe("Settings — Meta App section visibility", () => {
  it("is hidden for a non-admin/dev user", async () => {
    setUser("member");
    const { queryByText } = await renderSettingsOnKeysTab();
    expect(queryByText("Meta App")).toBeNull();
  });

  it("renders for an admin user with status badges", async () => {
    setUser("admin");
    const { getByText, getByTestId } = await renderSettingsOnKeysTab();
    expect(getByText("Meta App")).toBeTruthy();
    expect(getByTestId("meta-app-id-badge")).toBeTruthy();
    expect(getByTestId("meta-app-secret-badge")).toBeTruthy();
  });

  it("renders for a dev-role user (same gate as Visibilidade tab)", async () => {
    setUser("dev");
    const { getByText } = await renderSettingsOnKeysTab();
    expect(getByText("Meta App")).toBeTruthy();
  });

  it("shows 'ausente' badges when nothing is configured", async () => {
    setUser("owner");
    const { getByTestId } = await renderSettingsOnKeysTab();
    expect(getByTestId("meta-app-id-badge").textContent).toMatch(/ausente/i);
    expect(getByTestId("meta-app-secret-badge").textContent).toMatch(/ausente/i);
  });

  it("shows 'configurado' badges + masked hint when already set", async () => {
    setUser("owner");
    mockUseMetaAppStatus.mockReturnValue({
      data: {
        app_id_configured: true,
        app_secret_configured: true,
        app_id_masked: "1234****7890",
      },
      loading: false,
      refresh: mockRefresh,
    });
    const { getByTestId, getByText } = await renderSettingsOnKeysTab();
    expect(getByTestId("meta-app-id-badge").textContent).toMatch(/configurado/i);
    expect(getByTestId("meta-app-secret-badge").textContent).toMatch(/configurado/i);
    expect(getByText(/1234\*\*\*\*7890/)).toBeTruthy();
  });
});

describe("Settings — Meta App save flow", () => {
  it("blocks submit and does not call save() when App ID is empty", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();
    fireEvent.click(getByTestId("meta-app-save-btn"));
    expect(mockSave).not.toHaveBeenCalled();
  });

  it("calls save() with app_id + app_secret and clears both fields after success", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();

    const appIdInput = getByTestId("meta-app-id-input") as HTMLInputElement;
    const appSecretInput = getByTestId("meta-app-secret-input") as HTMLInputElement;

    fireEvent.change(appIdInput, { target: { value: "1234567890" } });
    fireEvent.change(appSecretInput, { target: { value: "supersecret" } });
    fireEvent.click(getByTestId("meta-app-save-btn"));

    // Flush the async handleSubmit (await save() + await refresh())
    await (await import("@testing-library/react")).waitFor(() => {
      expect(mockSave).toHaveBeenCalledWith({
        app_id: "1234567890",
        app_secret: "supersecret",
      });
    });

    await (await import("@testing-library/react")).waitFor(() => {
      // Secret (and App ID) are NEVER re-displayed after a save — the form
      // resets to empty rather than echoing what was typed.
      expect(appIdInput.value).toBe("");
      expect(appSecretInput.value).toBe("");
    });
    expect(mockRefresh).toHaveBeenCalled();
  });

  it("omits app_secret from the payload when left blank (keeps existing secret)", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByTestId("meta-app-id-input"), {
      target: { value: "999888777" },
    });
    fireEvent.click(getByTestId("meta-app-save-btn"));

    await (await import("@testing-library/react")).waitFor(() => {
      expect(mockSave).toHaveBeenCalledWith({
        app_id: "999888777",
        app_secret: undefined,
      });
    });
  });
});

describe("Settings — Instagram App section visibility", () => {
  it("is hidden for a non-admin/dev user", async () => {
    setUser("member");
    const { queryByText } = await renderSettingsOnKeysTab();
    expect(queryByText("Aplicativo Instagram")).toBeNull();
  });

  it("renders for an admin user with status badges", async () => {
    setUser("admin");
    const { getByText, getByTestId } = await renderSettingsOnKeysTab();
    expect(getByText("Aplicativo Instagram")).toBeTruthy();
    expect(getByTestId("instagram-app-id-badge")).toBeTruthy();
    expect(getByTestId("instagram-app-secret-badge")).toBeTruthy();
  });

  it("shows 'ausente' badges when nothing is configured", async () => {
    setUser("owner");
    const { getByTestId } = await renderSettingsOnKeysTab();
    expect(getByTestId("instagram-app-id-badge").textContent).toMatch(/ausente/i);
    expect(getByTestId("instagram-app-secret-badge").textContent).toMatch(/ausente/i);
  });

  it("shows 'configurado' badges + masked hint when already set", async () => {
    setUser("owner");
    mockUseInstagramAppStatus.mockReturnValue({
      data: {
        app_id_configured: true,
        app_secret_configured: true,
        app_id_masked: "5678****4321",
      },
      loading: false,
      refresh: mockRefreshInstagram,
    });
    const { getByTestId, getByText } = await renderSettingsOnKeysTab();
    expect(getByTestId("instagram-app-id-badge").textContent).toMatch(/configurado/i);
    expect(getByTestId("instagram-app-secret-badge").textContent).toMatch(/configurado/i);
    expect(getByText(/5678\*\*\*\*4321/)).toBeTruthy();
  });
});

describe("Settings — Instagram App save flow", () => {
  it("blocks submit and does not call save() when App ID is empty", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();
    fireEvent.click(getByTestId("instagram-app-save-btn"));
    expect(mockSaveInstagram).not.toHaveBeenCalled();
  });

  it("calls save() with app_id + app_secret and clears both fields after success", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();

    const appIdInput = getByTestId("instagram-app-id-input") as HTMLInputElement;
    const appSecretInput = getByTestId("instagram-app-secret-input") as HTMLInputElement;

    fireEvent.change(appIdInput, { target: { value: "1122334455" } });
    fireEvent.change(appSecretInput, { target: { value: "igsecret" } });
    fireEvent.click(getByTestId("instagram-app-save-btn"));

    await (await import("@testing-library/react")).waitFor(() => {
      expect(mockSaveInstagram).toHaveBeenCalledWith({
        app_id: "1122334455",
        app_secret: "igsecret",
      });
    });

    await (await import("@testing-library/react")).waitFor(() => {
      expect(appIdInput.value).toBe("");
      expect(appSecretInput.value).toBe("");
    });
    expect(mockRefreshInstagram).toHaveBeenCalled();
  });

  it("omits app_secret from the payload when left blank (keeps existing secret)", async () => {
    setUser("owner");
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByTestId("instagram-app-id-input"), {
      target: { value: "666777888" },
    });
    fireEvent.click(getByTestId("instagram-app-save-btn"));

    await (await import("@testing-library/react")).waitFor(() => {
      expect(mockSaveInstagram).toHaveBeenCalledWith({
        app_id: "666777888",
        app_secret: undefined,
      });
    });
  });
});

// ─── Per-client recipient scoping (migration 045) ───────────────────────────
// The requirement in the operator's words: "So João can have different
// recipient than One." These pin the two halves that make that true — the
// scope is visible and editable per row, and clearing it back to org-wide
// sends an explicit `null` rather than omitting the key (the backend
// distinguishes the two, so `undefined` here would silently no-op).

function stubRecipients(rows: unknown[], update = vi.fn()) {
  mockUseRecipients.mockReturnValue({
    data: rows, loading: false, create: vi.fn(), update, remove: vi.fn(),
  });
  return update;
}

const R_SCOPED = {
  id: "r1", name: "One contact", email: "one@x.com", whatsapp_number: null,
  is_active: true, client_id: "client-one", created_at: "2026-08-05T00:00:00Z",
};
const R_ORGWIDE = {
  id: "r2", name: "Fallback", email: "org@x.com", whatsapp_number: null,
  is_active: true, client_id: null, created_at: "2026-08-05T00:00:00Z",
};

describe("Settings — recipient client scoping", () => {
  it("shows each recipient's scope, defaulting to org-wide", async () => {
    setUser("admin");
    stubRecipients([R_SCOPED, R_ORGWIDE]);
    const { getByLabelText } = await renderSettingsOnKeysTab();

    expect((getByLabelText("Cliente de One contact") as HTMLSelectElement).value)
      .toBe("client-one");
    expect((getByLabelText("Cliente de Fallback") as HTMLSelectElement).value)
      .toBe("__org__");
  });

  it("scopes an org-wide recipient to a client", async () => {
    setUser("admin");
    const update = stubRecipients([R_ORGWIDE]);
    const { getByLabelText, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByLabelText("Cliente de Fallback"), {
      target: { value: "client-joao" },
    });
    expect(update).toHaveBeenCalledWith("r2", { client_id: "client-joao" });
  });

  it("clears a scope with an explicit null, never an omitted key", async () => {
    setUser("admin");
    const update = stubRecipients([R_SCOPED]);
    const { getByLabelText, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByLabelText("Cliente de One contact"), {
      target: { value: "__org__" },
    });
    // 🔴 null, never undefined. The backend uses `model_fields_set` to tell
    // "clear this" from "leave it alone", so an omitted key would no-op and a
    // recipient could never be returned to the org-wide tier.
    expect(update).toHaveBeenCalledWith("r1", { client_id: null });
  });
});
