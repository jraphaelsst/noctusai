import * as React from 'react';
import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import { ConfirmProvider, useConfirm } from './ConfirmProvider';
import type { ConfirmFn } from './ConfirmProvider';

let confirmFn: ConfirmFn;
function Grab() {
  confirmFn = useConfirm();
  return null;
}
function setup() {
  return render(
    <ConfirmProvider>
      <Grab />
    </ConfirmProvider>,
  );
}

describe('useConfirm', () => {
  it('resolves true on confirm, with pt-BR default labels', async () => {
    setup();
    let p!: Promise<boolean>;
    act(() => {
      p = confirmFn({ title: 'Excluir?' });
    });
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await expect(p).resolves.toBe(true);
    expect(screen.queryByTestId('confirm-dialog')).toBeNull();
  });

  it('resolves false on cancel', async () => {
    setup();
    let p!: Promise<boolean>;
    act(() => {
      p = confirmFn({ title: 'Excluir?', cancelLabel: 'Não', confirmLabel: 'Sim' });
    });
    fireEvent.click(screen.getByRole('button', { name: 'Não' }));
    await expect(p).resolves.toBe(false);
  });

  it('resolves false on Escape', async () => {
    setup();
    let p!: Promise<boolean>;
    act(() => {
      p = confirmFn({ title: 'Excluir?' });
    });
    fireEvent.keyDown(document, { key: 'Escape' });
    await expect(p).resolves.toBe(false);
  });

  it('renders description and focuses confirm (default) / cancel (danger)', async () => {
    setup();
    act(() => {
      void confirmFn({ title: 'A', description: 'Detalhe aqui' });
    });
    expect(screen.getByText('Detalhe aqui')).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Confirmar' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    act(() => {
      void confirmFn({ title: 'B', tone: 'danger' });
    });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancelar' }));
  });

  it('traps Tab between the two buttons', () => {
    setup();
    act(() => {
      void confirmFn({ title: 'A' });
    });
    const confirmBtn = screen.getByRole('button', { name: 'Confirmar' });
    confirmBtn.focus();
    fireEvent.keyDown(confirmBtn, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancelar' }));
    fireEvent.keyDown(document.activeElement!, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(confirmBtn);
  });

  it('queues sequential/concurrent confirms in order', async () => {
    setup();
    let p1!: Promise<boolean>;
    let p2!: Promise<boolean>;
    act(() => {
      p1 = confirmFn({ title: 'Primeiro' });
      p2 = confirmFn({ title: 'Segundo' });
    });
    expect(screen.getByRole('alertdialog').getAttribute('aria-label')).toBe('Primeiro');
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    await expect(p1).resolves.toBe(true);
    expect(screen.getByRole('alertdialog').getAttribute('aria-label')).toBe('Segundo');
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await expect(p2).resolves.toBe(false);
  });

  it('rejects at call time outside a provider (no silent window.confirm fallback)', async () => {
    let fn!: ConfirmFn;
    function Bare() {
      fn = useConfirm();
      return null;
    }
    render(<Bare />);
    await expect(fn({ title: 'x' })).rejects.toThrow(/ConfirmProvider/);
  });
});
