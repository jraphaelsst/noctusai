/**
 * Settings hooks — thin TanStack-Query wrappers over the /api/settings/*
 * endpoints. Splits each tab into its own hook so a slow API key check
 * doesn't block a tab from rendering.
 *
 * NOTE: useYouTubeStatus was removed — YouTube connections are now managed
 * in the unified Conexoes page via useIntegrationAccounts.
 */
import { useEffect, useState, useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@noctusai/seed/infra";
import { toast } from "sonner";

// ─── Types (mirror backend schemas) ─────────────────────────────────────
export interface Recipient {
  id: string;
  name: string;
  email?: string | null;
  whatsapp_number?: string | null;
  is_active: boolean;
  /**
   * Client this recipient is scoped to. `null` = ORG-WIDE: the fallback tier
   * that hears about anything not attributed to a specific client. Leads whose
   * Meta Page maps to no client land here, so an empty org tier means those
   * leads alert nobody.
   */
  marca_id?: string | null;
  created_at: string;
}

export interface RecipientCreate {
  name: string;
  email?: string;
  whatsapp_number?: string;
  is_active?: boolean;
  /** Omit or send null for an org-wide recipient. */
  marca_id?: string | null;
}

export interface RecipientUpdate {
  /**
   * Send an explicit `null` to clear the scope back to org-wide; OMIT the key
   * to leave it unchanged. The backend distinguishes the two via
   * `model_fields_set`, so `undefined` and `null` are NOT interchangeable here.
   */
  marca_id?: string | null;
  name?: string;
  email?: string | null;
  whatsapp_number?: string | null;
  is_active?: boolean;
}

export type KeyHealth = "configured" | "missing";

export interface KeyStatusEntry {
  label: string;
  health: KeyHealth;
  description: string;
}

export interface KeysStatus {
  youtube_client_id: KeyStatusEntry;
  youtube_client_secret: KeyStatusEntry;
  youtube_redirect_uri: KeyStatusEntry;
  frontend_base_url: KeyStatusEntry;
  encryption_key: KeyStatusEntry;
  smtp_user: KeyStatusEntry;
  smtp_password: KeyStatusEntry;
  waha_base_url: KeyStatusEntry;
  waha_api_key: KeyStatusEntry;
  waha_webhook_hmac_secret: KeyStatusEntry;
  vista_base_url: KeyStatusEntry;
  vista_api_key: KeyStatusEntry;
  database_backend: KeyStatusEntry;
  supabase_url: KeyStatusEntry;
  supabase_service_role_key: KeyStatusEntry;
}

// ─── Meta App credentials (admin/dev only) ──────────────────────────────
export interface MetaAppStatus {
  app_id_configured: boolean;
  app_secret_configured: boolean;
  app_id_masked?: string | null;
}

export interface MetaAppSave {
  app_id: string;
  /** Omit to keep the currently stored secret unchanged. */
  app_secret?: string;
}

// ─── Instagram App credentials (admin/dev only) ─────────────────────────
// Same shape as Meta App — a distinct Instagram Business Login app (its own
// App ID/Secret, separate from the Facebook app id + the "Token de Cliente").
export interface InstagramAppStatus {
  app_id_configured: boolean;
  app_secret_configured: boolean;
  app_id_masked?: string | null;
}

export interface InstagramAppSave {
  app_id: string;
  /** Omit to keep the currently stored secret unchanged. */
  app_secret?: string;
}

// ─── Recipients tab ─────────────────────────────────────────────────────
export function useRecipients() {
  const [data, setData] = useState<Recipient[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.get<Recipient[]>("/api/settings/recipients");
      setData(list);
    } catch (err) {
      console.error("recipients load failed", err);
      toast.error("Falha ao carregar destinatarios");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (payload: RecipientCreate) => {
    try {
      await api.post("/api/settings/recipients", payload);
      toast.success("Destinatario adicionado");
      await refresh();
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao adicionar destinatario");
      throw err;
    }
  }, [refresh]);

  const update = useCallback(async (id: string, payload: RecipientUpdate) => {
    try {
      await api.put(`/api/settings/recipients/${id}`, payload);
      await refresh();
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao atualizar destinatario");
    }
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    try {
      await api.delete(`/api/settings/recipients/${id}`);
      toast.success("Destinatario removido");
      await refresh();
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao remover destinatario");
    }
  }, [refresh]);

  return { data, loading, create, update, remove, refresh };
}

// ─── API Keys tab ───────────────────────────────────────────────────────
export function useKeysStatus() {
  const [data, setData] = useState<KeysStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const status = await api.get<KeysStatus>("/api/settings/keys/status");
        setData(status);
      } catch (err) {
        console.error("keys status load failed", err);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return { data, loading };
}

// ─── Google Calendar connection ─────────────────────────────────────────
/**
 * `GET /api/calendar/status` — which adapter the factory would build today.
 *
 * The calendar routes shipped with no UI at all, so an operator had no way to
 * see whether Google consent had been given, nor to give it. `adapter: "fake"`
 * with `consent_required` means the OAuth client is configured but nobody has
 * consented yet — exactly the state the connect button exists for.
 */
export interface CalendarStatus {
  configured: boolean;
  adapter: string;
  account_email: string | null;
  default_calendar_id: string | null;
  default_timezone: string | null;
  consent_required: boolean;
}

export function useCalendarStatus() {
  const [data, setData] = useState<CalendarStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<CalendarStatus>("/api/calendar/status"));
    } catch (err: any) {
      setError(err?.message ?? "Falha ao consultar o status do calendário.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}

/**
 * Fetch the Google consent URL without following the redirect.
 *
 * `redirect_to_consent=false` is what makes this usable from a SPA — the
 * default 302 would be opaque to fetch. Returns `auth_url` for the caller to
 * open, so the browser (not the XHR) performs the navigation.
 */
export async function fetchCalendarAuthUrl(): Promise<string> {
  const res = await api.get<{ auth_url: string }>(
    "/api/calendar/oauth/start?redirect_to_consent=false",
  );
  return res.auth_url;
}

// ─── Meta App credentials tab ───────────────────────────────────────────
/**
 * useMetaAppStatus — GET /api/settings/meta-app/status.
 *
 * Never returns the secret itself — only booleans + an optional masked
 * app_id for display. Exposes `refresh()` so the save form can re-fetch
 * status after a successful write.
 */
export function useMetaAppStatus() {
  const [data, setData] = useState<MetaAppStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await api.get<MetaAppStatus>("/api/settings/meta-app/status");
      setData(status);
    } catch (err) {
      console.error("meta-app status load failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, refresh };
}

/**
 * useSaveMetaApp — PUT /api/settings/meta-app.
 *
 * `app_secret` is write-only: omit it to keep the currently stored value
 * (backend never echoes it back). Callers should clear their local secret
 * field after a successful save — never re-display what was typed.
 */
export function useSaveMetaApp() {
  const [saving, setSaving] = useState(false);

  const save = useCallback(async (payload: MetaAppSave) => {
    setSaving(true);
    try {
      await api.put("/api/settings/meta-app", payload);
      toast.success("Credenciais do Meta App salvas.");
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao salvar credenciais do Meta App.");
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  return { save, saving };
}

// ─── Clientes inactivity threshold tab (D16, roadmap lead-card-hub-2026-08) ─
// Unlike the sibling hooks above, this pair uses TanStack Query directly
// (matches the newer hooks in this product — e.g. `useOlxLeads.ts`) rather
// than the manual useState/useEffect shape, precisely so the loading gate
// below can be honest.
export interface ClientesInactivityConfig {
  /** The EFFECTIVE threshold — either the org's own configured value, or
   * `default_threshold_days` when `configured` is false. `0` is a real,
   * deliberate value: the org explicitly disabled the sweep — never
   * render it as an empty/blank field. */
  threshold_days: number;
  /** `false` = no org row exists yet; `threshold_days` is the platform
   * default, not something anyone chose. `true` = an org admin set this
   * value explicitly (including explicitly setting it to 0). */
  configured: boolean;
  /** The platform-wide fallback (`app/config.py`'s
   * `clientes_inactivity_threshold_days_default`) — shown so the UI can
   * say "usando o padrão da plataforma (N dias)" instead of a bare number
   * with no context. */
  default_threshold_days: number;
}

export const CLIENTES_INACTIVITY_KEY = ["settings", "clientes-inactivity"] as const;

/**
 * useClientesInactivityConfig — GET /api/settings/clientes-inactivity.
 * Open to any authenticated org member (read is not admin-gated on the
 * backend — only the write is); see `settings_router.py`'s header comment
 * on that split.
 *
 * 🔴 Loading is gated on `isPending || isFetching`, never `isLoading`.
 * Under TanStack v5, `isLoading` is false during a background refetch, so
 * gating on it alone would let a stale/empty branch render over an
 * already-resolved value — this product shipped exactly that bug once
 * already (`check_lying_loading_state`).
 */
export function useClientesInactivityConfig() {
  const query = useQuery({
    queryKey: CLIENTES_INACTIVITY_KEY,
    queryFn: () =>
      api.get<ClientesInactivityConfig>("/api/settings/clientes-inactivity"),
  });
  return {
    ...query,
    loading: query.isPending || query.isFetching,
  };
}

/**
 * useSaveClientesInactivityConfig — PUT /api/settings/clientes-inactivity.
 * Admin-gated on the backend (owner/admin org role) — callers must check
 * that themselves before rendering the form (see `Settings.tsx`); a
 * non-admin submit here would just surface the 403 as a toast, which is
 * exactly the outcome the UI is meant to avoid by not showing the form.
 */
export function useSaveClientesInactivityConfig() {
  const qc = useQueryClient();
  return useMutation<ClientesInactivityConfig, unknown, number>({
    mutationFn: (threshold_days) =>
      api.put<ClientesInactivityConfig>("/api/settings/clientes-inactivity", {
        threshold_days,
      }),
    onSuccess: (data) => {
      qc.setQueryData(CLIENTES_INACTIVITY_KEY, data);
      toast.success("Limite de inatividade de clientes atualizado.");
    },
    onError: (err: any) => {
      toast.error(
        err?.message ?? "Falha ao salvar o limite de inatividade de clientes."
      );
    },
  });
}

// ─── Document retention policy tab (migration 079) ──────────────────────
/** One document type's retention policy for this org. */
export interface DocumentoRetencaoPolitica {
  /** Which document surface this type belongs to. `imovel` is absent on
   * purpose — `imovel_documentos` has no retention clock (a matrícula is a
   * public registry document about a property, not personal data). */
  superficie: "cliente" | "atendimento";
  tipo_documento: string;
  /** The EFFECTIVE value. `null` means "manter indefinidamente" — a real
   * policy, not a missing value, and it must never render as a blank field. */
  retencao_dias: number | null;
  /** The platform default this may be overriding. Shown next to the
   * effective value so "5 anos (padrão: 10 anos)" is one request, not two. */
  padrao_dias: number | null;
  /** `true` = this org set its own value; `false` = showing the default. */
  personalizado: boolean;
  motivo: string | null;
  padrao_motivo: string | null;
  /** What the countdown starts from. Without this a duration is ambiguous —
   * "5 anos" from the upload and from the deal's close are years apart. */
  ancora: "envio" | "encerramento";
  ancora_rotulo: string;
  atualizado_em: string | null;
  atualizado_por: string | null;
}

export interface DocumentoRetencaoLista {
  items: DocumentoRetencaoPolitica[];
  total: number;
}

export const DOCUMENTO_RETENCAO_KEY = ["settings", "documento-retencao"] as const;

/**
 * useDocumentoRetencao — GET /api/settings/documento-retencao.
 * Read is open to any authenticated org member; only the write is
 * admin-gated (same split every other org config on this router uses).
 *
 * 🔴 `loading` gates on `isPending || isFetching`, never `isLoading`.
 */
export function useDocumentoRetencao() {
  const query = useQuery({
    queryKey: DOCUMENTO_RETENCAO_KEY,
    queryFn: () =>
      api.get<DocumentoRetencaoLista>("/api/settings/documento-retencao"),
  });
  return { ...query, loading: query.isPending || query.isFetching };
}

export interface DocumentoRetencaoSave {
  superficie: "cliente" | "atendimento";
  tipo_documento: string;
  retencao_dias: number | null;
  motivo?: string | null;
}

/**
 * useSaveDocumentoRetencao — PUT /api/settings/documento-retencao.
 * Admin-gated on the backend. Returns the WHOLE list, which is written
 * straight into the cache — a partial response would leave the screen
 * reconciling rows by hand.
 */
export function useSaveDocumentoRetencao() {
  const qc = useQueryClient();
  return useMutation<DocumentoRetencaoLista, unknown, DocumentoRetencaoSave>({
    mutationFn: (body) =>
      api.put<DocumentoRetencaoLista>("/api/settings/documento-retencao", body),
    onSuccess: (data) => {
      qc.setQueryData(DOCUMENTO_RETENCAO_KEY, data);
      toast.success("Política de retenção atualizada.");
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao salvar a política de retenção.");
    },
  });
}

/**
 * useResetDocumentoRetencao — DELETE /api/settings/documento-retencao.
 * Drops this org's override so the platform default applies again.
 */
export function useResetDocumentoRetencao() {
  const qc = useQueryClient();
  return useMutation<
    DocumentoRetencaoLista,
    unknown,
    { superficie: string; tipo_documento: string }
  >({
    mutationFn: ({ superficie, tipo_documento }) =>
      api.delete<DocumentoRetencaoLista>(
        `/api/settings/documento-retencao?superficie=${encodeURIComponent(
          superficie
        )}&tipo_documento=${encodeURIComponent(tipo_documento)}`
      ),
    onSuccess: (data) => {
      qc.setQueryData(DOCUMENTO_RETENCAO_KEY, data);
      toast.success("Padrão da plataforma restaurado.");
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao restaurar o padrão.");
    },
  });
}

// ─── Instagram App credentials tab ──────────────────────────────────────
/**
 * useInstagramAppStatus — GET /api/settings/instagram-app/status.
 *
 * Mirrors useMetaAppStatus: never returns the secret itself — only booleans
 * + an optional masked app_id for display. Exposes `refresh()` so the save
 * form can re-fetch status after a successful write.
 */
export function useInstagramAppStatus() {
  const [data, setData] = useState<InstagramAppStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const status = await api.get<InstagramAppStatus>(
        "/api/settings/instagram-app/status"
      );
      setData(status);
    } catch (err) {
      console.error("instagram-app status load failed", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, refresh };
}

/**
 * useSaveInstagramApp — PUT /api/settings/instagram-app.
 *
 * Mirrors useSaveMetaApp: `app_secret` is write-only — omit it to keep the
 * currently stored value (backend never echoes it back). Callers should
 * clear their local secret field after a successful save.
 */
export function useSaveInstagramApp() {
  const [saving, setSaving] = useState(false);

  const save = useCallback(async (payload: InstagramAppSave) => {
    setSaving(true);
    try {
      await api.put("/api/settings/instagram-app", payload);
      toast.success("Credenciais do Instagram App salvas.");
    } catch (err: any) {
      toast.error(err?.message ?? "Falha ao salvar credenciais do Instagram App.");
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  return { save, saving };
}

// ─── API keys tab — operator-settable, encrypted at rest ────────────────
// Additive to `useKeysStatus` above: that one is the read-only health view
// of the DEPLOYMENT's .env. These three keys are set by the operator here,
// Fernet-encrypted into `social_wiring.credentials`, and read back by the
// certidões / matrículas workflows.

/** Which tier answered. `local` = this product's encrypted store. */
export type ApiKeySource = "local" | "platform" | "env";

export interface ApiKeyOption {
  value: string;
  label: string;
  description: string;
}

export interface ApiKeyStatus {
  key: string;
  label: string;
  description: string;
  is_secret: boolean;
  testable: boolean;
  input_type: string;
  placeholder: string;
  configured: boolean;
  /**
   * Non-empty makes this a CHOICE, not a free-text key: render a switch
   * over these instead of an input. Empty for every ordinary key, so this
   * array alone is the branch.
   *
   * Optional because a deploy is not atomic: a cached SPA bundle can talk
   * to an older API (or the reverse) for a few minutes, and a hard read of
   * `.length` there takes down the whole Settings page. Read it through
   * `apiKeyOptions()`.
   */
  options?: ApiKeyOption[];
  /**
   * What the product behaves as when the setting was never saved — what
   * the switch shows as selected in that case, so an unconfigured control
   * still reflects what will actually happen.
   */
  default?: string | null;
  /**
   * Display-only. Last 4 characters for a secret (`...b3f9`); the value in
   * full for a non-secret (an e-mail). NEVER the secret itself — the
   * backend does not have an endpoint that returns one.
   */
  hint: string | null;
  /**
   * `null` = configured nowhere. A non-`local` source after a removal is
   * why the UI can say "ainda ativa pela plataforma" instead of lying that
   * the key is gone.
   */
  source: ApiKeySource | null;
  /** Only ever set for the `local` tier. */
  updated_at: string | null;
}

export interface ApiKeysStatus {
  items: ApiKeyStatus[];
  total: number;
}

export interface ApiKeyTestResult {
  key: string;
  success: boolean;
  /** pt-BR, operator-facing — render verbatim. */
  message: string;
}

export const API_KEYS_QUERY_KEY = ["settings", "api-keys"] as const;

/**
 * useApiKeys — GET /api/settings/api-keys.
 *
 * Read is open to any authenticated org member; only writes are
 * admin-gated (the same split every other org config on this router uses).
 *
 * 🔴 TWO loading signals, never `isLoading` and never a bare `isFetching`:
 * `showSkeleton` is true only on the FIRST load (nothing to show yet), and
 * `isRefreshing` is the quiet indicator for a refetch over data that is
 * already on screen. Gating the card on `isFetching` alone would blank a
 * populated list every time a save invalidates it.
 */
export function useApiKeys() {
  const query = useQuery({
    queryKey: API_KEYS_QUERY_KEY,
    queryFn: () => api.get<ApiKeysStatus>("/api/settings/api-keys"),
  });
  return {
    ...query,
    showSkeleton: query.isPending && !query.data,
    isRefreshing: query.isFetching && !!query.data,
  };
}

export interface ApiKeySave {
  key: string;
  value: string;
}

/**
 * useSaveApiKey — PUT /api/settings/api-keys/{key}.
 *
 * Write-only: the backend never echoes the value back, so the caller's
 * input must be cleared on success rather than re-populated from the
 * response. Admin-gated on the backend — callers check the role before
 * rendering the controls (a non-admin submit would only surface a 403).
 */
export function useSaveApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyStatus, unknown, ApiKeySave>({
    mutationFn: ({ key, value }) =>
      api.put<ApiKeyStatus>(
        `/api/settings/api-keys/${encodeURIComponent(key)}`,
        { value }
      ),
    onSuccess: (data) => {
      toast.success(`${data.label} salva com sucesso.`);
      void qc.invalidateQueries({ queryKey: API_KEYS_QUERY_KEY });
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao salvar a chave.");
    },
  });
}

/**
 * useRemoveApiKey — DELETE /api/settings/api-keys/{key}.
 *
 * Drops this org's LOCAL override only. The response is the RE-RESOLVED
 * status, so when the platform/env tier still answers the toast says the
 * key is still active instead of claiming it was removed — an operator
 * told "removida" over a live key stops looking for the real source.
 */
export function useRemoveApiKey() {
  const qc = useQueryClient();
  return useMutation<ApiKeyStatus, unknown, string>({
    mutationFn: (key) =>
      api.delete<ApiKeyStatus>(
        `/api/settings/api-keys/${encodeURIComponent(key)}`
      ),
    onSuccess: (data) => {
      if (data.configured) {
        toast.success(
          `${data.label}: override local removido — ainda configurada fora deste produto.`
        );
      } else {
        toast.success(`${data.label} removida.`);
      }
      void qc.invalidateQueries({ queryKey: API_KEYS_QUERY_KEY });
    },
    onError: (err: any) => {
      toast.error(err?.message ?? "Falha ao remover a chave.");
    },
  });
}

/**
 * useTestApiKey — POST /api/settings/api-keys/{key}/test.
 *
 * Probes the value the WORKFLOWS would resolve (same two-tier chain), so a
 * green result means this org's certidões run will work — not that some key
 * somewhere is valid. A failed probe is a normal outcome, not an exception:
 * it comes back `success: false` with a pt-BR message to render inline.
 */
export function useTestApiKey() {
  return useMutation<ApiKeyTestResult, unknown, string>({
    mutationFn: (key) =>
      api.post<ApiKeyTestResult>(
        `/api/settings/api-keys/${encodeURIComponent(key)}/test`,
        {}
      ),
    onSuccess: (data) => {
      if (data.success) toast.success(data.message);
      else toast.error("Teste falhou", { description: data.message });
    },
    onError: (err: any) => {
      toast.error("Teste falhou", {
        description: err?.message ?? "Erro desconhecido.",
      });
    },
  });
}
