import type { Config } from "tailwindcss";

/**
 * Tokens de design do P Studio — terracota sobre branco quente.
 *
 * Portados do protótipo Lovable (`realty-lens-pro/src/styles.css`), que usava
 * a sintaxe `@theme` do Tailwind v4. Aqui a plataforma está no Tailwind v3, então
 * cada cor vira uma variável CSS com os *componentes* OKLCH soltos
 * (`--primary: 0.58 0.14 40`) e o config remonta `oklch(... / <alpha-value>)`.
 * É o que preserva os modificadores de opacidade (`bg-primary/10`,
 * `bg-status-late/15`) sem os quais o sistema de status por cor não funciona.
 */
const cor = (nome: string) => `oklch(var(--${nome}) / <alpha-value>)`;

export default {
  darkMode: "class",
  // 🔴 The seed's own source MUST be scanned. The FE runs on
  // `createProductApp` + `createProductLayout`, so the shell (AppShell /
  // Sidebar / Header) lives in `seed/framework` + `seed/lib` — NOT in
  // `./src`. Tailwind only emits classes it can SEE, so scanning `./src`
  // alone purges every utility used inside those components.
  //
  // That is not theoretical: it shipped. On 2026-08-17 p-studio went live
  // with the sidebar `fixed w-64` (those classes happen to also appear in
  // p-studio's own source, so they survived) while the content wrapper's
  // responsive offset did NOT — `main` rendered at x=0 UNDERNEATH the
  // sidebar, titles and KPI cards colliding with the nav. Backend healthy,
  // bundle valid, page visibly broken.
  //
  // Globs mirror `seed/framework/frontend/tailwind.config.factory.ts`
  // (`DEFAULT_CONTENT`), whose docstring warns of this exact failure.
  //
  // WHY NOT the factory itself (the seed-first answer)? The factory applies
  // `presets: [base]`, and the base preset defines every colour as
  // `hsl(var(--x))` while this product's palette is OKLCH
  // (`oklch(var(--x) / <alpha-value>)`, ported from the Lovable prototype).
  // Adopting the preset today would resolve HSL against OKLCH components and
  // break every colour. Reconciling the two colour spaces — or giving the
  // factory a theme seam — is tracked as follow-up; until then this config
  // stays local BY DECISION, and the content globs must be kept in sync
  // with the factory's.
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../../seed/lib/frontend/src/**/*.{ts,tsx}",
    "../../../seed/framework/frontend/src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: cor("background"),
        foreground: cor("foreground"),
        card: { DEFAULT: cor("card"), foreground: cor("card-foreground") },
        popover: { DEFAULT: cor("popover"), foreground: cor("popover-foreground") },
        primary: { DEFAULT: cor("primary"), foreground: cor("primary-foreground") },
        secondary: { DEFAULT: cor("secondary"), foreground: cor("secondary-foreground") },
        muted: { DEFAULT: cor("muted"), foreground: cor("muted-foreground") },
        accent: { DEFAULT: cor("accent"), foreground: cor("accent-foreground") },
        destructive: { DEFAULT: cor("destructive"), foreground: cor("destructive-foreground") },
        border: cor("border"),
        input: cor("input"),
        ring: cor("ring"),
        sidebar: {
          DEFAULT: cor("sidebar"),
          foreground: cor("sidebar-foreground"),
          primary: cor("sidebar-primary"),
          "primary-foreground": cor("sidebar-primary-foreground"),
          accent: cor("sidebar-accent"),
          "accent-foreground": cor("sidebar-accent-foreground"),
          border: cor("sidebar-border"),
          ring: cor("sidebar-ring"),
        },
        // Sistema de status por cor (spec § 9) — oito cores semânticas.
        status: {
          lead: cor("status-lead"),
          scheduled: cor("status-scheduled"),
          captured: cor("status-captured"),
          editing: cor("status-editing"),
          delivered: cor("status-delivered"),
          received: cor("status-received"),
          late: cor("status-late"),
          cancelled: cor("status-cancelled"),
        },
      },
      borderRadius: {
        sm: "calc(var(--radius) - 4px)",
        md: "calc(var(--radius) - 2px)",
        lg: "var(--radius)",
        xl: "calc(var(--radius) + 4px)",
      },
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Fraunces"', "ui-serif", "Georgia", "serif"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
} satisfies Config;
