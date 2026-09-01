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

// D16 (lead-card-hub): the clientes-inactivity tab. Defaults to the
// "never configured, using the platform default" shape so every OTHER
// suite in this file renders the tab without caring about it; the
// inactivity tests below override per-case.
const mockUseClientesInactivityConfig = vi.fn();
const mockSaveInactivity = vi.fn();

// Migration 079 — the document retention tab. Defaults to a two-row,
// nothing-customised shape so every OTHER suite in this file renders the tab
// without caring about it; the retention tests below override per-case.
const mockUseDocumentoRetencao = vi.fn();
const mockSaveRetencao = vi.fn();
const mockResetRetencao = vi.fn();

const mockUseCalendarStatus = vi.fn();
const mockFetchCalendarAuthUrl = vi.fn();

vi.mock("@/hooks/useSettings", () => ({
  useRecipients: mockUseRecipients,
  useKeysStatus: mockUseKeysStatus,
  useMetaAppStatus: mockUseMetaAppStatus,
  useSaveMetaApp: () => ({ save: mockSave, saving: false }),
  useInstagramAppStatus: mockUseInstagramAppStatus,
  useSaveInstagramApp: () => ({ save: mockSaveInstagram, saving: false }),
  useClientesInactivityConfig: mockUseClientesInactivityConfig,
  useSaveClientesInactivityConfig: () => ({
    mutate: mockSaveInactivity,
    isPending: false,
  }),
  useDocumentoRetencao: mockUseDocumentoRetencao,
  useSaveDocumentoRetencao: () => ({ mutate: mockSaveRetencao, isPending: false }),
  useResetDocumentoRetencao: () => ({ mutate: mockResetRetencao, isPending: false }),
  useCalendarStatus: mockUseCalendarStatus,
  fetchCalendarAuthUrl: mockFetchCalendarAuthUrl,
}));

