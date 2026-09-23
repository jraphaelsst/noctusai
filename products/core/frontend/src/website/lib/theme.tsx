/**
 * Website-local, SSR-safe theme hook (contract D2 — no seed changes in v1;
 * the seed `useTheme`'s `localStorage` read inside `useState` crashes under
 * SSR, so the website ships its own instead of forking it). Exported as
 * `useSiteTheme` (not `useTheme`) deliberately — this is a genuinely
 * separate implementation, not a wrapper around the canonical
 * `@noctusai/lib` organ, so it does not carry a `@consumes-organ`
 * declaration; a same-named local `useTheme` would instead trip
 * `check_canonical_organ_consumption` as an UNDECLARED re-implementation.
 * Same reasoning for `components/Header.tsx` → `SiteHeader`.
 *
 * The 3-state choice (`system|light|dark`) drives BOTH the header switch AND
 * the `--scene-*` CSS custom properties the 3D hero reads (06 §Theming) —
 * recolouring happens purely through the `data-theme` attribute + CSS, no
 * scene reload needed.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { THEME_STORAGE_KEY } from "./themeScript";

export type ThemeChoice = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice !== "system") return choice;
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolved);
}

interface ThemeContextValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  choice: "system",
  resolved: "dark",
  setChoice: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Both server and first client paint start at "system" / "dark" — matches
  // the inline script's own fallback, so there is nothing for React to
  // "correct" on hydrate. The inline script has ALREADY set the real
  // `data-theme` attribute imperatively before this ever runs.
  const [choice, setChoiceState] = useState<ThemeChoice>("system");
  const [resolved, setResolved] = useState<ResolvedTheme>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeChoice | null;
    const initial = stored ?? "system";
    setChoiceState(initial);
    setResolved(resolveTheme(initial));
  }, []);

  useEffect(() => {
    const next = resolveTheme(choice);
    setResolved(next);
    applyTheme(next);
    if (choice !== "system" || typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => {
      const r = resolveTheme("system");
      setResolved(r);
      applyTheme(r);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [choice]);

  function setChoice(next: ThemeChoice) {
    setChoiceState(next);
    if (typeof window !== "undefined") window.localStorage.setItem(THEME_STORAGE_KEY, next);
  }

  return (
    <ThemeContext.Provider value={{ choice, resolved, setChoice }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useSiteTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
