/**
 * Agent Studio — the onboarding channel to social-wiring (platform admin only).
 *
 *   GET  /api/studio/plataforma/sw-canal          state of the credential (never the value), last ok call, last error
 *   POST /api/studio/plataforma/sw-canal/testar   provisions it if due, then a harmless read-only call to social-wiring
 *
 * The credential is created and rotated by the server; nothing here can set or reveal it. The test's answer carries the
 * fresh status, which is committed into the status entry (the card never shows a state older than its own test).
 */
import { useQuery } from "@tanstack/react-query";
import { useCacheWriteMutation } from "@noctusai/lib/cache-writes";
import { api } from "@/lib/api";
import type { SwCanalStatus, SwCanalTeste } from "@/api/studio/types-onboarding";
import { studioKeys, toView } from "./keys";

const URL = "/api/studio/plataforma/sw-canal";

export function useSwCanal(enabled = true) {
  const q = useQuery<SwCanalStatus>({
    queryKey: studioKeys.swCanal(),
    queryFn: () => api.get<SwCanalStatus>(URL),
    enabled,
    retry: false,
    placeholderData: (prev) => prev,
  });
  return toView(q);
}

export function useTestarSwCanal() {
  return useCacheWriteMutation<SwCanalTeste, void>({
    mutationFn: () => api.post<SwCanalTeste>(`${URL}/testar`),
    // The server's answer IS the new status entry (it may have just provisioned the credential).
    targets: [{ queryKey: studioKeys.swCanal(), commit: (_old: SwCanalStatus | undefined, res: SwCanalTeste) => res.status }],
  });
}
