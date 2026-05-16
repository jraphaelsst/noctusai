/**
 * WhatsApp connection-admin + intake-monitor hooks for NoctusAI products.
 *
 * Two seed hook factories, same injection pattern as `createLLMHooks`
 * (the product passes its own authenticated `createApiClient()`):
 *
 * - `createWhatsAppConnectionHooks` wraps the `whatsapp_admin` standard
 *   router (`/api/whatsapp/connection/*`) — any WhatsApp-chatbot product
 *   gets the whole pairing UX (live status, QR scan, restart, logout,
 *   webhook wiring).
 * - `createWhatsAppIntakeHooks` wraps the intake/flow-monitor router
 *   (`/api/whatsapp/intake/conversations*`) — a read-only live window
 *   into WhatsApp conversation state + recent message history, plus the
 *   "cancel stuck flow" action.
 *
 * Presentation (pt-BR labels, cards, polling cadence overrides) stays in
 * the product; this module is locale-agnostic.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApiClient } from './api';

// ---------------------------------------------------------------------------
// Connection types — mirror the backend DTOs (whatsapp_admin_router.py)
// ---------------------------------------------------------------------------

export interface WhatsAppConnection {
  configured: boolean;
  status: string | null;
  paired: boolean;
  me_id: string | null;
  me_name: string | null;
  session: string;
  error: string | null;
}

export interface WhatsAppQr {
  scannable: boolean;
  status: string | null;
  png_base64: string | null;
}

export interface WhatsAppWebhookResult {
  ok: boolean;
  url: string;
  events: string[];
  status: string | null;
}

export interface ConfigureWebhookBody {
  url: string;
  events?: string[];
}

// ---------------------------------------------------------------------------
// Intake-monitor types — mirror the backend DTOs (intake_monitor_router.py:
// IntakeConversationDTO / IntakeMessageDTO / IntakeConversationDetailDTO /
// IntakeCancelResult)
// ---------------------------------------------------------------------------

export interface IntakeConversation {
  session_id: string;
  state: string;
  product_code: string | null;
  drive_url: string | null;
  video_filename: string | null;
  video_format: string | null;
  candidate_count: number;
  active_uploads: number;
}

export interface IntakeMessage {
  direction: string;
  body: string;
  created_at: string | null;
  provider_message_id: string | null;
}

export interface IntakeConversationDetail {
  conversation: IntakeConversation;
  messages: IntakeMessage[];
}

export interface IntakeCancelResult {
  session_id: string;
  cleared: boolean;
}

// ---------------------------------------------------------------------------
// Connection hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export function createWhatsAppConnectionHooks(api: ApiClient) {
  const KEY = ['whatsapp', 'connection'] as const;

  /**
   * Live session status. Polls while not paired so the UI reflects the
   * QR→pairing→WORKING transition without a manual refresh; backs off
   * once paired (status is then stable).
   */
  function useWhatsAppConnection(options?: { pollMs?: number }) {
    return useQuery<WhatsAppConnection>({
      queryKey: KEY,
      queryFn: () => api.get('/api/whatsapp/connection'),
      refetchInterval: (query) => {
        const data = query.state.data as WhatsAppConnection | undefined;
        if (data?.paired) return false;
        return options?.pollMs ?? 5000;
      },
    });
  }

  /**
   * QR image (base64 PNG). Polls while the session is scannable so a
   * rotated QR refreshes; stops once a scan completes (scannable false).
   */
  function useWhatsAppQr(enabled: boolean, options?: { pollMs?: number }) {
    return useQuery<WhatsAppQr>({
      queryKey: [...KEY, 'qr'],
      queryFn: () => api.get('/api/whatsapp/connection/qr'),
      enabled,
      refetchInterval: (query) => {
        const data = query.state.data as WhatsAppQr | undefined;
        if (data && !data.scannable) return false;
        return options?.pollMs ?? 8000;
      },
    });
  }

  function useWhatsAppActions() {
    const qc = useQueryClient();
    const invalidate = () => {
      qc.invalidateQueries({ queryKey: KEY });
    };

    const useRestart = () =>
      useMutation<WhatsAppConnection>({
        mutationFn: () => api.post('/api/whatsapp/connection/restart'),
        onSuccess: invalidate,
      });

    const useLogout = () =>
      useMutation<WhatsAppConnection>({
        mutationFn: () => api.post('/api/whatsapp/connection/logout'),
        onSuccess: invalidate,
      });

    const useConfigureWebhook = () =>
      useMutation<WhatsAppWebhookResult, unknown, ConfigureWebhookBody>({
        mutationFn: (body) =>
          api.post('/api/whatsapp/connection/webhook', body),
        onSuccess: invalidate,
      });

    return { useRestart, useLogout, useConfigureWebhook };
  }

  return { useWhatsAppConnection, useWhatsAppQr, useWhatsAppActions };
}

// ---------------------------------------------------------------------------
// Intake-monitor hook factory — takes an api client, returns bound hooks
// ---------------------------------------------------------------------------

export function createWhatsAppIntakeHooks(api: ApiClient) {
  const KEY = ['whatsapp', 'intake'] as const;

  /**
   * Live conversation list. Polls so the monitor stays current without a
   * manual refresh; the backend already orders non-idle states first.
   */
  function useIntakeConversations(options?: { pollMs?: number }) {
    return useQuery<IntakeConversation[]>({
      queryKey: [...KEY, 'conversations'],
      queryFn: () => api.get('/api/whatsapp/intake/conversations'),
      refetchInterval: options?.pollMs ?? 5000,
    });
  }

  /**
   * One conversation's live state + recent message history. Only enabled
   * when a session is selected; polls so an in-flight flow stays current.
   */
  function useIntakeConversation(
    sessionId: string | null,
    options?: { pollMs?: number },
  ) {
    return useQuery<IntakeConversationDetail>({
      queryKey: [...KEY, 'conversation', sessionId],
      queryFn: () =>
        api.get(
          `/api/whatsapp/intake/conversations/${encodeURIComponent(
            sessionId ?? '',
          )}`,
        ),
      enabled: !!sessionId,
      refetchInterval: options?.pollMs ?? 5000,
    });
  }

  function useCancelConversation() {
    const qc = useQueryClient();
    return useMutation<IntakeCancelResult, unknown, string>({
      mutationFn: (sessionId) =>
        api.post(
          `/api/whatsapp/intake/conversations/${encodeURIComponent(
            sessionId,
          )}/cancel`,
        ),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: KEY });
      },
    });
  }

  return {
    useIntakeConversations,
    useIntakeConversation,
    useCancelConversation,
  };
}
