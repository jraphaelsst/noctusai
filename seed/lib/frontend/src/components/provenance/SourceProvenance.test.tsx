import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MirrorOverrideValue, SourceBadge, formatSyncedAgo } from './SourceProvenance';

const NOW = new Date('2026-11-03T12:00:00Z');

describe('formatSyncedAgo', () => {
  it('is coarse and null-safe', () => {
    expect(formatSyncedAgo(null, NOW)).toBeNull();
    expect(formatSyncedAgo('lixo', NOW)).toBeNull();
    expect(formatSyncedAgo('2026-11-03T11:59:40Z', NOW)).toBe('agora');
    expect(formatSyncedAgo('2026-11-03T11:30:00Z', NOW)).toBe('há 30 min');
    expect(formatSyncedAgo('2026-11-03T10:00:00Z', NOW)).toBe('há 2 h');
    expect(formatSyncedAgo('2026-11-02T10:00:00Z', NOW)).toBe('há 1 dia');
    expect(formatSyncedAgo('2026-10-30T12:00:00Z', NOW)).toBe('há 4 dias');
  });
});

describe('SourceBadge', () => {
  it('names the source, the freshness and why it is read-only', () => {
    render(<SourceBadge source="Vista" syncedAt="2026-11-03T10:00:00Z" now={NOW} />);
    const b = screen.getByTestId('source-badge');
    expect(b).toHaveTextContent('Vista');
    expect(b).toHaveTextContent('há 2 h');
    expect(b.getAttribute('title')).toMatch(/Somente leitura/);
  });

  it('omits freshness when the sync time is unknown', () => {
    render(<SourceBadge source="Vista" />);
    expect(screen.getByTestId('source-badge').textContent).toBe('Vista');
  });
});

describe('MirrorOverrideValue', () => {
  it('shows both when they differ', () => {
    render(<MirrorOverrideValue mirror="120 m²" owned="115 m²" />);
    expect(screen.getByTestId('mirror-value')).toHaveTextContent('120 m²');
    expect(screen.getByTestId('owned-value')).toHaveTextContent('115 m²');
  });

  it('shows one value when they agree or only one exists', () => {
    const { rerender, container } = render(<MirrorOverrideValue mirror="120" owned="120" />);
    expect(container.textContent).toBe('120');
    rerender(<MirrorOverrideValue mirror="120" owned={null} />);
    expect(container.textContent).toBe('120');
    rerender(<MirrorOverrideValue mirror={null} owned="115" />);
    expect(container.textContent).toBe('115');
  });

  it('renders nothing when neither exists', () => {
    const { container } = render(<MirrorOverrideValue />);
    expect(container.firstChild).toBeNull();
  });
});
