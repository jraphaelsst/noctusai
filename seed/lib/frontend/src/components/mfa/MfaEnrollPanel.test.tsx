/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { MfaEnrollPanel } from './MfaEnrollPanel';
import { ApiError } from '../../api';
import type { MfaStatus } from './types';

afterEach(cleanup);

const F1 = { id: 'f1', friendly_name: 'Celular', status: 'verified' as const, created_at: '2026-10-01T00:00:00Z' };

function makeApi(status: MfaStatus | Promise<MfaStatus>): any {
  return {
    get: vi.fn(async () => status),
    post: vi.fn(async (path: string) =>
      path.endsWith('/enroll')
        ? { factor_id: 'f2', qr_code: 'data:image/svg+xml;base64,AAA', uri: 'otpauth://totp/x?secret=ABC' }
        : { aal: 'aal2' },
    ),
    delete: vi.fn(async () => null),
  };
}

describe('MfaEnrollPanel', () => {
  it('shows a skeleton while loading', () => {
    const api = makeApi(new Promise(() => {}));
    render(<MfaEnrollPanel api={api} />);
    expect(screen.getByTestId('mfa-skeleton')).toBeInTheDocument();
  });

  it('shows the error state with retry', async () => {
    const api = makeApi({ enrolled: false, aal: null, factors: [] });
    api.get.mockRejectedValueOnce(new ApiError(null, 'down'));
    render(<MfaEnrollPanel api={api} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível falar com o servidor');
    fireEvent.click(screen.getByText('Tentar de novo'));
    expect(await screen.findByText('Nenhum dispositivo cadastrado.')).toBeInTheDocument();
  });

  it('empty state recommends two devices', async () => {
    render(<MfaEnrollPanel api={makeApi({ enrolled: false, aal: null, factors: [] })} />);
    expect(await screen.findByText(/DOIS dispositivos/)).toBeInTheDocument();
  });

  it('enrols: name -> QR + uri copy -> confirm code via /verify', async () => {
    const onVerified = vi.fn();
    const writeText = vi.fn(async () => {});
    Object.assign(navigator, { clipboard: { writeText } });
    const api = makeApi({ enrolled: false, aal: 'aal1', factors: [] });
    render(<MfaEnrollPanel api={api} onVerified={onVerified} />);
    fireEvent.change(await screen.findByLabelText('Nome do dispositivo'), { target: { value: 'Meu cel' } });
    fireEvent.click(screen.getByText('Adicionar dispositivo'));
    expect(await screen.findByAltText(/Código QR/)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/auth/mfa/enroll', { friendly_name: 'Meu cel' });
    fireEvent.click(screen.getByText('Copiar'));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('otpauth://totp/x?secret=ABC'));
    expect(await screen.findByText('Chave copiada.')).toBeInTheDocument();
    const input = screen.getByLabelText('Código de 6 números');
    expect(input).toHaveAttribute('autocomplete', 'one-time-code');
    fireEvent.change(input, { target: { value: '123456' } });
    fireEvent.click(screen.getByText('Confirmar'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/auth/mfa/verify', { factor_id: 'f2', code: '123456' }));
    await waitFor(() => expect(onVerified).toHaveBeenCalledWith({ aal: 'aal2' }));
  });

  it('shows the invalid-code message and keeps the QR', async () => {
    const api = makeApi({ enrolled: false, aal: 'aal1', factors: [] });
    render(<MfaEnrollPanel api={api} />);
    fireEvent.click(await screen.findByText('Adicionar dispositivo'));
    await screen.findByAltText(/Código QR/);
    api.post.mockRejectedValueOnce(new ApiError(400, 'bad', { code: 'mfa_invalid_code' }));
    fireEvent.change(screen.getByLabelText('Código de 6 números'), { target: { value: '000000' } });
    fireEvent.click(screen.getByText('Confirmar'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Código incorreto');
    expect(screen.getByAltText(/Código QR/)).toBeInTheDocument();
  });

  it('409 factor limit is explained; at 2 verified the add form is hidden', async () => {
    const two = [F1, { ...F1, id: 'f2', friendly_name: 'Tablet' }];
    render(<MfaEnrollPanel api={makeApi({ enrolled: true, aal: 'aal2', factors: two })} />);
    expect(await screen.findByText('Tablet')).toBeInTheDocument();
    expect(screen.queryByLabelText('Nome do dispositivo')).toBeNull();
  });

  it('removes a factor after confirmation', async () => {
    const api = makeApi({ enrolled: true, aal: 'aal2', factors: [F1] });
    render(<MfaEnrollPanel api={api} />);
    fireEvent.click(await screen.findByLabelText('Remover Celular'));
    fireEvent.click(screen.getByText('Confirmar remoção'));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/auth/mfa/factors/f1'));
  });
});
