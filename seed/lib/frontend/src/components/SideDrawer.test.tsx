import * as React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { ConfirmProvider } from './confirm';
import { SideDrawer, SIDE_DRAWER_LEAVE_MESSAGE } from './SideDrawer';

function setup(props: Partial<React.ComponentProps<typeof SideDrawer>> = {}) {
  const onOpenChange = vi.fn();
  render(
    <ConfirmProvider>
      <SideDrawer open onOpenChange={onOpenChange} title="Configurar" {...props}>
        <input aria-label="campo" />
      </SideDrawer>
    </ConfirmProvider>,
  );
  return onOpenChange;
}

describe('SideDrawer', () => {
  it('renders dialog, title, description, chip, body and footer; closed renders nothing', () => {
    setup({ description: 'desc', statusChip: <span>Ativo</span>, footer: <button>Salvar</button> });
    expect(screen.getByRole('dialog', { name: 'Configurar' })).toBeTruthy();
    expect(screen.getByText('desc')).toBeTruthy();
    expect(screen.getByText('Ativo')).toBeTruthy();
    expect(screen.getByTestId('side-drawer-footer')).toBeTruthy();
  });

  it('closes via X, Esc and backdrop when clean', async () => {
    const o = setup();
    fireEvent.click(screen.getByLabelText('Fechar'));
    fireEvent.keyDown(document, { key: 'Escape' });
    const bd = screen.getByTestId('side-drawer-backdrop');
    fireEvent.mouseDown(bd);
    fireEvent.click(bd);
    await waitFor(() => expect(o).toHaveBeenCalledTimes(3));
    expect(o).toHaveBeenCalledWith(false);
  });

  it('dirty: asks with the default copy; the confirm is clickable; confirm closes', async () => {
    const o = setup({ dirty: true });
    fireEvent.click(screen.getByLabelText('Fechar'));
    expect(await screen.findByText(SIDE_DRAWER_LEAVE_MESSAGE)).toBeTruthy();
    expect(o).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }));
    await waitFor(() => expect(o).toHaveBeenCalledWith(false));
  });

  it('dirty: "Continuar editando" keeps it open; Esc inside the confirm does not stack a second one', async () => {
    const o = setup({ dirty: true });
    fireEvent.keyDown(document, { key: 'Escape' });
    await screen.findByTestId('confirm-dialog');
    fireEvent.keyDown(document, { key: 'Escape' }); // closes the confirm only
    await waitFor(() => expect(screen.queryByTestId('confirm-dialog')).toBeNull());
    expect(o).not.toHaveBeenCalled();
    expect(screen.getByTestId('side-drawer')).toBeTruthy();
  });

  it('confirm dialog sits above the drawer in stacking order', async () => {
    setup({ dirty: true });
    fireEvent.click(screen.getByLabelText('Fechar'));
    const confirmRoot = (await screen.findByTestId('confirm-dialog')).closest('[role="dialog"]')!;
    expect(confirmRoot.className).toContain('z-50');
    expect(screen.getByTestId('side-drawer-backdrop').className).toContain('z-40');
  });

  it('custom confirm copy; Voltar guarded then calls onBack', async () => {
    const onBack = vi.fn();
    setup({ dirty: true, onBack, confirmMessage: 'Descartar?' });
    fireEvent.click(screen.getByRole('button', { name: /Voltar/ }));
    expect(await screen.findByText('Descartar?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Sair' }));
    await waitFor(() => expect(onBack).toHaveBeenCalled());
  });

  it('footer render-prop exposes a dirty-guarded requestClose', async () => {
    const o = setup({ dirty: true, footer: ({ requestClose }) => <button onClick={requestClose}>Cancelar</button> });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await screen.findByText(SIDE_DRAWER_LEAVE_MESSAGE);
    expect(o).not.toHaveBeenCalled();
  });

  it('traps Tab inside the panel and applies the width variant', () => {
    setup({ width: 'lg', footer: <button>Salvar</button> });
    expect(screen.getByTestId('side-drawer').className).toContain('max-w-lg');
    const salvar = screen.getByRole('button', { name: 'Salvar' });
    salvar.focus();
    fireEvent.keyDown(salvar, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByLabelText('Fechar'));
  });
});
