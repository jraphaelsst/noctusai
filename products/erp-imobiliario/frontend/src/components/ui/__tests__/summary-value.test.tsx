/**
 * SummaryValue — the third mode of the lying-loading-state bug class.
 *
 * Mode A tells the lie with an empty state. Mode B tells it with a skeleton
 * unmounted over real data. This third mode tells it with a ZERO: a
 * `resumo?.field || 0` fallback renders as a real, legitimate-looking answer
 * before its query has ever resolved.
 *
 * Proves the three states this component exists to distinguish:
 *   1. not-yet-loaded  -> no zero/value rendered, a skeleton placeholder instead
 *   2. server-returned-zero -> the real "0" renders (never mistaken for #1)
 *   3. refetch-with-data -> the previous value stays mounted, no skeleton
 *
 * KB § PATTERNS/frontend/lying-loading-state.md
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { SummaryValue } from '../summary-value';

afterEach(() => {
  cleanup();
});

describe('SummaryValue', () => {
  it('state 1 — not-yet-loaded: renders a skeleton, never a "0"', () => {
    const { container } = render(
      React.createElement(SummaryValue, { notArrived: true }, '0'),
    );

    // The literal "0" must not be in the document — that is exactly the
    // false-zero lie this component exists to prevent.
    expect(screen.queryByText('0')).toBeNull();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('state 2 — server-returned-zero: renders the real "0", not a skeleton', () => {
    const { container } = render(
      React.createElement(SummaryValue, { notArrived: false }, '0'),
    );

    // A genuine zero from the server IS data — it must render, not be
    // mistaken for "not arrived yet". This is the whole point: notArrived
    // is driven by isPending && !data, never by the VALUE being falsy.
    expect(screen.getByText('0')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('state 3 — refetch-with-data: the previous value stays mounted, no skeleton re-arms', () => {
    // isFetching=true (refetch in flight) must never flip notArrived back
    // to true once data has arrived once — call-site contract is
    // `notArrived = query.isPending && !query.data`, which is false here.
    const { container, rerender } = render(
      React.createElement(SummaryValue, { notArrived: false }, 'R$ 42,00'),
    );
    expect(screen.getByText('R$ 42,00')).toBeTruthy();

    // Simulate a background refetch: notArrived recomputed at the call site
    // stays false (isPending is false once resolved once), value unchanged
    // until the refetch resolves.
    rerender(React.createElement(SummaryValue, { notArrived: false }, 'R$ 42,00'));

    expect(screen.getByText('R$ 42,00')).toBeTruthy();
    expect(container.querySelector('.animate-pulse')).toBeNull();
  });

  it('honors a custom className on the skeleton placeholder', () => {
    const { container } = render(
      React.createElement(SummaryValue, { notArrived: true, className: 'h-3 w-16' }, '0'),
    );
    const skeleton = container.querySelector('.animate-pulse');
    expect(skeleton).toBeTruthy();
    expect(skeleton?.className).toContain('h-3');
    expect(skeleton?.className).toContain('w-16');
  });
});
