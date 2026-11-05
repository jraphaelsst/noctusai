/**
 * `<CreateConnectionDialog/>` — the WAHA key field is a seam: `askApiKey` (default true) for a backend that takes the key from the
 * operator; `askApiKey={false}` for a backend that provisions with its own server key (the form is the name only, and the POST body
 * carries NO `api_key`).
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

import { CreateConnectionDialog } from './CreateConnectionDialog';

afterEach(cleanup);

function renderDialog(askApiKey?: boolean) {
  const mutateAsync = vi.fn(async (body: unknown) => ({ id: 'c1', label: 'x', ...(body as object) }));
  const mutations = {
    create: { mutateAsync, reset: vi.fn(), isPending: false, isError: false, error: null },
  } as never;
  render(<CreateConnectionDialog open onClose={vi.fn()} mutations={mutations} askApiKey={askApiKey} />);
  return mutateAsync;
}

describe('CreateConnectionDialog askApiKey', () => {
  it('default: asks for the key and posts it', async () => {
    const create = renderDialog();
    fireEvent.change(await screen.findByLabelText('Nome'), { target: { value: 'Linha' } });
    fireEvent.change(screen.getByLabelText('Chave de API WAHA'), { target: { value: 'k' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar conexão' }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ label: 'Linha', api_key: 'k' }));
  });

  it('askApiKey=false: no key field, and the body is the name only', async () => {
    const create = renderDialog(false);
    expect(screen.queryByLabelText('Chave de API WAHA')).toBeNull();
    fireEvent.change(await screen.findByLabelText('Nome'), { target: { value: 'Linha' } });
    fireEvent.click(screen.getByRole('button', { name: 'Criar conexão' }));
    await waitFor(() => expect(create).toHaveBeenCalledWith({ label: 'Linha' }));
  });
});
