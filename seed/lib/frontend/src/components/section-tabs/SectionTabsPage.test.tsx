import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { SectionTabsPage, type SectionTab } from './SectionTabsPage';

const SECTIONS: SectionTab[] = [
  { key: 'conexoes', label: 'Conexões', render: () => <p>conteudo conexoes</p> },
  { key: 'equipe', label: 'Equipe', render: () => <p>conteudo equipe</p> },
  { key: 'secreta', label: 'Secreta', visible: false, render: () => <p>conteudo secreta</p> },
];

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function renderAt(path: string, sections = SECTIONS) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/configuracoes/*"
          element={<><SectionTabsPage basePath="/configuracoes/" title="Configurações" description="Ajustes" sections={sections} /><Where /></>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SectionTabsPage', () => {
  it('opens the section named by the URL and renders only that one', () => {
    renderAt('/configuracoes/equipe');
    expect(screen.getByText('conteudo equipe')).toBeInTheDocument();
    expect(screen.queryByText('conteudo conexoes')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Configurações' })).toBeInTheDocument();
    expect(screen.getByText('Ajustes')).toBeInTheDocument();
  });

  it('redirects the bare base path and an unknown segment to the first section', () => {
    renderAt('/configuracoes');
    expect(screen.getByTestId('where')).toHaveTextContent('/configuracoes/conexoes');
    expect(screen.getByText('conteudo conexoes')).toBeInTheDocument();
  });

  it('redirects an unknown segment and a hidden section to the first visible one', () => {
    renderAt('/configuracoes/secreta');
    expect(screen.getByTestId('where')).toHaveTextContent('/configuracoes/conexoes');
    expect(screen.queryByText('conteudo secreta')).toBeNull();
    expect(screen.queryByTestId('section-tab-secreta')).toBeNull();
  });

  it('clicking a tab navigates to its sub-route', () => {
    renderAt('/configuracoes/conexoes');
    fireEvent.mouseDown(screen.getByTestId('section-tab-equipe'));
    fireEvent.click(screen.getByTestId('section-tab-equipe'));
    expect(screen.getByTestId('where')).toHaveTextContent('/configuracoes/equipe');
    expect(screen.getByText('conteudo equipe')).toBeInTheDocument();
  });

  it('renders nothing when every section is hidden', () => {
    const { container } = renderAt('/configuracoes/conexoes', SECTIONS.map((s) => ({ ...s, visible: false })));
    expect(container.querySelector('[data-testid="section-tabs-page"]')).toBeNull();
  });
});
