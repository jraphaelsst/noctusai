/**
 * Upload refusal organ — every refusal (client-side type/size, server 4xx,
 * server 5xx / transport, a failed `useRetryableAction` outcome) becomes
 * `erro` state with the file name, and `<UploadErro>` draws it.
 * KB § PATTERNS/frontend/silent-refusal.md.
 */
import { act, cleanup, fireEvent, render, renderHook, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './api';
import { UploadErro } from './components/UploadErro';
import { motivoDaRecusa, recusaDeUpload, textoDaRecusa, useUploadDocumento } from './upload-refusal';

afterEach(cleanup);

const pdf = (name = 'contrato.pdf') => new File(['%PDF'], name, { type: 'application/pdf' });

describe('motivoDaRecusa', () => {
  it('a 4xx shows the SERVER words (from the body), not the "[422]" prefix', () => {
    const err = new ApiError(422, 'tipo inválido', { error: { message: 'Arquivo acima de 20 MB.' } });
    expect(motivoDaRecusa(err)).toBe('Arquivo acima de 20 MB.');
  });

  it('a 4xx without a body falls back to its own message, prefix stripped', () => {
    expect(motivoDaRecusa(new ApiError(400, 'Tipo de documento reservado.'))).toBe('Tipo de documento reservado.');
  });

  it('a 5xx / transport failure shows the reason class, never the raw text', () => {
    expect(motivoDaRecusa(new ApiError(502, '<html>Bad Gateway</html>'))).toBe('O servidor está instável no momento.');
    expect(motivoDaRecusa(new ApiError(null, 'fetch failed', undefined, null, 'network'))).toBe('Sem conexão com o servidor.');
  });

  it('a plain Error with a status (hand-rolled multipart) — 5xx class, 4xx message', () => {
    expect(motivoDaRecusa(Object.assign(new Error('boom'), { status: 503 }))).toBe('O servidor está instável no momento.');
    expect(motivoDaRecusa(Object.assign(new Error('[413] Arquivo grande demais.'), { status: 413 }))).toBe('Arquivo grande demais.');
  });

  it('recusaDeUpload carries the file name, status and key', () => {
    const r = recusaDeUpload(pdf('rg.pdf'), new ApiError(400, 'não'), 'linha-1');
    expect(r).toEqual({ arquivo: 'rg.pdf', mensagem: 'não', status: 400, origem: 'servidor', chave: 'linha-1' });
    expect(textoDaRecusa(r)).toBe('"rg.pdf" não foi enviado: não');
  });
});

describe('useUploadDocumento', () => {
  it('a server refusal becomes erro (never a rejection); the next attempt clears it', async () => {
    const send = vi.fn().mockRejectedValueOnce(new ApiError(400, 'Tipo reservado.')).mockResolvedValueOnce({ id: 'd1' });
    const { result } = renderHook(() => useUploadDocumento((file: File) => send(file)));
    let r1: unknown;
    await act(async () => {
      r1 = await result.current.enviar(pdf());
    });
    expect(r1).toMatchObject({ ok: false });
    expect(result.current.erro).toMatchObject({ arquivo: 'contrato.pdf', mensagem: 'Tipo reservado.', status: 400, origem: 'servidor' });
    let r2: unknown;
    await act(async () => {
      r2 = await result.current.enviar(pdf());
    });
    expect(r2).toEqual({ ok: true, valor: { id: 'd1' } });
    expect(result.current.erro).toBeNull();
  });

  it('a type the browser KNOWS and is not accepted is refused on screen, without sending (F75b)', async () => {
    const send = vi.fn();
    const { result } = renderHook(() => useUploadDocumento(send, { aceitos: ['application/pdf'] }));
    await act(async () => {
      await result.current.enviar(new File(['x'], 'foto.png', { type: 'image/png' }));
    });
    expect(send).not.toHaveBeenCalled();
    expect(result.current.erro).toMatchObject({ arquivo: 'foto.png', origem: 'cliente', mensagem: 'formato image/png não aceito' });
  });

  it('an indeterminate type (WhatsApp/Drive, no extension) always goes to the server sniff', async () => {
    const send = vi.fn().mockResolvedValue('ok');
    const { result } = renderHook(() => useUploadDocumento(send, { aceitos: ['application/pdf'] }));
    await act(async () => {
      await result.current.enviar(new File(['x'], 'arquivo', { type: '' }));
      await result.current.enviar(new File(['x'], 'arquivo2', { type: 'application/octet-stream' }));
    });
    expect(send).toHaveBeenCalledTimes(2);
    expect(result.current.erro).toBeNull();
  });

  it('a size over maxBytes is refused client-side with the file name', async () => {
    const send = vi.fn();
    const { result } = renderHook(() => useUploadDocumento(send, { maxBytes: 1024 * 1024 }));
    const big = new File([new Uint8Array(2 * 1024 * 1024)], 'grande.pdf', { type: 'application/pdf' });
    await act(async () => {
      await result.current.enviar(big);
    });
    expect(send).not.toHaveBeenCalled();
    expect(result.current.erro?.mensagem).toBe('o arquivo passa de 1 MB');
  });

  it('a failed useRetryableAction outcome (which never rejects) is a refusal, not a success', async () => {
    const send = vi.fn().mockResolvedValue({ ok: false, error: new ApiError(422, 'CPF ilegível.'), attempts: 1 });
    const { result } = renderHook(() => useUploadDocumento(send));
    let r: unknown;
    await act(async () => {
      r = await result.current.enviar(pdf());
    });
    expect(r).toMatchObject({ ok: false });
    expect(result.current.erro?.mensagem).toBe('CPF ilegível.');
  });

  it('enviarEm tags the refusal with the row key; recusar records a caller-side refusal', async () => {
    const send = vi.fn().mockRejectedValue(new Error('Linha inválida.'));
    const { result } = renderHook(() => useUploadDocumento(send));
    await act(async () => {
      await result.current.enviarEm('serasa', pdf());
    });
    expect(result.current.erro?.chave).toBe('serasa');
    act(() => {
      result.current.recusar(pdf('x.pdf'), 'escolha o tipo antes.');
    });
    expect(result.current.erro).toMatchObject({ arquivo: 'x.pdf', mensagem: 'escolha o tipo antes.', origem: 'cliente' });
    act(() => result.current.limpar());
    expect(result.current.erro).toBeNull();
  });

  it('enviando follows the in-flight upload', async () => {
    let resolve!: (v: unknown) => void;
    const send = vi.fn(() => new Promise((r) => (resolve = r)));
    const { result } = renderHook(() => useUploadDocumento(send));
    let p!: Promise<unknown>;
    act(() => {
      p = result.current.enviar(pdf());
    });
    expect(result.current.enviando).toBe(true);
    await act(async () => {
      resolve('ok');
      await p;
    });
    expect(result.current.enviando).toBe(false);
  });
});

describe('<UploadErro>', () => {
  const erro = { arquivo: 'rg.pdf', mensagem: 'Tipo reservado.', status: 400, origem: 'servidor' as const, chave: 'a' };

  it('renders nothing without a refusal', () => {
    const { container } = render(<UploadErro erro={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders the file name + reason as an alert, and dismisses', () => {
    const onDismiss = vi.fn();
    render(<UploadErro erro={erro} onDismiss={onDismiss} />);
    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('"rg.pdf" não foi enviado: Tipo reservado.');
    fireEvent.click(screen.getByTestId('upload-erro-dispensar'));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('with `chave`, shows only its own row', () => {
    const { rerender } = render(<UploadErro erro={erro} chave="b" />);
    expect(screen.queryByRole('alert')).toBeNull();
    rerender(<UploadErro erro={erro} chave="a" />);
    expect(screen.getByRole('alert')).toBeTruthy();
  });
});
