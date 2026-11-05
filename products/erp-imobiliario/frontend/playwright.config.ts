import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Retries exist to capture a trace (trace: 'on-first-retry'), never to decide: a spec that
  // failed then passed is flaky and fails the job. Quarantine = test.fixme + NOC-REMEDIATE[flaky]
  // (14-day expiry, pending owner confirmation). KB § PATTERNS/compliance/test-engineering-canon.md §8
  failOnFlakyTests: !!process.env.CI,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: 'http://localhost:8080',
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
    port: 8080,
    reuseExistingServer: !process.env.CI,
    env: {
      VITE_SUPABASE_URL: 'http://localhost:54321',
      // E2E mocks the backend, so the frontend never round-trips to Supabase —
      // a non-secret placeholder is the correct value (real key not needed and
      // not wanted: a JWT-shaped literal here trips Trivy's secret scanner).
      VITE_SUPABASE_PUBLISHABLE_KEY:
        process.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'test-publishable-key-e2e-only',
      VITE_BACKEND_API_URL: 'http://localhost:8001',
    },
  },
});
