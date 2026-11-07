import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ProductIcon, resolveProductIcon } from './product-icon';

const MIGRATIONS = join(__dirname, '../../../backend/migrations');

/** Every icone written by a core migration (INSERT row before url_base, or UPDATE ... SET icone). */
function migrationIcones(): Array<{ file: string; icone: string }> {
  const out: Array<{ file: string; icone: string }> = [];
  for (const file of readdirSync(MIGRATIONS).filter((f) => f.endsWith('.sql'))) {
    const sql = readFileSync(join(MIGRATIONS, file), 'utf8');
    for (const m of sql.matchAll(/'([^']*)'\s*,\s*'https?:\/\//g)) out.push({ file, icone: m[1] });
    for (const m of sql.matchAll(/SET\s+icone\s*=\s*'([^']*)'/gi)) out.push({ file, icone: m[1] });
  }
  return out;
}

/** Seeded then deleted by 033_retire_consolidated_products.sql — the rows no longer exist, so their icons need not render. */
const RETIRED_SEED_FILES = new Set(['013_seed_media_scheduling_product.sql', '028_seed_imobi_scheduling_product.sql']);

const isEmoji = (v: string) => [...v].some((c) => (c.codePointAt(0) ?? 0) > 127);

describe('ProductIcon registry', () => {
  it('resolves every icone seeded in core migrations to a real icon', () => {
    const rows = migrationIcones();
    expect(rows.length).toBeGreaterThan(5);
    const unresolved = rows.filter((r) => !RETIRED_SEED_FILES.has(r.file) && r.icone !== '' && !isEmoji(r.icone) && !resolveProductIcon(r.icone));
    expect(unresolved).toEqual([]);
  });

  it.each(['camera', 'dumbbell', 'Camera', 'Dumbbell'])('renders stored name %s as its own icon', (name) => {
    expect(resolveProductIcon(name)).toBeDefined();
    const { container } = render(<ProductIcon name={name} />);
    expect(container.querySelector('svg')?.getAttribute('class')).not.toContain('lucide-box');
  });

  it('falls back to Box for an unknown name', () => {
    const { container } = render(<ProductIcon name="no-such-icon" />);
    expect(container.querySelector('svg')?.getAttribute('class')).toContain('lucide-box');
  });
});
