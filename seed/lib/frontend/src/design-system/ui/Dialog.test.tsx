/**
 * Tests for `<Dialog/>`'s close gestures.
 *
 * The regression that motivated the press-origin tracking: on the academia
 * "interessados" popup, a visitor dragged across the `nome` field to select
 * their text and released the button OUTSIDE the panel. The browser fires
 * `click` on the nearest common ancestor — the backdrop — so the old
 * `onClick`-only check read that as "clicked outside", closed the dialog and
 * threw away everything they had typed. A close now needs BOTH ends of the
 * gesture on the backdrop.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { Dialog } from './Dialog';

afterEach(cleanup);

function renderDialog() {
  const onClose = vi.fn();
  render(
    <Dialog open onClose={onClose} title="Interesse">
      <input aria-label="nome" defaultValue="Gilson" />
    </Dialog>,
  );
  const backdrop = screen.getByRole('dialog');
  const field = screen.getByLabelText('nome');
  return { onClose, backdrop, field };
}

describe('Dialog close gestures', () => {
  it('closes when the press both starts and ends on the backdrop', () => {
    const { onClose, backdrop } = renderDialog();

    fireEvent.mouseDown(backdrop);
    fireEvent.click(backdrop);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT close when a drag starts inside the panel and releases on the backdrop', () => {
    const { onClose, backdrop, field } = renderDialog();

    // select-all drag: press inside the field, release over the backdrop —
    // the browser still fires `click` on the backdrop (common ancestor).
    fireEvent.mouseDown(field);
    fireEvent.mouseUp(backdrop);
    fireEvent.click(backdrop);

    expect(onClose).not.toHaveBeenCalled();
  });

  it('does not close on a plain click inside the panel', () => {
    const { onClose, field } = renderDialog();

    fireEvent.mouseDown(field);
    fireEvent.click(field);

    expect(onClose).not.toHaveBeenCalled();
  });

  it('still closes on Escape', () => {
    const { onClose } = renderDialog();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('Dialog focus management', () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>Abrir</button>
        <Dialog open={open} onClose={() => setOpen(false)} title="Detalhes">
          <button>Primeiro</button>
          <button>Segundo</button>
        </Dialog>
      </>
    );
  }

  it('moves focus in, traps Tab, and returns focus to the opener on Esc', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Abrir' });
    await user.click(opener);

    const first = screen.getByRole('button', { name: 'Primeiro' });
    const second = screen.getByRole('button', { name: 'Segundo' });
    expect(first).toHaveFocus();

    await user.tab();
    expect(second).toHaveFocus();
    await user.tab(); // wraps, never leaves the dialog
    expect(first).toHaveFocus();
    await user.tab({ shift: true });
    expect(second).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });
});
