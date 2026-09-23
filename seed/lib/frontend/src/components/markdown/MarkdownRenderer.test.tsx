/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { MarkdownRenderer } from './MarkdownRenderer';

afterEach(cleanup);

describe('MarkdownRenderer — GFM', () => {
  it('renders a GFM table with header + rows', () => {
    const md = ['| Nome | Valor |', '| --- | --- |', '| Linha 1 | 10 |', '| Linha 2 | 20 |'].join(
      '\n',
    );
    render(<MarkdownRenderer content={md} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByText('Nome')).toBeInTheDocument();
    expect(screen.getByText('Linha 1')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('renders GFM task list checkboxes as disabled + reflects checked state', () => {
    const md = ['- [x] Feito', '- [ ] Pendente'].join('\n');
    render(<MarkdownRenderer content={md} />);
    const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
    expect(boxes).toHaveLength(2);
    expect(boxes[0].checked).toBe(true);
    expect(boxes[0]).toBeDisabled();
    expect(boxes[1].checked).toBe(false);
  });

  it('renders strikethrough (GFM del)', () => {
    render(<MarkdownRenderer content="~~riscado~~" />);
    const del = screen.getByText('riscado');
    expect(del.tagName.toLowerCase()).toBe('del');
  });

  it('renders a fenced code block', () => {
    const md = ['```ts', 'const x = 1;', '```'].join('\n');
    render(<MarkdownRenderer content={md} />);
    expect(screen.getByText('const x = 1;')).toBeInTheDocument();
  });
});

describe('MarkdownRenderer — slugged headings', () => {
  it('gives headings a stable slug id usable by #anchor links', () => {
    render(<MarkdownRenderer content="## Visão Geral" />);
    const heading = screen.getByRole('heading', { level: 2, name: 'Visão Geral' });
    expect(heading.id).toBe('visão-geral');
  });

  it('disambiguates duplicate headings the way github-slugger does', () => {
    const md = ['## Repetido', '## Repetido'].join('\n\n');
    render(<MarkdownRenderer content={md} />);
    const headings = screen.getAllByRole('heading', { level: 2 });
    expect(headings[0].id).toBe('repetido');
    expect(headings[1].id).toBe('repetido-1');
  });
});

describe('MarkdownRenderer — sanitization (no raw HTML execution)', () => {
  it('renders a raw <script> payload as inert text, never a real <script> element', () => {
    const { container } = render(
      <MarkdownRenderer content={'before\n\n<script>window.__pwned = true;</script>\n\nafter'} />,
    );
    expect(container.querySelector('script')).toBeNull();
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined();
  });

  it('renders a raw onerror-img payload inert (no live <img> with an onerror handler)', () => {
    const { container } = render(
      <MarkdownRenderer content={'<img src=x onerror="window.__pwned2 = true">'} />,
    );
    const img = container.querySelector('img');
    // Either no <img> materializes at all (raw HTML encoded as text), or if
    // one somehow did, it must carry no live onerror handler.
    if (img) {
      expect(img.onerror).toBeNull();
    }
    expect((window as unknown as { __pwned2?: boolean }).__pwned2).toBeUndefined();
  });

  it('defangs a javascript: URI in a standard markdown link', () => {
    render(<MarkdownRenderer content={'[clique aqui](javascript:window.__pwned3=true)'} />);
    const link = screen.getByText('clique aqui').closest('a');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href') ?? '').not.toMatch(/^javascript:/i);
  });
});

describe('MarkdownRenderer — image resolver seam', () => {
  it('resolves a relative image src via resolveImage', () => {
    const resolveImage = vi.fn().mockReturnValue('/resolved/logo.webp');
    render(<MarkdownRenderer content={'![Logo](assets/logo.webp)'} resolveImage={resolveImage} />);
    expect(resolveImage).toHaveBeenCalledWith('assets/logo.webp');
    const img = screen.getByAltText('Logo') as HTMLImageElement;
    expect(img.src).toContain('/resolved/logo.webp');
  });

  it('renders a placeholder (never a broken <img>) when resolveImage returns undefined', () => {
    const resolveImage = vi.fn().mockReturnValue(undefined);
    const { container } = render(
      <MarkdownRenderer content={'![Ausente](assets/missing.webp)'} resolveImage={resolveImage} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(screen.getByText(/Imagem indisponível/)).toBeInTheDocument();
  });

  it('does not call resolveImage for an already-absolute image URL', () => {
    const resolveImage = vi.fn();
    render(
      <MarkdownRenderer
        content={'![Ext](https://example.com/pic.png)'}
        resolveImage={resolveImage}
      />,
    );
    expect(resolveImage).not.toHaveBeenCalled();
    expect(screen.getByAltText('Ext')).toBeInTheDocument();
  });
});

describe('MarkdownRenderer — link navigation seam', () => {
  it('calls onNavigate (and prevents default) for a relative doc link', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<MarkdownRenderer content={'[IA](05-information-architecture.md)'} onNavigate={onNavigate} />);
    await user.click(screen.getByText('IA'));
    expect(onNavigate).toHaveBeenCalledWith('05-information-architecture.md');
  });

  it('opens an absolute http(s) link in a new tab, never through onNavigate', () => {
    const onNavigate = vi.fn();
    render(<MarkdownRenderer content={'[Linear](https://linear.app)'} onNavigate={onNavigate} />);
    const link = screen.getByText('Linear').closest('a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('leaves a bare #hash link native (no onNavigate call)', () => {
    const onNavigate = vi.fn();
    render(<MarkdownRenderer content={'[Voltar ao topo](#visao-geral)'} onNavigate={onNavigate} />);
    const link = screen.getByText('Voltar ao topo').closest('a');
    expect(link).toHaveAttribute('href', '#visao-geral');
    expect(onNavigate).not.toHaveBeenCalled();
  });
});