// `useMarcas` calls TanStack's `useQuery` directly, so without a
// QueryClientProvider it throws for the whole tab. Mocked with the two real
// clients so the recipient scope selector has something to render.
vi.mock("@/hooks/useMarcas", () => ({
  useMarcas: () => ({
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

const RETENCAO_FGTS = {
  superficie: "atendimento" as const,
  tipo_documento: "extratos_fgts",
  retencao_dias: 730,
  padrao_dias: 730,
  personalizado: false,
  motivo: null,
  padrao_motivo: "Finalidade encerra na decisão do banco.",
  ancora: "encerramento" as const,
  ancora_rotulo: "a partir do encerramento do atendimento",
  atualizado_em: null,
  atualizado_por: null,
};

const RETENCAO_CONTRATO = {
  ...RETENCAO_FGTS,
  superficie: "cliente" as const,
  tipo_documento: "contrato",
  retencao_dias: 1825,
  padrao_dias: 1825,
  padrao_motivo: null,
  ancora: "envio" as const,
  ancora_rotulo: "a partir do envio do documento",
};

beforeEach(() => {
  mockUseCalendarStatus.mockReturnValue({
    data: {
      configured: false,
      adapter: "fake",
      account_email: null,
      default_calendar_id: null,
      default_timezone: "America/Sao_Paulo",
      consent_required: true,
    },
    loading: false,
    error: null,
    refresh: vi.fn(),
  });
  mockFetchCalendarAuthUrl.mockReset();
  mockFetchCalendarAuthUrl.mockResolvedValue("https://accounts.google.com/o/oauth2/auth?x=1");
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
  // The unconfigured shape — no org row, so the effective value IS the
  // platform default. Every suite in this file renders the whole page, so
  // this has to be a valid resolved state or unrelated tests fail on a tab
  // they do not care about.
  mockSaveRetencao.mockReset();
  mockResetRetencao.mockReset();
  mockUseDocumentoRetencao.mockReturnValue({
    data: { items: [RETENCAO_FGTS, RETENCAO_CONTRATO], total: 2 },
    loading: false,
    isError: false,
    refetch: vi.fn(),
  });
  mockUseClientesInactivityConfig.mockReturnValue({
    data: { threshold_days: 365, configured: false, default_threshold_days: 365 },
    loading: false,
    isError: false,
    refetch: vi.fn(),
  });
  mockSaveInactivity.mockReset();
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
  is_active: true, marca_id: "client-one", created_at: "2026-08-05T00:00:00Z",
};
const R_ORGWIDE = {
  id: "r2", name: "Fallback", email: "org@x.com", whatsapp_number: null,
  is_active: true, marca_id: null, created_at: "2026-08-05T00:00:00Z",
};

describe("Settings — recipient client scoping", () => {
  it("shows each recipient's scope, defaulting to org-wide", async () => {
    setUser("admin");
    stubRecipients([R_SCOPED, R_ORGWIDE]);
    const { getByLabelText } = await renderSettingsOnKeysTab();

    expect((getByLabelText("Marca de One contact") as HTMLSelectElement).value)
      .toBe("client-one");
    expect((getByLabelText("Marca de Fallback") as HTMLSelectElement).value)
      .toBe("__org__");
  });

  it("scopes an org-wide recipient to a client", async () => {
    setUser("admin");
    const update = stubRecipients([R_ORGWIDE]);
    const { getByLabelText, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByLabelText("Marca de Fallback"), {
      target: { value: "client-joao" },
    });
    expect(update).toHaveBeenCalledWith("r2", { marca_id: "client-joao" });
  });

  it("clears a scope with an explicit null, never an omitted key", async () => {
    setUser("admin");
    const update = stubRecipients([R_SCOPED]);
    const { getByLabelText, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByLabelText("Marca de One contact"), {
      target: { value: "__org__" },
    });
    // 🔴 null, never undefined. The backend uses `model_fields_set` to tell
    // "clear this" from "leave it alone", so an omitted key would no-op and a
    // recipient could never be returned to the org-wide tier.
    expect(update).toHaveBeenCalledWith("r1", { marca_id: null });
  });
});

// ─── Clientes inactivity threshold (D16) ─────────────────────────────────
// The three states here are NOT interchangeable and the UI is the only
// place a user can tell them apart:
//   · no org row      → the platform default applies, nobody chose it
//   · a configured N  → somebody chose N
//   · a configured 0  → somebody deliberately turned the sweep OFF
// Rendering 0 as an empty field, or "unconfigured" as a bare number, would
// each quietly misrepresent what the system is about to do to the board —
// and this sweep hides ~46% of clientes at the shipped default.
describe("Settings — clientes inactivity threshold", () => {
  function stubInactivity(over: Record<string, unknown>) {
    mockUseClientesInactivityConfig.mockReturnValue({
      data: { threshold_days: 365, configured: false, default_threshold_days: 365, ...over },
      loading: false,
      isError: false,
      refetch: vi.fn(),
    });
  }

  it("says the value is the platform default when the org never configured one", async () => {
    setUser("admin");
    stubInactivity({ configured: false, threshold_days: 365, default_threshold_days: 365 });
    const { getByTestId } = await renderSettingsOnKeysTab();

    expect(getByTestId("clientes-inactivity-status-badge").textContent).toContain(
      "padrao da plataforma"
    );
    expect(getByTestId("clientes-inactivity-status").textContent).toContain("365");
  });

  it("says 'personalizado' and shows the org's own number when configured", async () => {
    setUser("admin");
    stubInactivity({ configured: true, threshold_days: 45 });
    const { getByTestId } = await renderSettingsOnKeysTab();

    expect(getByTestId("clientes-inactivity-status-badge").textContent).toContain(
      "personalizado"
    );
    expect(getByTestId("clientes-inactivity-status").textContent).toContain("45");
  });

  it("renders 0 as an explicit 'desativado' state, never as an empty value", async () => {
    setUser("admin");
    stubInactivity({ configured: true, threshold_days: 0 });
    const { getByTestId } = await renderSettingsOnKeysTab();

    expect(getByTestId("clientes-inactivity-status-badge").textContent).toContain(
      "desativado"
    );
    // The distinguishing sentence — a blank field would be indistinguishable
    // from "not set", which is a DIFFERENT state with the opposite effect.
    expect(getByTestId("clientes-inactivity-status").textContent).toContain(
      "desativada"
    );
    // 0 is a real value and must round-trip into the editable field.
    expect((getByTestId("clientes-inactivity-input") as HTMLInputElement).value).toBe("0");
  });

  it("is read-only for a non-admin — no form, and it says why", async () => {
    setUser("member");
    stubInactivity({});
    const { getByTestId, queryByTestId } = await renderSettingsOnKeysTab();

    expect(queryByTestId("clientes-inactivity-form")).toBeNull();
    expect(getByTestId("clientes-inactivity-readonly-note")).toBeTruthy();
    // The current value is still VISIBLE to a non-admin — they need to know
    // why people are leaving the board even if they cannot change it.
    expect(getByTestId("clientes-inactivity-status")).toBeTruthy();
  });

  it("saves the typed threshold for an admin", async () => {
    setUser("admin");
    stubInactivity({ configured: true, threshold_days: 365 });
    const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.change(getByTestId("clientes-inactivity-input"), {
      target: { value: "540" },
    });
    fireEvent.submit(getByTestId("clientes-inactivity-form"));

    // `mutate(value, { onSuccess })` — the second arg is how the component
    // clears its dirty flag once the server confirms, so assert the VALUE
    // and that a success callback was supplied, rather than pinning the
    // exact options object.
    expect(mockSaveInactivity).toHaveBeenCalledTimes(1);
    const [value, opts] = mockSaveInactivity.mock.calls[0];
    expect(value).toBe(540);
    expect(typeof (opts as any)?.onSuccess).toBe("function");
  });
});

// ─── Document retention tab (migration 079) ─────────────────────────────
describe("Settings — document retention policy", () => {
  function stubRetencao(items: unknown[]) {
    mockUseDocumentoRetencao.mockReturnValue({
      data: { items, total: items.length },
      loading: false,
      isError: false,
      refetch: vi.fn(),
    });
  }

  it("names the document in Portuguese, with the slug kept as a subtitle", async () => {
    // The slug is what the API and the storage path call it, so it stays
    // visible — but a settings screen that shows ONLY `extratos_fgts` is the
    // same defect as the imóvel filters showing `Cozinhaplanejada`.
    setUser("owner");
    const { getByTestId } = await renderSettingsOnKeysTab();

    const linha = getByTestId("retencao-row-atendimento-extratos_fgts");
    expect(linha.textContent).toContain("Extratos do FGTS");
    expect(linha.textContent).toContain("extratos_fgts");
  });

  it("always shows what the countdown starts from, not just a duration", async () => {
    // 🔴 The point of the tab. "730 dias" alone is ambiguous — counted from
    // the upload and from the deal's close it is years apart, and only the
    // second is what Lei 9.613/98 art. 10 III means.
    setUser("owner");
    const { getByTestId } = await renderSettingsOnKeysTab();

    const linha = getByTestId("retencao-row-atendimento-extratos_fgts");
    expect(linha.textContent).toContain("a partir do encerramento do atendimento");

    const cliente = getByTestId("retencao-row-cliente-contrato");
    expect(cliente.textContent).toContain("a partir do envio do documento");
  });

  it("renders a null retention as 'Indefinidamente', never as a blank", async () => {
    setUser("owner");
    stubRetencao([{ ...RETENCAO_FGTS, retencao_dias: null, personalizado: true }]);
    const { getByTestId } = await renderSettingsOnKeysTab();

    expect(
      getByTestId("retencao-row-atendimento-extratos_fgts").textContent
    ).toContain("Indefinidamente");
  });

  it("marks an org override and shows the default it replaced", async () => {
    setUser("owner");
    stubRetencao([{ ...RETENCAO_FGTS, retencao_dias: 365, personalizado: true }]);
    const { getByTestId } = await renderSettingsOnKeysTab();

    const linha = getByTestId("retencao-row-atendimento-extratos_fgts");
    expect(linha.textContent).toContain("personalizado");
    expect(linha.textContent).toContain("Padrão da plataforma");
    expect(linha.textContent).toContain("730");
  });

  it("hides every control from a non-admin", async () => {
    // Read stays open — a corretor should be able to look up how long we keep
    // a buyer's income tax return — but nothing on screen offers to change it.
    setUser("member");
    const { getByTestId } = await renderSettingsOnKeysTab();

    const linha = getByTestId("retencao-row-atendimento-extratos_fgts");
    expect(linha.textContent).toContain("730");
    expect(linha.textContent).not.toContain("Alterar");
  });

  it("saves the typed number for the right surface and type", async () => {
    setUser("owner");
    const { getByTestId, getByLabelText, fireEvent } =
      await renderSettingsOnKeysTab();

    fireEvent.click(getByTestId("retencao-alterar-extratos_fgts"));
    fireEvent.change(getByLabelText(/Retenção em dias para Extratos do FGTS/), {
      target: { value: "365" },
    });
    fireEvent.click(getByTestId("retencao-salvar-extratos_fgts"));

    expect(mockSaveRetencao).toHaveBeenCalledTimes(1);
    expect(mockSaveRetencao.mock.calls[0][0]).toEqual({
      superficie: "atendimento",
      tipo_documento: "extratos_fgts",
      retencao_dias: 365,
    });
  });

  it("refuses a zero or negative value without calling save", async () => {
    // Zero is falsy and the upload path reads `if retencao_dias` — it would
    // show as a policy on screen while behaving as no clock at all.
    setUser("owner");
    const { getByTestId, getByLabelText, fireEvent } =
      await renderSettingsOnKeysTab();

    fireEvent.click(getByTestId("retencao-alterar-extratos_fgts"));
    fireEvent.change(getByLabelText(/Retenção em dias para Extratos do FGTS/), {
      target: { value: "0" },
    });
    fireEvent.click(getByTestId("retencao-salvar-extratos_fgts"));

    expect(mockSaveRetencao).not.toHaveBeenCalled();
  });

  it("restores the platform default from the override row", async () => {
    setUser("owner");
    stubRetencao([{ ...RETENCAO_FGTS, retencao_dias: 365, personalizado: true }]);
    const { getByLabelText, fireEvent } = await renderSettingsOnKeysTab();

    fireEvent.click(getByLabelText("Restaurar o padrão de Extratos do FGTS"));

    expect(mockResetRetencao).toHaveBeenCalledWith({
      superficie: "atendimento",
      tipo_documento: "extratos_fgts",
    });
  });
});

// ── Google Calendar connection ──────────────────────────────────────────────
// `/api/calendar/status` + `/oauth/start` shipped with no UI: no way to see
// whether consent had been given, and no way to give it.

describe("Settings — Google Calendar", () => {
  it("shows the adapter and offers connect when consent is required", async () => {
    const { getByTestId } = await renderSettingsOnKeysTab();
    expect(getByTestId("calendar-status").textContent).toContain("fake");
    expect(getByTestId("calendar-connect")).toBeTruthy();
  });

  it("hides the connect button once consent is not required", async () => {
    mockUseCalendarStatus.mockReturnValue({
      data: {
        configured: true,
        adapter: "oauth",
        account_email: "agenda@exemplo.com",
        default_calendar_id: "primary",
        default_timezone: "America/Sao_Paulo",
        consent_required: false,
      },
      loading: false,
      error: null,
      refresh: vi.fn(),
    });
    const { getByTestId, queryByTestId } = await renderSettingsOnKeysTab();
    expect(getByTestId("calendar-status").textContent).toContain("agenda@exemplo.com");
    expect(queryByTestId("calendar-connect")).toBeNull();
  });

  it("opens the consent URL in a new tab rather than navigating the SPA", async () => {
    const open = vi.fn();
    const original = window.open;
    (window as any).open = open;
    try {
      const { getByTestId, fireEvent } = await renderSettingsOnKeysTab();
      fireEvent.click(getByTestId("calendar-connect"));
      await new Promise((r) => setTimeout(r, 0));
      expect(mockFetchCalendarAuthUrl).toHaveBeenCalled();
      expect(open).toHaveBeenCalledWith(
        "https://accounts.google.com/o/oauth2/auth?x=1",
        "_blank",
        "noopener,noreferrer",
      );
    } finally {
      (window as any).open = original;
    }
  });

  it("surfaces a status error instead of a blank card", async () => {
    mockUseCalendarStatus.mockReturnValue({
      data: null,
      loading: false,
      error: "Falha ao consultar o status do calendário.",
      refresh: vi.fn(),
    });
    const { getByTestId } = await renderSettingsOnKeysTab();
    expect(getByTestId("calendar-error")).toBeTruthy();
  });
});
