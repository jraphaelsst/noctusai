/**
 * Cookie/tracking consent — website-local (contract D3, D8). Bottom bar,
 * never a modal (P12). Categories: Necessários (always on) · Medição ·
 * Marketing. Stored with a text version so a future copy change can force
 * re-consent. NOC-REMEDIATE[seed-promotion] once a second product needs
 * LGPD cookie consent (distinct from the seed's legal-document consent
 * routes, which this does not replace).
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export const CONSENT_TEXT_VERSION = "2026-09-23.v1";
const CONSENT_STORAGE_KEY = "nx.consent";

export interface ConsentDecision {
  measurement: boolean;
  marketing: boolean;
  text_version: string;
  at: string;
}

interface ConsentContextValue {
  decision: ConsentDecision | null;
  /** True until the visitor has made (or restored) a decision. */
  bannerOpen: boolean;
  accept: () => void;
  reject: () => void;
  save: (partial: { measurement: boolean; marketing: boolean }) => void;
}

const ConsentContext = createContext<ConsentContextValue>({
  decision: null,
  bannerOpen: false,
  accept: () => {},
  reject: () => {},
  save: () => {},
});

function readStored(): ConsentDecision | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CONSENT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ConsentDecision;
    // A copy change (text_version bump) invalidates any prior decision —
    // re-prompt rather than silently keep an outdated consent.
    if (parsed.text_version !== CONSENT_TEXT_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

function persist(decision: ConsentDecision): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(decision));
}

export function ConsentProvider({ children }: { children: ReactNode }) {
  // SSR/first paint: no decision, banner not yet shown — the banner only
  // appears once we know (post-mount) there is genuinely no stored decision,
  // avoiding a flash-then-hide on returning visitors.
  const [decision, setDecision] = useState<ConsentDecision | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setDecision(readStored());
    setChecked(true);
  }, []);

  function commit(measurement: boolean, marketing: boolean) {
    const next: ConsentDecision = {
      measurement,
      marketing,
      text_version: CONSENT_TEXT_VERSION,
      at: new Date().toISOString(),
    };
    persist(next);
    setDecision(next);
  }

  const value: ConsentContextValue = {
    decision,
    bannerOpen: checked && decision === null,
    accept: () => commit(true, true),
    reject: () => commit(false, false),
    save: (partial) => commit(partial.measurement, partial.marketing),
  };

  return <ConsentContext.Provider value={value}>{children}</ConsentContext.Provider>;
}

export function useConsent(): ConsentContextValue {
  return useContext(ConsentContext);
}
