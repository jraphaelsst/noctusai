import { createClient } from '@supabase/supabase-js';
import { env } from './env';

/**
 * Actionable message for the #1 silent-blank-page defect: the seed's
 * required `VITE_SUPABASE_*` were empty in the Vite bundle because the
 * product Docker build never passed them as build args (Vite inlines
 * `import.meta.env.VITE_*` at `vite build` time — they are a *build*
 * concern, not runtime). Names the root cause + the fix so the next
 * consumer doesn't burn two debugging cycles on a blank screen.
 *
 * Under noc's single-container house model the fix lives in the
 * product's backend Dockerfile (the stage that runs the frontend
 * `vite build`) + that product's docker-compose `build.args` — NOT a
 * separate `Dockerfile.frontend` (the old 2-container shape the
 * originating workspace used; superseded by `serve_spa`).
 */
const SUPABASE_ENV_HELP =
  'Missing VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY. These are ' +
  'BUILD-time vars — Vite inlines them at `vite build`, not at runtime. ' +
  'Pass them as Docker build args in the product image stage that runs ' +
  'the frontend build:\n' +
  '  ARG VITE_SUPABASE_URL / ARG VITE_SUPABASE_PUBLISHABLE_KEY\n' +
  '  ENV  VITE_SUPABASE_URL=${VITE_SUPABASE_URL} (+ the publishable key)\n' +
  'and in docker-compose `build.args` for that product. Do NOT bake ' +
  'VITE_BACKEND_API_URL — it is runtime-detected on purpose (one image ' +
  'serves direct/tunnel/proxy).';

/**
 * Build-time assertion. Call in the product `main.tsx` BEFORE render.
 * Because `env.SUPABASE_*` read `import.meta.env` (Vite-inlined), an
 * empty value here means the build itself was misconfigured — fail with
 * the actionable message instead of rendering a blank page that throws
 * deep in `createProductSupabase` on first use.
 *
 * Skipped when `VITE_DEV_AUTOLOGIN` is on: the dev-autologin path
 * synthesizes a session and never constructs a real Supabase client, so
 * the Supabase vars are legitimately absent in that mode.
 */
export function assertSupabaseBuildEnv(): void {
  if (env.DEV_AUTOLOGIN) return;
  if (!env.SUPABASE_URL || !env.SUPABASE_PUBLISHABLE_KEY) {
    throw new Error(SUPABASE_ENV_HELP);
  }
}

export function createProductSupabase(schema?: string) {
  if (!env.SUPABASE_URL || !env.SUPABASE_PUBLISHABLE_KEY) {
    throw new Error(SUPABASE_ENV_HELP);
  }
  return createClient(env.SUPABASE_URL, env.SUPABASE_PUBLISHABLE_KEY, {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    },
    ...(schema ? { db: { schema } } : {}),
  });
}
