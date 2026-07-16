/**
 * Test-time stub for `@noctusai/lib/design-system`.
 *
 * The framework's `createProductApp` imports `PageSkeleton` from the design
 * system. At runtime the real component (with lucide icons, Radix primitives,
 * and the full UI surface) is fine because consumer products install those
 * deps. In THIS test harness we don't want to pull the entire design-system
 * transitive-dep graph just to test routing/auth logic — so vitest aliases
 * `@noctusai/lib/design-system` to this minimal stub.
 *
 * `layout.test.tsx` (the `sessionAuth`/`supabase` dual-mode seam) additionally
 * needs `AppShell` / `Sidebar` / `Header` / `useTheme` / `useActivityRefresh` /
 * `InactivityWarning` / `AIBadgeStack` / badge components — stubbed below with
 * just enough surface to (a) not crash `createProductLayout`'s render and
 * (b) expose the injected handlers (`onLogout`, `onUpdatePassword`,
 * `onUpdateProfile`, `InactivityWarning.onExtend`) as clickable buttons so
 * tests can prove they're ACTUALLY invoked — not just present as props.
 *
 * If a future test actually needs to render a real design-system component,
 * extend this stub with an explicit-enough component (or remove the alias
 * for that test via `vi.doMock`).
 */
import React from "react";

export const PageSkeleton: React.FC = () => (
  <div data-testid="page-skeleton-stub" />
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const AppShell: React.FC<any> = ({ sidebar, header, children }) => (
  <div data-testid="app-shell-stub">
    <div data-testid="app-shell-sidebar">{sidebar}</div>
    <div data-testid="app-shell-header">
      {typeof header === "function" ? header({ onMenuToggle: () => {} }) : header}
    </div>
    <div data-testid="app-shell-content">{children}</div>
  </div>
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const Sidebar: React.FC<any> = ({ brandTitle, navGroups, standaloneItems, footerContent }) => (
  <nav data-testid="sidebar-stub">
    <span data-testid="sidebar-brand">{brandTitle}</span>
    <span data-testid="sidebar-nav-group-count">{navGroups?.length ?? 0}</span>
    <span data-testid="sidebar-nav-item-count">
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      {(navGroups ?? []).reduce((acc: number, g: any) => acc + (g.items?.length ?? 0), 0)}
    </span>
    <span data-testid="sidebar-standalone-count">{standaloneItems?.length ?? 0}</span>
    {footerContent}
  </nav>
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const Header: React.FC<any> = ({
  user,
  onLogout,
  onUpdatePassword,
  onUpdateProfile,
  actions,
}) => (
  <header data-testid="header-stub">
    <span data-testid="header-user-name">{user?.name}</span>
    <span data-testid="header-user-email">{user?.email}</span>
    <button data-testid="logout-button" onClick={() => { void onLogout(); }}>
      Sair
    </button>
    <button
      data-testid="update-password-button"
      onClick={() => { void onUpdatePassword("new-pass-123"); }}
    >
      Alterar senha
    </button>
    <button
      data-testid="update-profile-button"
      onClick={() => {
        void onUpdateProfile({ name: "New Name", email: "new@example.com", phone: "555" });
      }}
    >
      Atualizar perfil
    </button>
    <div data-testid="header-actions">{actions}</div>
  </header>
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useTheme({ initialTheme }: { initialTheme?: "light" | "dark" } = {}) {
  return { theme: initialTheme ?? "light", toggleTheme: () => {} };
}

// Real activity-tracking behavior (event listeners + interval) is unit-tested
// in `seed/lib/frontend`'s own `useActivityRefresh` suite — a no-op here
// keeps `layout.test.tsx` deterministic (no fake timers needed).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useActivityRefresh(_opts: any): void {
  // intentionally no-op
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const InactivityWarning: React.FC<any> = ({ onExtend, onExpired }) => (
  <div data-testid="inactivity-warning-stub">
    <button data-testid="inactivity-extend-button" onClick={() => { void onExtend(); }}>
      Continuar
    </button>
    <button data-testid="inactivity-expired-button" onClick={onExpired}>
      Expirado
    </button>
  </div>
);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const AIBadgeStack: React.FC<any> = ({ badges }) => (
  <div data-testid="ai-badge-stack-stub">{badges}</div>
);

export const PendingConsentBadge: React.FC = () => (
  <span data-testid="pending-consent-badge-stub" />
);

export const LLMSpendBadge: React.FC = () => (
  <span data-testid="llm-spend-badge-stub" />
);
