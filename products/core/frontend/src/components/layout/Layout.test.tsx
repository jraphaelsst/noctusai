/**
 * `visibleNavGroups` — sidebar derivation for the marketing role carve-out
 * (contract §6: "the sidebar shows only the Website group ... derive it
 * from the same NAV_GROUPS, not a second list"). A pure-function test:
 * verifies the DERIVATION without rendering the full `AppShell`/`Sidebar`/
 * `Header` tree (covered indirectly by `CoreLayout.test.tsx`'s gate tests).
 */
import { describe, expect, it } from 'vitest';
import { NAV_GROUPS, visibleNavGroups } from './Layout';

describe('visibleNavGroups', () => {
  it('returns every group for admin (and any non-marketing role)', () => {
    expect(visibleNavGroups('admin')).toBe(NAV_GROUPS);
    expect(visibleNavGroups(undefined)).toBe(NAV_GROUPS);
  });

  it('returns ONLY the website group for marketing, derived from NAV_GROUPS', () => {
    const groups = visibleNavGroups('marketing');
    expect(groups.map((g) => g.key)).toEqual(['website']);
    // Same object identity as the source items — a derivation, not a copy.
    expect(groups[0]).toBe(NAV_GROUPS.find((g) => g.key === 'website'));
  });

  it('the website group carries Documentação, Configurações and Leads', () => {
    const [website] = visibleNavGroups('marketing');
    const names = website.items.map((i) => i.name);
    expect(names).toContain('Documentação');
    expect(names).toContain('Configurações');
    expect(names).toContain('Leads');
  });
});
