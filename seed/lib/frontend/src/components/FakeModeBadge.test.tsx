/**
 * Tests for `<FakeModeBadge/>` + `useEnvMode()`.
 *
 * Mocks `import.meta.env.VITE_BACKEND_MODE` via vitest's `vi.stubEnv` —
 * each test sets the value, exercises the surface, and restores via
 * `afterEach` so cross-test leakage stays impossible.
 *
 * The component is rendered with `@testing-library/react`; assertions
 * use `@testing-library/jest-dom` matchers (registered in the seed
 * framework's vitest setup file).
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import { FakeModeBadge } from './FakeModeBadge';
import { useEnvMode } from '../hooks/useEnvMode';

function setMode(value: string | undefined): void {
  if (value === undefined) {
    vi.stubEnv('VITE_BACKEND_MODE', '');
    // also force the key to be "missing" by deleting it from the env-like proxy
    const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
    if (env) delete env.VITE_BACKEND_MODE;
  } else {
    vi.stubEnv('VITE_BACKEND_MODE', value);
  }
}

describe('useEnvMode', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    // clear so the "missing" branch is reachable
    const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
    if (env) delete env.VITE_BACKEND_MODE;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("returns mode='unknown' when VITE_BACKEND_MODE is missing", () => {
    const result = useEnvMode();
    expect(result.mode).toBe('unknown');
    expect(result.vendors).toEqual({});
  });

  it("returns mode='fake' for 'fake'", () => {
    setMode('fake');
    const result = useEnvMode();
    expect(result.mode).toBe('fake');
    expect(result.vendors.default).toBe('fake');
  });

  it("returns mode='real' for 'real'", () => {
    setMode('real');
    const result = useEnvMode();
    expect(result.mode).toBe('real');
    expect(result.vendors.default).toBe('real');
  });

  it("returns mode='mixed' with vendor map for 'calendar=fake,maps=real'", () => {
    setMode('calendar=fake,maps=real');
    const result = useEnvMode();
    expect(result.mode).toBe('mixed');
    expect(result.vendors).toEqual({ calendar: 'fake', maps: 'real' });
  });

  it("collapses to uniform mode when all pairs share the same value", () => {
    setMode('a=fake,b=fake');
    const result = useEnvMode();
    expect(result.mode).toBe('fake');
    expect(result.vendors).toEqual({ a: 'fake', b: 'fake' });
  });

  it("falls back to 'unknown' on malformed pair input + emits a console.warn in dev", () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    // import.meta.env.DEV is set true by vitest by default
    setMode('garbage=value');
    const result = useEnvMode();
    expect(result.mode).toBe('unknown');
    expect(result.vendors).toEqual({});
    expect(warn).toHaveBeenCalled();
  });

  it("falls back to 'unknown' on bare unrecognized string", () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    setMode('banana');
    const result = useEnvMode();
    expect(result.mode).toBe('unknown');
    expect(warn).toHaveBeenCalled();
  });
});

describe('<FakeModeBadge/>', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env;
    if (env) delete env.VITE_BACKEND_MODE;
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("renders the full chip with 'Mode: Fake' when mode='fake' (variant='auto')", () => {
    setMode('fake');
    const { container } = render(<FakeModeBadge />);
    const chip = container.querySelector('span[aria-label="Mode: Fake"]');
    expect(chip).toBeInTheDocument();
    expect(chip?.textContent).toContain('Mode: Fake');
    expect(chip?.className).toContain('bg-amber-50');
  });

  it("renders nothing when mode='real' and variant='auto'", () => {
    setMode('real');
    const { container } = render(<FakeModeBadge />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the full chip when variant='full' even if mode='real'", () => {
    setMode('real');
    const { container } = render(<FakeModeBadge variant="full" />);
    const chip = container.querySelector('span[aria-label="Mode: Real"]');
    expect(chip).toBeInTheDocument();
    expect(chip?.textContent).toContain('Mode: Real');
    expect(chip?.className).toContain('bg-emerald-50');
  });

  it("renders only a small amber dot when variant='dot' and mode='fake'", () => {
    setMode('fake');
    const { container } = render(<FakeModeBadge variant="dot" />);
    const dot = container.querySelector('span[role="img"]');
    expect(dot).toBeInTheDocument();
    expect(dot?.className).toContain('bg-amber-500');
    expect(dot?.textContent).toBe('');
  });

  it("renders nothing when variant='dot' and mode='real'", () => {
    setMode('real');
    const { container } = render(<FakeModeBadge variant="dot" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when variant='none'", () => {
    setMode('fake');
    const { container } = render(<FakeModeBadge variant="none" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a 'Mode: Mixed' partial chip with vendor map title when mode='mixed'", () => {
    setMode('calendar=fake,maps=real');
    const { container } = render(<FakeModeBadge />);
    const chip = container.querySelector('span[aria-label="Mode: Mixed"]');
    expect(chip).toBeInTheDocument();
    expect(chip?.textContent).toContain('Mode: Mixed');
    expect(chip?.getAttribute('title')).toBe('calendar=fake, maps=real');
  });

  it("appends className prop to the rendered chip", () => {
    setMode('fake');
    const { container } = render(<FakeModeBadge className="my-custom-class" />);
    const chip = container.querySelector('span[aria-label="Mode: Fake"]');
    expect(chip?.className).toContain('my-custom-class');
  });
});
