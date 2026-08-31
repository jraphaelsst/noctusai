/**
 * The organ's contract. These assertions are the reason it can be trusted
 * as the ONE detail modal: the states a consumer would otherwise re-invent
 * per surface (loading, error, not-found, empty-value, non-applicable
 * field) each behave one documented way.
 *
 * Tested here in the seed's own vitest, never from a product's — a product
 * suite renders a SECOND React copy against the seed's, which fails on
 * hooks. See `KB § PATTERNS/compliance/testing.md`.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EntityDetailDialog } from './EntityDetailDialog';
import type { DetailSection } from './EntityDetailDialog';

const SECTIONS: DetailSection[] = [
  {
    fields: [
      { label: 'Contato', value: '+5511994573387' },
      { label: 'Origem', value: 'Meta Ads' },
      { label: 'Observações', value: null },
    ],
  },
  {
    title: 'Campanha',
    fields: [{ label: 'Formulário', value: 'form-1' }],
  },
];

function renderDialog(props: Partial<React.ComponentProps<typeof EntityDetailDialog>> = {}) {
  return render(
    <EntityDetailDialog
      open
      onClose={() => {}}
      title="Maria Silva"
      sections={SECTIONS}
      {...props}
    />,
  );
}

describe('rendering the record', () => {
  it('renders title, fields and section headings', () => {
    renderDialog();
    expect(screen.getByText('Maria Silva')).toBeInTheDocument();
    expect(screen.getByText('Contato')).toBeInTheDocument();
    expect(screen.getByText('+5511994573387')).toBeInTheDocument();
    expect(screen.getByText('Campanha')).toBeInTheDocument();
  });

  it('renders an em-dash for an empty value instead of dropping the row', () => {
    // A visibly empty field says "we hold no value here"; a missing row
    // says nothing at all, and the user cannot tell the difference between
    // "blank" and "this modal forgot to show it".
    renderDialog();
    expect(screen.getByText('Observações')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('drops a hidden field entirely — that is what "does not apply" means', () => {
    renderDialog({
      sections: [{ fields: [{ label: 'Corretor', value: 'Ana', hidden: true }] }],
    });
    expect(screen.queryByText('Corretor')).not.toBeInTheDocument();
  });

  it('drops a section whose fields are all hidden rather than showing a bare heading', () => {
    renderDialog({
      sections: [
        { title: 'Campanha', fields: [{ label: 'Formulário', value: 'x', hidden: true }] },
      ],
    });
    expect(screen.queryByText('Campanha')).not.toBeInTheDocument();
  });

  it('renders badges and the explanatory note', () => {
    renderDialog({
      badges: [{ label: 'Revisar', variant: 'destructive' }],
      note: 'Origem não reconhecida',
    });
    expect(screen.getByText('Revisar')).toBeInTheDocument();
    expect(screen.getByText('Origem não reconhecida')).toBeInTheDocument();
  });

  it('renders nothing when closed', () => {
    renderDialog({ open: false });
    expect(screen.queryByText('Maria Silva')).not.toBeInTheDocument();
  });
});

describe('async states — the reason a kanban card can open this safely', () => {
  it('shows a skeleton, not an empty grid, while fetching (no sections yet)', () => {
    // A card carries a PROJECTION of the record. Rendering its missing
    // columns as blank fields would assert "these are empty" about data
    // that simply has not arrived. `sections: []` is the genuine
    // first-open case — nothing has arrived yet.
    renderDialog({ isLoading: true, sections: [] });
    expect(screen.getByTestId('entity-detail-loading')).toBeInTheDocument();
    expect(screen.queryByText('Contato')).not.toBeInTheDocument();
  });

  // REGRESSION for the refetch-unmount bug (`KB § PATTERNS/frontend/
  // lying-loading-state.md`). Reported symptom: edit one field on a record
  // whose detail dialog is open, the fetch that reloads the record flips
  // `isLoading` true again, and the whole 8-row `SkeletonGrid` replaced the
  // already-populated field grid while the dialog's height collapsed and
  // came back. Before this fix `isLoading` alone gated the skeleton; now it
  // is scoped to "no visible sections yet", so a background refetch of an
  // already-open record keeps the fields on screen.
  it('REGRESSION: keeps showing already-loaded fields when isLoading flips true again (background refetch)', () => {
    renderDialog({ isLoading: true }); // default SECTIONS — data already present
    expect(screen.getByText('Contato')).toBeInTheDocument();
    expect(screen.getByText('+5511994573387')).toBeInTheDocument();
    expect(screen.queryByTestId('entity-detail-loading')).not.toBeInTheDocument();
  });

  it('error wins over loading and over sections', () => {
    renderDialog({ isLoading: true, error: 'Falha ao carregar' });
    expect(screen.getByText('Falha ao carregar')).toBeInTheDocument();
    expect(screen.queryByTestId('entity-detail-loading')).not.toBeInTheDocument();
    expect(screen.queryByText('Contato')).not.toBeInTheDocument();
  });

  it('not-found is distinct from empty', () => {
    renderDialog({ notFound: true });
    expect(screen.getByTestId('entity-detail-dialog-not-found')).toBeInTheDocument();
    expect(screen.queryByText('Contato')).not.toBeInTheDocument();
  });
});

describe('actions', () => {
  it('fires the callback and never mutates on its own', () => {
    const onEdit = vi.fn();
    renderDialog({ actions: [{ label: 'Editar', onClick: onEdit }] });
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    expect(onEdit).toHaveBeenCalledTimes(1);
  });

  it('respects disabled', () => {
    const onEdit = vi.fn();
    renderDialog({ actions: [{ label: 'Editar', onClick: onEdit, disabled: true }] });
    fireEvent.click(screen.getByRole('button', { name: 'Editar' }));
    expect(onEdit).not.toHaveBeenCalled();
  });

  it('renders start-aligned actions apart from end-aligned ones', () => {
    renderDialog({
      actions: [
        { label: 'Excluir', onClick: () => {}, variant: 'destructive', align: 'start' },
        { label: 'Editar', onClick: () => {} },
      ],
    });
    expect(screen.getByRole('button', { name: 'Excluir' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Editar' })).toBeInTheDocument();
  });

  it('omits the footer entirely when there are no actions', () => {
    renderDialog();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('closing', () => {
  it('escape closes', () => {
    const onClose = vi.fn();
    renderDialog({ onClose });
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('a backdrop click closes, a click inside the panel does not', () => {
    const onClose = vi.fn();
    renderDialog({ onClose });
    fireEvent.click(screen.getByText('Maria Silva'));
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('dialog'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
