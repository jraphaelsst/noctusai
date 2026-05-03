/**
 * NoctusAI — Inactivity Warning Modal
 *
 * Shows a countdown warning when the user has been inactive for too long,
 * giving them a chance to extend their session before it expires.
 *
 * Uses the same activity tracking pattern as useActivityRefresh
 * (lastInteractionRef with throttled mousemove).
 *
 * ## Wiring into a product
 *
 * Add to the product's Layout.tsx (alongside useActivityRefresh):
 *
 * ```tsx
 * import { InactivityWarning } from "@noctusai/lib/design-system";
 * import { supabase } from "@/integrations/supabase/client";
 *
 * // Inside Layout component return:
 * <InactivityWarning
 *   onExtend={async () => { await supabase.auth.refreshSession(); }}
 *   onExpired={() => { supabase.auth.signOut(); }}
 * />
 * ```
 *
 * Props:
 * - onExtend: called when user clicks "Continuar" — should refresh the token
 * - onExpired: called when countdown reaches 0 — should sign out / redirect
 * - tokenLifetimeMs: total inactivity before expiry (default 30 min)
 * - warningBeforeMs: how early to show warning (default 2 min)
 */
import { useState, useEffect, useRef, useCallback } from "react";

const INTERACTION_EVENTS = ["keydown", "scroll", "click", "touchstart"] as const;
const MOUSEMOVE_THROTTLE = 1000;

interface InactivityWarningProps {
  /** Called when user clicks "Continuar" to extend the session. */
  onExtend: () => Promise<void>;
  /** Called when the countdown reaches 0. */
  onExpired: () => void;
  /** Total inactivity time before session expires (ms). Default: 30 min. */
  tokenLifetimeMs?: number;
  /** How long before expiry to show the warning (ms). Default: 2 min. */
  warningBeforeMs?: number;
}

export function InactivityWarning({
  onExtend,
  onExpired,
  tokenLifetimeMs = 30 * 60 * 1000,
  warningBeforeMs = 2 * 60 * 1000,
}: InactivityWarningProps) {
  const [visible, setVisible] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const lastInteractionRef = useRef<number>(Date.now());
  const mouseMoveThrottleRef = useRef<number>(0);
  const expiredRef = useRef(false);

  const warningThreshold = tokenLifetimeMs - warningBeforeMs;

  const markInteraction = useCallback(() => {
    lastInteractionRef.current = Date.now();
  }, []);

  const handleMouseMove = useCallback(() => {
    const now = Date.now();
    if (now - mouseMoveThrottleRef.current > MOUSEMOVE_THROTTLE) {
      mouseMoveThrottleRef.current = now;
      lastInteractionRef.current = now;
    }
  }, []);

  // Register activity listeners
  useEffect(() => {
    INTERACTION_EVENTS.forEach((e) =>
      window.addEventListener(e, markInteraction, { passive: true })
    );
    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    return () => {
      INTERACTION_EVENTS.forEach((e) =>
        window.removeEventListener(e, markInteraction)
      );
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, [markInteraction, handleMouseMove]);

  // Check inactivity every second
  useEffect(() => {
    const intervalId = setInterval(() => {
      const elapsed = Date.now() - lastInteractionRef.current;

      if (elapsed >= tokenLifetimeMs) {
        if (!expiredRef.current) {
          expiredRef.current = true;
          setVisible(false);
          onExpired();
        }
        return;
      }

      if (elapsed >= warningThreshold) {
        const remaining = Math.ceil((tokenLifetimeMs - elapsed) / 1000);
        setSecondsLeft(remaining);
        setVisible(true);
      } else {
        setVisible(false);
      }
    }, 1000);

    return () => clearInterval(intervalId);
  }, [tokenLifetimeMs, warningThreshold, onExpired]);

  const handleExtend = async () => {
    try {
      await onExtend();
      lastInteractionRef.current = Date.now();
      expiredRef.current = false;
      setVisible(false);
    } catch {
      // If refresh fails, let the countdown continue
    }
  };

  if (!visible) return null;

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const timeDisplay = `${minutes}:${seconds.toString().padStart(2, "0")}`;

  return (
    <div className="fixed bottom-4 right-4 z-50 bg-card border border-border shadow-lg rounded-lg p-4 w-80">
      <p className="text-sm font-medium text-card-foreground mb-1">
        Sessao expirando
      </p>
      <p className="text-xs text-muted-foreground mb-3">
        Sua sessao sera encerrada em{" "}
        <span className="font-mono font-semibold text-card-foreground">
          {timeDisplay}
        </span>{" "}
        por inatividade.
      </p>
      <button
        onClick={handleExtend}
        className="w-full px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Continuar
      </button>
    </div>
  );
}
