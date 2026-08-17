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
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
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
