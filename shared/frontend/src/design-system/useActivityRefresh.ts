/**
 * NoctusAI — Activity-Based Token Refresh
 *
 * Proactively refreshes the auth token while the user is active.
 * Inactive users' tokens expire naturally for security.
 *
 * Two-tier activity model:
 * 1. DIRECT INTERACTION (proves a human is present):
 *    mousemove (throttled 1x/sec), keydown, scroll, click, touchstart
 *    → Resets the full activity timer.
 *
 * 2. PASSIVE PRESENCE (tab visible but no proof of human):
 *    visibilitychange (tab visible), focus (window focused)
 *    → Only counts as active for READING_TIMEOUT (3 min) after the
 *      last direct interaction. After that, passive presence alone
 *      is NOT enough to keep refreshing — protects unattended screens.
 *
 * Security scenario:
 *   User walks away → no direct interaction → after 3 min, passive
 *   presence stops counting → token stops refreshing → expires naturally.
 *   Someone sitting at the unattended PC sees an expired session.
 *
 * Optimizations:
 * - Mousemove throttled to 1 update/second
 * - Multi-tab coordination via localStorage (only one tab refreshes)
 * - Offline-aware: skips refresh when navigator.onLine is false
 * - Failure backoff: 30s cooldown after failed refresh
 * - Deduplication: won't refresh if last refresh was < interval/2 ago
 */
import { useEffect, useRef, useCallback } from "react";

const INTERACTION_EVENTS = ["keydown", "scroll", "click", "touchstart"] as const;
const DEFAULT_INTERVAL = 5 * 60 * 1000; // 5 minutes
const DEFAULT_READING_TIMEOUT = 3 * 60 * 1000; // 3 minutes
const MOUSEMOVE_THROTTLE = 1000; // 1 second
const FAILURE_BACKOFF = 30 * 1000; // 30 seconds
const STORAGE_KEY = "noctus_last_token_refresh";

interface UseActivityRefreshOptions {
  /** Called to refresh the token. */
  onRefresh: () => Promise<void>;
  /** Refresh interval in ms. Default: 5 minutes. */
  intervalMs?: number;
  /**
   * How long passive presence (tab visible, no interaction) counts as active.
   * After this duration without direct interaction, passive signals are ignored.
   * Default: 3 minutes. Set to 0 to disable passive presence entirely.
   */
  readingTimeoutMs?: number;
  /** Set to false to disable. Default: true. */
  enabled?: boolean;
}

export function useActivityRefresh({
  onRefresh,
  intervalMs = DEFAULT_INTERVAL,
  readingTimeoutMs = DEFAULT_READING_TIMEOUT,
  enabled = true,
}: UseActivityRefreshOptions) {
  // Last DIRECT interaction (mouse, key, scroll, click, touch)
  const lastInteractionRef = useRef<number>(Date.now());
  // Last activity (direct OR passive within reading window)
  const lastActivityRef = useRef<number>(Date.now());
  const lastRefreshRef = useRef<number>(0);
  const failedAtRef = useRef<number>(0);
  const mouseMoveThrottleRef = useRef<number>(0);

  // Direct interaction — proves a human is present
  const markInteraction = useCallback(() => {
    const now = Date.now();
    lastInteractionRef.current = now;
    lastActivityRef.current = now;
  }, []);

  // Throttled mousemove — direct interaction with rate limit
  const handleMouseMove = useCallback(() => {
    const now = Date.now();
    if (now - mouseMoveThrottleRef.current > MOUSEMOVE_THROTTLE) {
      mouseMoveThrottleRef.current = now;
      lastInteractionRef.current = now;
      lastActivityRef.current = now;
    }
  }, []);

  // Passive presence — only counts if last direct interaction was recent
  const handlePassivePresence = useCallback(() => {
    const now = Date.now();
    const sinceLastInteraction = now - lastInteractionRef.current;

    // Only extend activity if we had direct interaction within the reading window
    if (sinceLastInteraction < readingTimeoutMs) {
      lastActivityRef.current = now;
    }
    // If no direct interaction for > readingTimeout, passive presence is ignored.
    // This is the "unattended screen" protection.
  }, [readingTimeoutMs]);

  const handleVisibility = useCallback(() => {
    if (document.visibilityState === "visible") {
      handlePassivePresence();
    }
  }, [handlePassivePresence]);

  useEffect(() => {
    if (!enabled) return;

    // Direct interaction listeners
    INTERACTION_EVENTS.forEach((e) =>
      window.addEventListener(e, markInteraction, { passive: true })
    );
    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // Passive presence listeners
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handlePassivePresence);

    // Multi-tab coordination
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        lastRefreshRef.current = parseInt(e.newValue, 10) || 0;
      }
    };
    window.addEventListener("storage", handleStorage);

    // Refresh interval
    const intervalId = setInterval(async () => {
      const now = Date.now();
      const sinceActivity = now - lastActivityRef.current;
      const sinceLastRefresh = now - lastRefreshRef.current;
      const sinceFailure = now - failedAtRef.current;

      // Skip if user was inactive for the full interval
      if (sinceActivity >= intervalMs) return;

      // Skip if offline
      if (!navigator.onLine) return;

      // Skip if we (or another tab) refreshed recently
      if (sinceLastRefresh < intervalMs / 2) return;

      // Skip if we failed recently (backoff)
      if (failedAtRef.current > 0 && sinceFailure < FAILURE_BACKOFF) return;

      try {
        await onRefresh();
        lastRefreshRef.current = now;
        failedAtRef.current = 0;
        try {
          localStorage.setItem(STORAGE_KEY, String(now));
        } catch {
          // localStorage may be unavailable
        }
      } catch {
        failedAtRef.current = now;
      }
    }, intervalMs);

    return () => {
      INTERACTION_EVENTS.forEach((e) =>
        window.removeEventListener(e, markInteraction)
      );
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handlePassivePresence);
      window.removeEventListener("storage", handleStorage);
      clearInterval(intervalId);
    };
  }, [enabled, intervalMs, onRefresh, markInteraction, handleMouseMove, handleVisibility, handlePassivePresence]);
}
