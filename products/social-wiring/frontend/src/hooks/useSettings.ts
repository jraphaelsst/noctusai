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
