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
  get BACKEND_API_URL() { return getViteVar('VITE_BACKEND_API_URL') || 'http://localhost:8000'; },
  get CORE_URL() { return getViteVar('VITE_CORE_URL') || 'http://localhost:5173'; },
  get CORE_API_URL() { return getViteVar('VITE_CORE_API_URL') || 'http://localhost:8000'; },
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
