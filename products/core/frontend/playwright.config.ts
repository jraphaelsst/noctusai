import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    env: {
      // The seed supabase client (`@noctusai/lib/design-system` -> supabase.ts)
      // THROWS at module load when these build-time vars are absent — the React
      // tree never mounts and every spec fails with "element(s) not found". Core
      // uses its own custom JWT auth provider, but the seed still imports the
      // supabase client, so the vars must exist. E2E mocks the backend, so the
      // frontend never round-trips to Supabase — non-secret placeholders are the
      // correct values (a real/JWT-shaped key would trip Trivy's secret scanner).
      VITE_SUPABASE_URL: 'http://localhost:54321',
      VITE_SUPABASE_PUBLISHABLE_KEY:
        process.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'test-publishable-key-e2e-only',
      VITE_CORE_API_URL: 'http://localhost:8000',
    },
  },
});
