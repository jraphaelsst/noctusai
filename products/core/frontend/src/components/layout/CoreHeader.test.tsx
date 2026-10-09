/**
 * CoreHeader: the single core binding of the seed Header. Auth/api/bell are
 * module-boundary mocks (house pattern, see CoreLayout.test.tsx); the seed
 * Header itself renders for real so the label assertion is end-to-end.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CoreHeader, LOGOUT_LABEL } from './CoreHeader';

afterEach(() => cleanup());

const logout = vi.fn(async () => {});

vi.mock('../../lib/auth-context', () => ({
  useAuth: () => ({
    user: { nome: 'Ana', email: 'ana@x.com', role: 'admin' },
    logout,
    refresh: vi.fn(),
  }),
}));

vi.mock('../../lib/api', () => ({ api: { patch: vi.fn(), post: vi.fn() } }));

vi.mock('../NotificationBell', () => ({
  NotificationBell: () => <div data-testid="bell" />,
}));

/** The logout button lives in the profile HoverCard; open it via the trigger. */
function openProfile() {
  const trigger = screen.getByText('Administrador').closest('div[class*="cursor-pointer"]') as HTMLElement;
  fireEvent.pointerEnter(trigger, { pointerType: 'mouse' });
  fireEvent.mouseEnter(trigger);
  fireEvent.focus(trigger);
}

function renderHeader(actions?: React.ReactNode) {
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<CoreHeader actions={actions} />} />
        <Route path="/login" element={<div>LOGIN PAGE</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('CoreHeader', () => {
  it('labels logout "Sair de todos os dispositivos"', async () => {
    expect(LOGOUT_LABEL).toBe('Sair de todos os dispositivos');
    renderHeader();
    openProfile();
    const el = await screen.findByLabelText(LOGOUT_LABEL);
    expect(el.getAttribute('title')).toBe(LOGOUT_LABEL);
  });

  it('logout calls logout() then navigates to /login', async () => {
    renderHeader();
    openProfile();
    fireEvent.click(await screen.findByLabelText(LOGOUT_LABEL));
    await waitFor(() => expect(screen.getByText('LOGIN PAGE')).toBeTruthy());
    expect(logout).toHaveBeenCalledTimes(1);
  });

  it('renders page actions before the NotificationBell', () => {
    renderHeader(<button data-testid="extra">Voltar</button>);
    const extra = screen.getByTestId('extra');
    const bell = screen.getByTestId('bell');
    expect(extra.compareDocumentPosition(bell) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
