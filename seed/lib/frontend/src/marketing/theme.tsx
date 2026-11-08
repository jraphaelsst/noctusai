/**
 * SSR-safe 3-state theme (sistema / claro / escuro) for PUBLIC pages, lifted from core's website so every
 * landing shares one implementation. The seed `useTheme` (design-system) reads `localStorage` inside
 * `useState` and crashes under SSR, and has no "system" state, so public pages use this instead.
 *
 * The choice drives the `.dark` class (the seed tokens' Tailwind `darkMode: "class"`) AND `data-theme` on
 * `<html>` (legacy site CSS keys off it). The inline `<head>` script (`createThemeInlineScript`) applies
 * the stored choice before first paint so there is no flash; the provider starts at "system"/"dark" on both
 * server and first client paint (matching the script's own fallback), then reads storage in an effect.
 */
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { ThemeChoice } from "./LandingNav";

export type ResolvedTheme = "light" | "dark";

/** Default storage key. Core's value, kept so already-persisted choices survive the lift. */
export const THEME_STORAGE_KEY = "nx.theme";

/** The no-flash `<head>` script for `storageKey`. Runs before `<body>` exists, so it targets `<html>`. */
export function createThemeInlineScript(storageKey: string = THEME_STORAGE_KEY): string {
  const key = JSON.stringify(storageKey);
  return `(function(){try{var k=${key};var s=localStorage.getItem(k);var t=s;if(!t||t==="system"){t=window.matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";}document.documentElement.setAttribute("data-theme",t);document.documentElement.classList.toggle("dark",t==="dark");}catch(e){}})();`;
}

/** `createThemeInlineScript()` with the default key. */
export const THEME_INLINE_SCRIPT = createThemeInlineScript();

function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice !== "system") return choice;
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export interface LandingThemeValue {
  choice: ThemeChoice;
  resolved: ResolvedTheme;
  setChoice: (choice: ThemeChoice) => void;
}

const ThemeContext = createContext<LandingThemeValue>({ choice: "system", resolved: "dark", setChoice: () => {} });

export interface LandingThemeProviderProps {
  children: ReactNode;
  /** localStorage key; must match the one given to `createThemeInlineScript`. */
  storageKey?: string;
}

export function LandingThemeProvider({ children, storageKey = THEME_STORAGE_KEY }: LandingThemeProviderProps) {
  const [choice, setChoiceState] = useState<ThemeChoice>("system");
  const [resolved, setResolved] = useState<ResolvedTheme>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(storageKey) as ThemeChoice | null;
    const initial = stored ?? "system";
    setChoiceState(initial);
    setResolved(resolveTheme(initial));
  }, [storageKey]);

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
    if (typeof window !== "undefined") window.localStorage.setItem(storageKey, next);
  }

  return <ThemeContext.Provider value={{ choice, resolved, setChoice }}>{children}</ThemeContext.Provider>;
}

export function useLandingTheme(): LandingThemeValue {
  return useContext(ThemeContext);
}

/** Props for `LandingNav.themeSwitch` wired to the provider's state (the common case). */
export function useLandingThemeSwitch(onChange?: (next: ThemeChoice) => void) {
  const { choice, setChoice } = useLandingTheme();
  return {
    value: choice,
    onChange: (next: ThemeChoice) => {
      setChoice(next);
      onChange?.(next);
    },
  };
}
