import '@testing-library/jest-dom';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { Docs } from './Docs';
import type { DocsSource } from './docsSource';

afterEach(cleanup);

function fixtureSource(overrides: Partial<DocsSource> = {}): DocsSource {
  return {
    markdown: {
      '00-index.md': async () =>
        ['# Índice', '', 'Bem-vindo. Veja a [IA](05-information-architecture.md).', '', '![Logo](assets/logo.webp)'].join(
          '\n',
        ),
      '01-brief-and-decisions.md': async () => 'Sem título aqui.',
      '05-information-architecture.md': async () => '# Arquitetura de Informação\n\nCorpo.',
      '03-reference-reports/linear.md': async () =>
        '# Linear\n\n[Voltar ao índice](../00-index.md)\n\n![Home](../assets/refs/linear-home.webp)',
      ...overrides.markdown,
    },
    images: {
      'assets/logo.webp': '/resolved/logo.webp',
      'assets/refs/linear-home.webp': '/resolved/linear-home.webp',
      ...overrides.images,
    },
  };
}

function renderDocs(source: DocsSource, initialPath = '/admin/website/docs') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/admin/website/docs/*" element={<Docs docsSource={source} />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Docs — index ordering / grouping', () => {
  it('defaults to 00-index and lists root docs before the folder group', async () => {
    renderDocs(fixtureSource());
    await screen.findByRole('heading', { name: 'Índice' });

    const nav = screen.getByRole('navigation', { name: 'Índice da documentação' });
    const items = Array.from(nav.querySelectorAll('button')).map((b) => b.textContent);
    // Root docs (title or humanized-filename fallback) precede the "Reference Reports" folder group.
    expect(items).toEqual(['Índice', 'Brief And Decisions', 'Arquitetura de Informação', 'Linear']);
    expect(screen.getByText('Reference Reports')).toBeInTheDocument();
  });
});

describe('Docs — relative link navigation', () => {
  it('navigates to another doc via a relative .md link', async () => {
    renderDocs(fixtureSource());
    await screen.findByRole('heading', { name: 'Índice' });

    fireEvent.click(screen.getByText('IA'));
    await screen.findByRole('heading', { name: 'Arquitetura de Informação' });
  });

  it('resolves a ../ relative link from a subfolder doc back to a root doc', async () => {
    renderDocs(fixtureSource(), '/admin/website/docs/03-reference-reports/linear');
    await screen.findByRole('heading', { name: 'Linear' });

    fireEvent.click(screen.getByText('Voltar ao índice'));
    await screen.findByRole('heading', { name: 'Índice' });
  });
});

describe('Docs — image resolution', () => {
  it('resolves a root-relative image', async () => {
    renderDocs(fixtureSource());
    const img = (await screen.findByAltText('Logo')) as HTMLImageElement;
    expect(img.src).toContain('/resolved/logo.webp');
  });

  it('resolves a ../assets image from a subfolder doc', async () => {
    renderDocs(fixtureSource(), '/admin/website/docs/03-reference-reports/linear');
    const img = (await screen.findByAltText('Home')) as HTMLImageElement;
    expect(img.src).toContain('/resolved/linear-home.webp');
  });
});

describe('Docs — states', () => {
  it('shows the empty state when there are no docs', async () => {
    renderDocs({ markdown: {}, images: {} });
    expect(await screen.findByText('Nenhuma documentação publicada ainda.')).toBeInTheDocument();
  });

  it('shows a not-found state for an unknown doc path', async () => {
    renderDocs(fixtureSource(), '/admin/website/docs/does-not-exist');
    expect(await screen.findByText('Documento "does-not-exist" não encontrado.')).toBeInTheDocument();
  });

  it('shows an error state when a doc loader rejects', async () => {
    const source = fixtureSource({
      markdown: {
        '00-index.md': async () => {
          throw new Error('boom');
        },
      },
    });
    renderDocs(source);
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });

  it('renders a loading skeleton before docs resolve, never an empty/error state', async () => {
    let resolveDoc: (value: string) => void = () => {};
    const pending = new Promise<string>((resolve) => {
      resolveDoc = resolve;
    });
    const source: DocsSource = { markdown: { '00-index.md': () => pending }, images: {} };
    renderDocs(source);

    expect(screen.queryByText('Nenhuma documentação publicada ainda.')).toBeNull();
    expect(screen.getByLabelText('Carregando documentação')).toBeInTheDocument();

    resolveDoc('# Índice');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Índice' })).toBeInTheDocument());
  });
});

describe('Docs — filter box', () => {
  it('filters the index by title', async () => {
    renderDocs(fixtureSource());
    await screen.findByRole('heading', { name: 'Índice' });

    const nav = screen.getByRole('navigation', { name: 'Índice da documentação' });
    fireEvent.change(screen.getByLabelText('Filtrar por título'), { target: { value: 'linear' } });
    expect(within(nav).queryByText('Índice')).toBeNull();
    expect(within(nav).getByText('Linear')).toBeInTheDocument();
  });
});
