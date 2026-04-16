/**
 * NoctusAI Global Theme Hook
 *
 * Shared dark/light theme toggle logic.
 * Reads from localStorage, syncs to document.documentElement.classList.
 *
 * Products can optionally persist to DB via the onPersist callback.
 *
 * Usage:
 *   const { theme, toggleTheme } = useTheme();
 *   // or with DB persistence:
 *   const { theme, toggleTheme } = useTheme({
 *     initialTheme: profile?.tema,
 *     onPersist: (t) => updateProfile({ tema: t }),
 *   });
 */
import { useState, useEffect } from "react";

const STORAGE_KEY = "theme";

interface UseThemeOptions {
  /** Initial theme from DB (overrides localStorage on first load) */
  initialTheme?: "light" | "dark" | null;
  /** Persist theme change to DB */
  onPersist?: (theme: "light" | "dark") => void;
}

export function useTheme(options?: UseThemeOptions) {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === "dark" ? "dark" : "light";
  });

  // Sync DB value → local on first load
  useEffect(() => {
    if (options?.initialTheme && options.initialTheme !== theme) {
      setTheme(options.initialTheme);
    }
  }, [options?.initialTheme]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync to DOM + localStorage
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    options?.onPersist?.(next);
  };

  return { theme, toggleTheme } as const;
}
