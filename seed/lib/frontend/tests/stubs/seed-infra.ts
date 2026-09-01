/**
 * Resolution stub for `@noctusai/seed/infra` inside `@noctusai/lib`'s OWN test
 * run.
 *
 * `seed/lib/frontend` sits BELOW the seed framework in the dependency order: a
 * product resolves `@noctusai/seed/infra` through its own node_modules, but the
 * lib package has no such link, so any organ importing it was untestable here —
 * Vite fails at RESOLVE time, before `vi.mock` ever gets a chance to intercept.
 * That is why `<LLMSpendBadge/>` had no tests while carrying a live bug.
 *
 * Aliased in `vitest.config.ts`. Every value here is inert on purpose: a test
 * that needs real behaviour must `vi.mock('@noctusai/seed/infra', …)` with what
 * it actually expects, so nothing silently passes against this stub.
 */
export const useAuthStore = () => ({ user: null });
export const coreApi = {
  get: async () => {
    throw new Error(
      'coreApi.get called against the resolution stub — vi.mock("@noctusai/seed/infra") in your test.',
    );
  },
};
export const api = coreApi;
