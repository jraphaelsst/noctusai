/**
 * Settings hooks — thin TanStack-Query wrappers over the /api/settings/*
 * endpoints. Splits each tab into its own hook so a slow API key check
 * doesn't block a tab from rendering.
 *
 * NOTE: useYouTubeStatus was removed — YouTube connections are now managed
 * in the unified Conexoes page via useIntegrationAccounts.
 */
import { useEffect, useState, useCallback } from "react";
import { api } from "@noctusai/seed/infra";
import { toast } from "sonner";

// ─── Types (mirror backend schemas) ─────────────────────────────────────
export interface Recipient {
  id: string;
  name: string;
  email?: string | null;
  whatsapp_number?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface RecipientCreate {
  name: string;
  email?: string;
  whatsapp_number?: string;
  is_active?: boolean;
}

export interface RecipientUpdate {
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
