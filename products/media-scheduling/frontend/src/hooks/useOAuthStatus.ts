/**
 * useOAuthStatus — Google Calendar OAuth status hook.
 *
 * Reads connection state + token expiry from backend; provides a `redirectToInit`
 * helper that initiates the OAuth handshake on the backend.
 *
 * TODO Phase 3 — confirm endpoint paths
 *   GET  `/api/oauth/google/status` → { connected: boolean, expires_at?: string, account_email?: string }
 *   GET  `/oauth/google/init`       → 302 to Google consent screen
 */
import { useQuery } from "@tanstack/react-query";
import { api, useAuthStore } from "@noctusai/seed/infra";

export interface OAuthStatus {
  connected: boolean;
  /** ISO datetime — when the access token expires. */
  expires_at?: string | null;
  /** Email of the connected Google account, if any. */
  account_email?: string | null;
  /** Free-form last-error string surfaced from backend (token refresh failure, etc). */
  last_error?: string | null;
}

const STATUS_PATH = "/api/oauth/google/status"; // TODO Phase 3 — confirm endpoint path
const INIT_PATH = "/oauth/google/init"; // TODO Phase 3 — confirm endpoint path

export function useOAuthStatus() {
  const { user } = useAuthStore();
  return useQuery<OAuthStatus>({
    queryKey: ["oauth-google-status"],
    queryFn: () => api.get(STATUS_PATH),
    enabled: !!user,
    // Modest refetch — token expiry visibility doesn't need to be sub-second.
    refetchInterval: 60_000,
  });
}

/**
 * Redirect the browser to the backend OAuth init endpoint.
 * Backend handles the Google consent + redirects back to a frontend success page.
 */
export function redirectToOAuthInit(): void {
  // Use full path so reverse-proxy + dev-server both forward to backend.
  window.location.href = INIT_PATH;
}
