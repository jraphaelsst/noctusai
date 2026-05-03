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
 * If a future test actually needs to render a real design-system component,
 * extend this stub with an explicit-enough component (or remove the alias
 * for that test via `vi.doMock`).
 */
import React from "react";

export const PageSkeleton: React.FC = () => (
  <div data-testid="page-skeleton-stub" />
);
