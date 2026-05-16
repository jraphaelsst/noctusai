/// <reference types="vite/client" />
/**
 * Shared environment variable configuration for NoctusAI products.
 *
 * Defines the required VITE_ environment variables every product frontend needs,
 * provides typed access, and validates at startup.
 *
 * Usage in product main.tsx:
 *   import { validateEnv } from '@noctusai/lib';
 *   validateEnv();  // throws with clear message if vars are missing
 *
 * Usage for typed access:
 *   import { env } from '@noctusai/lib';
 *   console.log(env.BACKEND_API_URL);
 *
 * Generating .env.example:
 *   import { generateEnvExample } from '@noctusai/lib';
 *   console.log(generateEnvExample(8005));
 */

// ---------------------------------------------------------------------------
// Shared env var definitions — single source of truth
// ---------------------------------------------------------------------------

export interface ProductEnv {
  /** Supabase project URL */
  SUPABASE_URL: string;
  /** Supabase anon/publishable key */
  SUPABASE_PUBLISHABLE_KEY: string;
  /** Product backend API base URL (e.g. http://localhost:8005) */
  BACKEND_API_URL: string;
  /** Core platform frontend URL (for SSO redirect and navigation) */
  CORE_URL: string;
  /** Core platform backend API URL (for SSO token exchange) */
  CORE_API_URL: string;
  /**
   * Dev-only: when 'true', the frontend skips the Landing/Login redirect
   * and synthesizes a fixed dev session (pairs with the backend
   * `SEED_DEV_AUTH` bypass). MUST be unset/false in production builds —
   * a loud console banner fires whenever it activates. Vite inlines this
   * at build time like the other VITE_* vars.
   */
  DEV_AUTOLOGIN: boolean;
  /**
   * Deployment topology: is this product attached to the Core platform?
   * Core-attached (default, true) → Core-only surfaces like
   * `/api/me/consents` are available. Standalone (false) → those
   * surfaces are absent; seed hooks that depend on them no-op instead of
   * toasting a backend-down error. Mirrors how `apiBase` reasons about
   * topology. Default true preserves existing SSO/Core-attached behavior
   * for every current product; standalone deploys opt out.
   */
  CORE_ATTACHED: boolean;
}

/** All required VITE_ var names with descriptions and defaults */
export const ENV_VARS: Record<keyof ProductEnv, { viteKey: string; description: string; required: boolean; defaultDev: string }> = {
  SUPABASE_URL: {
    viteKey: 'VITE_SUPABASE_URL',
    description: 'Supabase project URL (required by shared createProductSupabase)',
    required: true,
    defaultDev: 'https://your-project.supabase.co',
  },
  SUPABASE_PUBLISHABLE_KEY: {
    viteKey: 'VITE_SUPABASE_PUBLISHABLE_KEY',
    description: 'Supabase anon/publishable key (required by shared createProductSupabase)',
    required: true,
    defaultDev: 'eyJ...your-anon-key',
  },
  BACKEND_API_URL: {
    viteKey: 'VITE_BACKEND_API_URL',
    description: 'Product backend API URL',
    required: false,
    defaultDev: 'http://localhost:8000',
  },
  CORE_URL: {
    viteKey: 'VITE_CORE_URL',
    description: 'Core platform frontend URL (SSO redirect, navigation)',
    required: false,
    defaultDev: 'http://localhost:5173',
  },
  CORE_API_URL: {
    viteKey: 'VITE_CORE_API_URL',
    description: 'Core platform backend API URL (SSO token exchange)',
    required: false,
    defaultDev: 'http://localhost:8000',
  },
  DEV_AUTOLOGIN: {
    viteKey: 'VITE_DEV_AUTOLOGIN',
    description: 'Dev-only auto-login bypass (pairs with backend SEED_DEV_AUTH) — NEVER set in prod',
    required: false,
    defaultDev: 'false',
  },
  CORE_ATTACHED: {
    viteKey: 'VITE_CORE_ATTACHED',
    description: 'Topology: true=attached to Core platform (default), false=standalone (no Core-only endpoints)',
    required: false,
    defaultDev: 'true',
  },
};

// ---------------------------------------------------------------------------
// Typed env access
// ---------------------------------------------------------------------------

function getViteVar(viteKey: string): string | undefined {
  return (import.meta as any).env?.[viteKey];
}

/** Typed access to product environment variables with fallbacks */
export const env: ProductEnv = {
  get SUPABASE_URL() { return getViteVar('VITE_SUPABASE_URL') || ''; },
  get SUPABASE_PUBLISHABLE_KEY() { return getViteVar('VITE_SUPABASE_PUBLISHABLE_KEY') || ''; },
  // Read the LITERAL `import.meta.env.VITE_BACKEND_API_URL` so Vite's
  // `define` (vite.config.factory) rewrites it: absolute
  // http://localhost:<port> in dev/native, or `window.location.origin`
  // in single-container same-origin mode. getViteVar()'s bracket access
  // is NOT define-rewritten — this one getter reads the member
  // expression directly. → project: containerization-single-container.
  get BACKEND_API_URL() { return import.meta.env.VITE_BACKEND_API_URL || 'http://localhost:8000'; },
  get CORE_URL() { return getViteVar('VITE_CORE_URL') || 'http://localhost:5173'; },
  get CORE_API_URL() { return getViteVar('VITE_CORE_API_URL') || 'http://localhost:8000'; },
  // Read the LITERAL member expression so Vite's build-time inline
  // applies (same reason as BACKEND_API_URL above). String 'true' →
  // boolean true; anything else (incl. unset) → false. Default-OFF so a
  // prod build with the var absent never auto-logs-in.
  get DEV_AUTOLOGIN() { return import.meta.env.VITE_DEV_AUTOLOGIN === 'true'; },
  // Default-true: an UNSET var means "Core-attached" so every existing
  // product keeps current behavior. Only an explicit 'false' opts into
  // standalone (Core-only surfaces no-op).
  get CORE_ATTACHED() { return import.meta.env.VITE_CORE_ATTACHED !== 'false'; },
};

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Validates that all required VITE_ environment variables are set.
 * Call this once in the product's main.tsx before rendering.
 * Throws with a clear message listing missing vars.
 */
export function validateEnv(): void {
  const missing: string[] = [];
  for (const [key, config] of Object.entries(ENV_VARS)) {
    if (config.required && !getViteVar(config.viteKey)) {
      missing.push(`  ${config.viteKey} — ${config.description}`);
    }
  }
  if (missing.length > 0) {
    console.error(
      `[NoctusAI] Missing required environment variables:\n${missing.join('\n')}\n\n` +
      `Copy frontend/.env.example to frontend/.env and fill in the values.`
    );
  }
}

// ---------------------------------------------------------------------------
// .env.example generator
// ---------------------------------------------------------------------------

/**
 * Generates the content for a product's .env.example file.
 * @param backendPort — the product's backend port (e.g. 8005)
 */
export function generateEnvExample(backendPort: number): string {
  const lines: string[] = [];
  for (const [_key, config] of Object.entries(ENV_VARS)) {
    lines.push(`# ${config.description}`);
    const value = config.viteKey === 'VITE_BACKEND_API_URL'
      ? `http://localhost:${backendPort}`
      : config.defaultDev;
    lines.push(`${config.viteKey}=${value}`);
    lines.push('');
  }
  return lines.join('\n');
}
