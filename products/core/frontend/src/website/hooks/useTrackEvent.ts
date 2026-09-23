/**
 * Event tracking gated on Medição consent (contract: "a first-party anon id
 * stored only after the Medição consent"). The `POST /api/website/events`
 * call itself is allowed regardless (it's first-party telemetry with no PII,
 * contract §1 `website_events`), but the ANON ID that ties events together
 * across a session is only minted once the visitor has opted into
 * measurement — before that, events are sent anonId-less.
 */
import { useCallback } from "react";
import { useConsent } from "../lib/consent";
import { postEvent } from "../lib/api";

function ensureAnonId(): void {
  if (typeof window === "undefined") return;
  if (window.localStorage.getItem("nx.anon_id")) return;
  const id = `nx_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
  window.localStorage.setItem("nx.anon_id", id);
}

function ensureSessionId(): void {
  if (typeof window === "undefined") return;
  if (window.sessionStorage.getItem("nx.session_id")) return;
  const id = `s_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
  window.sessionStorage.setItem("nx.session_id", id);
}

export function useTrackEvent(): (event: string, props?: Record<string, unknown>) => void {
  const { decision } = useConsent();

  return useCallback(
    (event: string, props?: Record<string, unknown>) => {
      if (decision?.measurement) {
        ensureAnonId();
        ensureSessionId();
      }
      postEvent(event, props);
    },
    [decision?.measurement],
  );
}
