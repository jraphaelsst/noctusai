/**
 * Tests for the PhotoReviewGrid organ.
 *
 * Coverage:
 *   1. Loading — showSkeleton=true renders the skeleton grid, no cards.
 *   2. Refreshing — isRefreshing=true renders a non-blocking indicator
 *      WITHOUT hiding the already-rendered cards (the lying-loading-state
 *      contract: refreshing must never unmount content that exists).
 *   3. Empty — no photos, not loading → "Nenhuma foto" message.
 *   4. Comment required on ✗ — Confirmar rejeição stays disabled until text
 *      is entered; onDecidir is called with the comment on confirm.
 *   5. Approve — ✓ calls onDecidir immediately with a null comment.
 *   6. Verdict hidden without the capability — podeVerVeredito=false never
 *      renders the AI verdict block even when the photo carries `avaliacao`.
 *   7. Verdict shown with the capability — podeVerVeredito=true + avaliacao
 *      present renders score/veredito/motivo.
 *   8. falhou state — renders the reason + a retry button that calls onRetry.
 *   9. Decisions changeable — a photo already decided still shows active
 *      ✓/✗ controls that can flip the decision.
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';

import { PhotoReviewGrid } from './PhotoReviewGrid';
import type { FotoRevisao } from './hooks';

afterEach(cleanup);

function makeFoto(overrides: Partial<FotoRevisao> = {}): FotoRevisao {
  return {
    id: 'foto-1',
    url_antes: 'https://example.com/antes.jpg',
    url_depois: 'https://example.com/depois.jpg',
    comodo: 'sala',
    estado: 'aguardando_decisao',
    falha_motivo: null,
    decisao: null,
    comentario: null,
    avaliacao: null,
    ...overrides,
  };
}

// ── 1. Loading ────────────────────────────────────────────────────────────────

describe('PhotoReviewGrid: loading', () => {
  it('renders the skeleton grid and no photo cards when showSkeleton is true', () => {
    render(
      <PhotoReviewGrid
        fotos={[makeFoto()]}
        podeVerVeredito={false}
        showSkeleton
        onDecidir={vi.fn()}
      />,
    );
    expect(screen.getByRole('status', { name: 'Carregando fotos' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Aprovar foto')).not.toBeInTheDocument();
  });
});

// ── 2. Refreshing ─────────────────────────────────────────────────────────────

describe('PhotoReviewGrid: refreshing', () => {
  it('shows a non-blocking indicator without hiding existing cards', () => {
    render(
      <PhotoReviewGrid
        fotos={[makeFoto()]}
        podeVerVeredito={false}
        showSkeleton={false}
        isRefreshing
        onDecidir={vi.fn()}
      />,
    );
    expect(screen.getByText('Atualizando…')).toBeInTheDocument();
    // The card is still there — refreshing never unmounts content.
    expect(screen.getByLabelText('Aprovar foto')).toBeInTheDocument();
  });
});

// ── 3. Empty ──────────────────────────────────────────────────────────────────

describe('PhotoReviewGrid: empty', () => {
  it('renders the empty message when there are no photos', () => {
    render(
      <PhotoReviewGrid fotos={[]} podeVerVeredito={false} showSkeleton={false} onDecidir={vi.fn()} />,
    );
    expect(screen.getByText('Nenhuma foto neste lote.')).toBeInTheDocument();
  });
});

// ── 4. Comment required on ✗ ─────────────────────────────────────────────────

describe('PhotoReviewGrid: rejection requires a comment', () => {
  it('keeps the confirm button disabled until a comment is typed, then submits it', () => {
    const onDecidir = vi.fn();
    render(
      <PhotoReviewGrid
        fotos={[makeFoto()]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={onDecidir}
      />,
    );

    fireEvent.click(screen.getByLabelText('Rejeitar foto'));

    const confirmButton = screen.getByText('Confirmar rejeição');
    expect(confirmButton).toBeDisabled();

    fireEvent.click(confirmButton);
    expect(onDecidir).not.toHaveBeenCalled();

    const textarea = screen.getByLabelText('Comentário (obrigatório)');
    fireEvent.change(textarea, { target: { value: 'Céu queimado, refazer.' } });
    expect(confirmButton).not.toBeDisabled();

    fireEvent.click(confirmButton);
    expect(onDecidir).toHaveBeenCalledWith('foto-1', 'rejeitar', 'Céu queimado, refazer.');
  });

  it('does not submit a whitespace-only comment', () => {
    const onDecidir = vi.fn();
    render(
      <PhotoReviewGrid
        fotos={[makeFoto()]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={onDecidir}
      />,
    );
    fireEvent.click(screen.getByLabelText('Rejeitar foto'));
    fireEvent.change(screen.getByLabelText('Comentário (obrigatório)'), {
      target: { value: '   ' },
    });
    expect(screen.getByText('Confirmar rejeição')).toBeDisabled();
  });
});

// ── 5. Approve ────────────────────────────────────────────────────────────────

describe('PhotoReviewGrid: approve', () => {
  it('calls onDecidir immediately with a null comment', () => {
    const onDecidir = vi.fn();
    render(
      <PhotoReviewGrid
        fotos={[makeFoto()]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={onDecidir}
      />,
    );
    fireEvent.click(screen.getByLabelText('Aprovar foto'));
    expect(onDecidir).toHaveBeenCalledWith('foto-1', 'aprovar', null);
  });
});

// ── 6/7. AI verdict gating ────────────────────────────────────────────────────

describe('PhotoReviewGrid: AI verdict visibility', () => {
  const fotoComVeredito = makeFoto({
    avaliacao: { veredito: 'aprovar', score: 8, motivo: 'Boa iluminação e enquadramento.' },
  });

  it('never renders the verdict when podeVerVeredito is false, even if avaliacao is present', () => {
    render(
      <PhotoReviewGrid
        fotos={[fotoComVeredito]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Veredito IA/)).not.toBeInTheDocument();
    expect(screen.queryByText('Boa iluminação e enquadramento.')).not.toBeInTheDocument();
  });

  it('renders the verdict when podeVerVeredito is true and avaliacao is present', () => {
    render(
      <PhotoReviewGrid
        fotos={[fotoComVeredito]}
        podeVerVeredito
        showSkeleton={false}
        onDecidir={vi.fn()}
      />,
    );
    expect(screen.getByText(/Veredito IA/)).toBeInTheDocument();
    expect(screen.getByText('Boa iluminação e enquadramento.')).toBeInTheDocument();
  });

  it('renders nothing when podeVerVeredito is true but avaliacao is absent (not yet evaluated)', () => {
    render(
      <PhotoReviewGrid
        fotos={[makeFoto({ avaliacao: null })]}
        podeVerVeredito
        showSkeleton={false}
        onDecidir={vi.fn()}
      />,
    );
    expect(screen.queryByText(/Veredito IA/)).not.toBeInTheDocument();
  });
});

// ── 8. falhou state ───────────────────────────────────────────────────────────

describe('PhotoReviewGrid: falhou', () => {
  it('renders the failure reason and a retry button instead of ✓/✗', () => {
    const onRetry = vi.fn();
    render(
      <PhotoReviewGrid
        fotos={[
          makeFoto({
            estado: 'falhou',
            falha_motivo: 'Timeout no provedor de edição.',
            url_depois: null,
          }),
        ]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={vi.fn()}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Timeout no provedor de edição.');
    expect(screen.queryByLabelText('Aprovar foto')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Tentar novamente'));
    expect(onRetry).toHaveBeenCalledWith('foto-1');
  });
});

// ── 9. Decisions changeable ───────────────────────────────────────────────────

describe('PhotoReviewGrid: decisions stay changeable', () => {
  it('shows active ✓/✗ controls for an already-decided photo, and flipping calls onDecidir again', () => {
    const onDecidir = vi.fn();
    render(
      <PhotoReviewGrid
        fotos={[makeFoto({ decisao: 'aprovar' })]}
        podeVerVeredito={false}
        showSkeleton={false}
        onDecidir={onDecidir}
      />,
    );
    expect(screen.getByText('Aprovada')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Rejeitar foto'));
    fireEvent.change(screen.getByLabelText('Comentário (obrigatório)'), {
      target: { value: 'Mudei de ideia.' },
    });
    fireEvent.click(screen.getByText('Confirmar rejeição'));
    expect(onDecidir).toHaveBeenCalledWith('foto-1', 'rejeitar', 'Mudei de ideia.');
  });
});
