/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react';
import { MfaChallengeDialog } from './MfaChallengeDialog';
import { MfaChallengeHost } from './MfaChallengeHost';
import { mfaChallenge } from '../../mfaChallenge';
import { ApiError } from '../../api';
import type { MfaStatus } from './types';

afterEach(() => {
  cleanup();
  mfaChallenge.settle(false);
});

const F1 = { id: 'f1', friendly_name: 'Celular', status: 'verified' as const, created_at: '2026-10-01T00:00:00Z' };
const STATUS: MfaStatus = { enrolled: true, aal: 'aal1', factors: [F1] };

const mkApi = (status: MfaStatus = STATUS): any => ({
  get: vi.fn(async () => status),
  post: vi.fn(async () => ({ aal: 'aal2' })),
  delete: vi.fn(async () => null),
});

describe('MfaChallengeDialog', () => {
  it('shows a skeleton then the code form; submits verify', async () => {
    const api = mkApi();
    const onVerified = vi.fn();
    render(<MfaChallengeDialog open enrolled api={api} onVerified={onVerified} onCancel={() => {}} />);
    expect(screen.getByTestId('mfa-challenge-skeleton')).toBeInTheDocument();
    const input = await screen.findByLabelText('Código de 6 números');
    expect(input).toHaveAttribute('autocomplete', 'one-time-code');
    expect(input).toHaveAttribute('inputmode', 'numeric');
    const submit = screen.getByText('Confirmar');
    expect(submit).toBeDisabled();
    fireEvent.change(input, { target: { value: '12ab3456' } });
    expect(input).toHaveValue('123456');
    fireEvent.click(submit);
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/auth/mfa/verify', { factor_id: 'f1', code: '123456' }));
    await waitFor(() => expect(onVerified).toHaveBeenCalledWith({ aal: 'aal2' }));
  });

  it('announces invalid code and rate limit', async () => {
    const api = mkApi();
    render(<MfaChallengeDialog open enrolled api={api} onVerified={() => {}} onCancel={() => {}} />);
    const input = await screen.findByLabelText('Código de 6 números');
    api.post.mockRejectedValueOnce(new ApiError(400, 'x', { code: 'mfa_invalid_code' }));
    fireEvent.change(input, { target: { value: '111111' } });
    fireEvent.click(screen.getByText('Confirmar'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Código incorreto');
    api.post.mockRejectedValueOnce(new ApiError(429, 'x', undefined, 30));
    fireEvent.change(input, { target: { value: '222222' } });
    fireEvent.click(screen.getByText('Confirmar'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Aguarde 30 segundos'));
  });

  it('enrolled:false explains enrolment and shows the enroll panel', async () => {
    render(<MfaChallengeDialog open enrolled={false} api={mkApi({ enrolled: false, aal: 'aal1', factors: [] })} onVerified={() => {}} onCancel={() => {}} />);
    expect(screen.getByTestId('mfa-enroll-required')).toBeInTheDocument();
    expect(await screen.findByText('Adicionar dispositivo')).toBeInTheDocument();
  });

  it('cancel button and Escape cancel', async () => {
    const onCancel = vi.fn();
    render(<MfaChallengeDialog open enrolled api={mkApi()} onVerified={() => {}} onCancel={onCancel} />);
    await screen.findByLabelText('Código de 6 números');
    fireEvent.click(screen.getByText('Cancelar'));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });

  it('traps Tab focus inside the dialog', async () => {
    render(<MfaChallengeDialog open enrolled api={mkApi()} onVerified={() => {}} onCancel={() => {}} />);
    await screen.findByLabelText('Código de 6 números');
    screen.getByText('Cancelar').focus();
    // last enabled control is "Confirmar"? it is disabled → Cancelar is last; Tab wraps to the input.
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByLabelText('Código de 6 números')).toHaveFocus();
  });
});

describe('MfaChallengeHost', () => {
  it('renders nothing until a challenge is requested, and settles true on verify', async () => {
    const api = mkApi();
    const onVerified = vi.fn();
    render(<MfaChallengeHost />);
    expect(screen.queryByRole('dialog')).toBeNull();
    let result: Promise<boolean>;
    act(() => {
      result = mfaChallenge.request({ enrolled: true, api, onVerified });
    });
    fireEvent.change(await screen.findByLabelText('Código de 6 números'), { target: { value: '123456' } });
    fireEvent.click(screen.getByText('Confirmar'));
    await expect(result!).resolves.toBe(true);
    expect(onVerified).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('cancel settles false', async () => {
    render(<MfaChallengeHost />);
    let result: Promise<boolean>;
    act(() => {
      result = mfaChallenge.request({ enrolled: true, api: mkApi(), onVerified: () => {} });
    });
    fireEvent.click(await screen.findByText('Cancelar'));
    await expect(result!).resolves.toBe(false);
  });
});
