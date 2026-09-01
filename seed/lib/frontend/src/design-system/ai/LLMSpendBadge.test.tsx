/**
 * Tests for `<LLMSpendBadge/>` + `useLLMSpend`'s envelope handling.
 *
 * THE BUG THESE PIN (live on social.noctusai.com, 2026-09-01):
 * core answers `GET /api/admin/llm-spend/{org}` with the seed envelope
 * `{"data": {...}}`, but the hook read the TOP level. Every field came back
 * `undefined` — including `status`, so the badge's `status === 'ok' | 'unset'`
 * early-return never fired. Result: a permanent, content-free warning chip
 * reading `IA ?% (— / —)` on every page for every admin, and a real
 * `hard_stop` that could never render as one.
 *
 * The badge is the surface that showed the symptom, so it is what is asserted:
 * an unreadable payload must render NOTHING, and a well-formed envelope must
 * render the real numbers.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  vi.resetModules();
});

const mockUseLLMSpend = vi.fn();

vi.mock('./useLLMSpend', () => ({
  useLLMSpend: (...a: unknown[]) => mockUseLLMSpend(...a),
  LLM_SPEND_REFETCH_INTERVAL_MS: 300000,
}));

vi.mock('@noctusai/seed/infra', () => ({
  useAuthStore: () => ({
    user: { user_metadata: { org_id: 'org-1', product_roles: { admin: true } } },
  }),
  coreApi: { get: vi.fn() },
}));

// The component imports `resolveSSORoles` from the package's public entry, so
// that is the specifier to intercept — not the module it happens to live in.
vi.mock('@noctusai/lib', () => ({
  resolveSSORoles: () => ({ isProductAdmin: true }),
}));

vi.mock('./SpendDetailModal', () => ({
  SpendDetailModal: () => null,
}));

async function renderBadge() {
  const React = (await import('react')).default;
  const { LLMSpendBadge } = await import('./LLMSpendBadge');
  return render(React.createElement(LLMSpendBadge));
}

describe('<LLMSpendBadge/> — never render a warning nobody can read', () => {
  it('renders nothing when every figure is missing (the envelope bug)', async () => {
    mockUseLLMSpend.mockReturnValue({
      data: {
        status: 'warn',
        used_pct: null,
        spent_brl: null,
        budget_brl: null,
      },
    });
    const { container } = await renderBadge();
    expect(container.textContent).toBe('');
  });

  it('renders nothing on ok', async () => {
    mockUseLLMSpend.mockReturnValue({
      data: { status: 'ok', used_pct: 0.1, spent_brl: 10, budget_brl: 100 },
    });
    const { container } = await renderBadge();
    expect(container.textContent).toBe('');
  });

  it('renders nothing on unset', async () => {
    mockUseLLMSpend.mockReturnValue({
      data: { status: 'unset', used_pct: 0, spent_brl: 0, budget_brl: 0 },
    });
    const { container } = await renderBadge();
    expect(container.textContent).toBe('');
  });

  it('renders the real numbers on warn', async () => {
    mockUseLLMSpend.mockReturnValue({
      data: { status: 'warn', used_pct: 85.4, spent_brl: 854, budget_brl: 1000 },
    });
    const { container } = await renderBadge();
    expect(container.textContent).toContain('85%');
    expect(container.textContent).not.toContain('?%');
  });

  it('renders the hard-stop label on hard_stop', async () => {
    mockUseLLMSpend.mockReturnValue({
      data: { status: 'hard_stop', used_pct: 101, spent_brl: 1010, budget_brl: 1000 },
    });
    const { container } = await renderBadge();
    expect(container.textContent).toContain('Limite IA atingido');
  });

  it('renders nothing when the query has no data at all', async () => {
    mockUseLLMSpend.mockReturnValue({ data: undefined });
    const { container } = await renderBadge();
    expect(container.textContent).toBe('');
  });
});
