/**
 * Tests for `<MotivoMoveDialog/>` — the reusable reason-for-a-move prompt
 * `onBeforeMove` handlers call from.
 */
/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

import { MotivoMoveDialog } from './MotivoMoveDialog';

afterEach(() => {
  cleanup();
});

describe('MotivoMoveDialog', () => {
  it('renders nothing when closed', () => {
    render(
      <MotivoMoveDialog open={false} title="Mover para Fechado?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('cancel calls onCancel without a motivo', () => {
    const onCancel = vi.fn();
    render(
      <MotivoMoveDialog open title="Mover para Fechado?" onConfirm={vi.fn()} onCancel={onCancel} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('confirm with an empty, non-required reason resolves motivo as undefined (not an empty string)', () => {
    const onConfirm = vi.fn();
    render(
      <MotivoMoveDialog open title="Mover para Fechado?" onConfirm={onConfirm} onCancel={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it('confirm sends the trimmed reason', () => {
    const onConfirm = vi.fn();
    render(
      <MotivoMoveDialog open title="Mover para Fechado?" onConfirm={onConfirm} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: '  aprovado pelo gerente  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    expect(onConfirm).toHaveBeenCalledWith('aprovado pelo gerente');
  });

  it('required=true disables confirm until a reason is typed', () => {
    render(
      <MotivoMoveDialog
        open
        required
        title="Mover para Cancelado?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'cliente desistiu' } });
    expect(screen.getByRole('button', { name: 'Confirmar' })).not.toBeDisabled();
  });

  it('busy disables both controls', () => {
    render(
      <MotivoMoveDialog open busy title="Mover para Fechado?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled();
  });

  it('re-opening for a NEW move clears whatever was typed for the last one', () => {
    const { rerender } = render(
      <MotivoMoveDialog open title="Mover para A?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'texto antigo' } });
    rerender(<MotivoMoveDialog open={false} title="Mover para A?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    rerender(<MotivoMoveDialog open title="Mover para B?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText('Motivo')).toHaveValue('');
  });

  it('🔴 mobile-first (R0): the panel carries the full-screen sheet utilities below `sm`', () => {
    render(
      <MotivoMoveDialog open title="Mover para Fechado?" onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    const panel = screen.getByRole('dialog');
    const classes = panel.className.split(/\s+/);
    expect(classes).toEqual(
      expect.arrayContaining([
        'max-sm:h-[100dvh]',
        'max-sm:w-screen',
        'max-sm:max-w-none',
        'max-sm:rounded-none',
        'max-sm:overflow-y-auto',
      ]),
    );
  });

  it('custom labels and placeholder are honoured', () => {
    render(
      <MotivoMoveDialog
        open
        title="Mover para Fechado?"
        placeholder="Por que este negócio fechou?"
        confirmLabel="Mover"
        cancelLabel="Voltar"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText('Por que este negócio fechou?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mover' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voltar' })).toBeInTheDocument();
  });
});
