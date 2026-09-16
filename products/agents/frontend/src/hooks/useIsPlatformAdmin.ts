/**
 * UX-only hint for the NoctusAI operator (`noctus_role === "admin"`), used to
 * decide whether to ASK for platform-admin data (the dashboard's expiry
 * banner). User metadata is user-writable, so this is never the gate — the
 * backend's `require_platform_admin` reads `public.noctus_users.role`, and
 * the Credenciais / Configurações pages render whatever the API answers
 * (a 403 shows the restricted-access state).
 */
import { useAuthStore } from "@noctusai/seed/infra";

export function useIsPlatformAdmin(): boolean {
  const { user } = useAuthStore();
  const metadata = (user?.user_metadata ?? {}) as Record<string, unknown>;
  return metadata.noctus_role === "admin";
}
