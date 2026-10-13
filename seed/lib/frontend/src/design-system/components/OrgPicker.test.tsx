/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiGet = vi.fn();
const apiPut = vi.fn();
const apiDelete = vi.fn();
const removeAllChannels = vi.fn(async () => []);
vi.mock('@noctusai/seed/infra', () => ({
  supabase: { removeAllChannels: () => removeAllChannels() },
  api: {
    get: (...a: unknown[]) => apiGet(...a),
    put: (...a: unknown[]) => apiPut(...a),
    delete: (...a: unknown[]) => apiDelete(...a),
  },
}));

import { ActingAsBanner } from './ActingAsBanner';
import { OrgPickerModal, OrgPickerModalView } from './OrgPickerModal';
import { OrgContentGate, OrgSelectionGate, useOrgEntryPending } from './OrgSelectionGate';
import { endOrgSelectionBestEffort, resetOrgSelectionPage, setOrgPickerForced } from '../../org-selection';
import { getOrgPin, notifyOrgSelectionChanged, setOrgPin } from '../../org-pin';
import { hasOrgVisitMarker, markOrgVisit } from '../../org-visit';

const HOME = { id: 'h', nome: 'NoctusAI' };
const ACME = { id: 'o1', nome: 'Imobiliária Acme' };
const base = { has_access: true, product_slug: 'p', org: HOME };
const sel = (over: object = {}) => ({
  available: true, required: true, mfa_required: false, acting: false,
  org: HOME, home_org: HOME, selection_id: null, ...over,
});
const choices = { orgs: [{ id: 'h', nome: 'NoctusAI', is_home: true }, { id: 'o1', nome: 'Imobiliária Acme', is_home: false }] };

function mount(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}
function route(access: object) {
  apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/me/access') return access;
    if (path === '/api/me/org-choices') return choices;
    throw new Error(`unexpected ${path}`);
  });
}

describe('OrgPickerModal', () => {
  const reload = vi.fn();
  const orig = window.location;
  beforeEach(() => {
    [apiGet, apiPut, apiDelete, reload, removeAllChannels].forEach((m) => m.mockReset());
    setOrgPin(null);
    resetOrgSelectionPage();
    markOrgVisit(); // within a visit (reload): entry behaviour is covered below
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, reload } });
  });
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  it('renders nothing for non-staff', async () => {
    route({ ...base, org_selection: sel({ available: false, required: false }) });
    mount(<OrgPickerModal />);
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/me/access'));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('required: client orgs first, home LAST, non-dismissible (Escape + no close button)', async () => {
    route({ ...base, org_selection: sel() });
    mount(<OrgPickerModal />);
    expect(await screen.findByText('Entrar como NoctusAI (minha org)')).toBeInTheDocument();
    const items = screen.getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Imobiliária Acme');
    expect(items[items.length - 1]).toHaveTextContent('Entrar como NoctusAI (minha org)');
    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByLabelText('Fechar')).toBeNull();
  });

  it('choose PUTs the org, pins it, then reloads', async () => {
    route({ ...base, org_selection: sel() });
    apiPut.mockResolvedValue({});
    mount(<OrgPickerModal />);
    await userEvent.click(await screen.findByText('Imobiliária Acme'));
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith('/api/me/org-choice', { org_id: 'o1' }));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(getOrgPin()).toBe('o1');
    expect(removeAllChannels).toHaveBeenCalledTimes(1);
    expect(removeAllChannels.mock.invocationCallOrder[0]).toBeLessThan(reload.mock.invocationCallOrder[0]);
  });

  it('shows the error and does not reload when the PUT fails', async () => {
    route({ ...base, org_selection: sel() });
    apiPut.mockRejectedValue(new Error('sem licença'));
    mount(<OrgPickerModal />);
    await userEvent.click(await screen.findByText('Imobiliária Acme'));
    expect(await screen.findByRole('alert')).toHaveTextContent('sem licença');
    expect(reload).not.toHaveBeenCalled();
  });

  it('mfa_required shows the 2FA CTA instead of the list', async () => {
    route({ ...base, org_selection: sel({ mfa_required: true }) });
    mount(<OrgPickerModal />);
    const cta = await screen.findByRole('link', { name: 'Configurar 2FA' });
    expect(cta.getAttribute('href')).toMatch(/\/security$/);
    expect(screen.queryByTestId('org-picker-list')).toBeNull();
    expect(apiGet).not.toHaveBeenCalledWith('/api/me/org-choices');
  });

  it('required: "Sair" calls the shell logout (the modal covers the header avatar menu)', async () => {
    route({ ...base, org_selection: sel({ mfa_required: true }) });
    const onSignOut = vi.fn();
    mount(<OrgPickerModal onSignOut={onSignOut} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Sair' }));
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });

  it('dismissible ("Trocar org") picker has no "Sair" — the header is reachable', () => {
    render(
      <OrgPickerModalView
        open required={false} onClose={() => {}} mfaRequired={false} mfaUrl="/security"
        choices={choices.orgs} loading={false} error={false} onRetry={() => {}} onChoose={() => {}}
        onSignOut={() => {}}
      />,
    );
    expect(screen.queryByRole('button', { name: 'Sair' })).toBeNull();
  });

  it('empty choices → empty state', async () => {
    route({ ...base, org_selection: sel() });
    apiGet.mockImplementation(async (path: string) =>
      path === '/api/me/access' ? { ...base, org_selection: sel() } : { orgs: [] });
    mount(<OrgPickerModal />);
    expect(await screen.findByTestId('org-picker-empty')).toBeInTheDocument();
  });

  it('choices failure → error state with retry', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/me/access') return { ...base, org_selection: sel() };
      throw new Error('boom');
    });
    mount(<OrgPickerModal />);
    expect(await screen.findByTestId('org-picker-error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tentar novamente' })).toBeInTheDocument();
  });
});

describe('ActingAsBanner / OrgSelectionGate', () => {
  beforeEach(() => { [apiGet, apiPut, apiDelete].forEach((m) => m.mockReset()); setOrgPin(null); resetOrgSelectionPage(); setOrgPickerForced(false); markOrgVisit(); });
  afterEach(() => { cleanup(); window.sessionStorage.clear(); });

  it('hidden for non-staff', async () => {
    route({ ...base, org_selection: sel({ available: false, required: false, acting: true, org: ACME }) });
    mount(<ActingAsBanner />);
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(screen.queryByTestId('acting-as-banner')).toBeNull();
  });

  it('staff in their home org: slim Trocar org bar, not the full banner', async () => {
    route({ ...base, org_selection: sel({ required: false, acting: false, selection_id: 's' }) });
    mount(<OrgSelectionGate />);
    expect(await screen.findByTestId('org-switch-bar')).toBeInTheDocument();
    expect(screen.queryByTestId('acting-as-banner')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Trocar org' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('no switch bar while the picker is still required', async () => {
    route({ ...base, org_selection: sel() });
    mount(<ActingAsBanner />);
    await waitFor(() => expect(apiGet).toHaveBeenCalled());
    expect(screen.queryByTestId('org-switch-bar')).toBeNull();
  });

  it('acting: shows the org, pins it, and Trocar org opens the picker', async () => {
    route({ ...base, org: ACME, org_selection: sel({ required: false, acting: true, org: ACME, selection_id: 's1' }) });
    mount(<OrgSelectionGate />);
    expect(await screen.findByText('Imobiliária Acme')).toBeInTheDocument();
    expect(screen.getByText(/Você está atuando em/)).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).toBeNull();
    await waitFor(() => expect(getOrgPin()).toBe('o1'));
    await userEvent.click(screen.getByRole('button', { name: 'Trocar org' }));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    // dismissible when not required
    expect(screen.getByLabelText('Fechar')).toBeInTheDocument();
  });

  it('endOrgSelectionBestEffort swallows errors and clears the pin', async () => {
    setOrgPin('o1');
    apiDelete.mockRejectedValue(new Error('403'));
    await expect(endOrgSelectionBestEffort()).resolves.toBeUndefined();
    expect(apiDelete).toHaveBeenCalledWith('/api/me/org-choice?all=true');
    expect(getOrgPin()).toBeNull();
    expect(hasOrgVisitMarker()).toBe(false); // the next load after logout is an entry
  });
});

describe('every entry is a choice (owner 2026-10-12)', () => {
  const reload = vi.fn();
  const orig = window.location;
  const LEFTOVER = sel({ required: false, acting: true, org: ACME, selection_id: 's-old' });

  /** Access answers `first` until the entry DELETE lands, then `after`. */
  function routeEntry(first: object, after: object) {
    let ended = false;
    apiDelete.mockImplementation(async () => { ended = true; });
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/me/access') return ended ? after : first;
      if (path === '/api/me/org-choices') return choices;
      throw new Error(`unexpected ${path}`);
    });
  }
  function mountShell() {
    return mount(
      <>
        <OrgSelectionGate />
        <OrgContentGate><p data-testid="product-content">conteúdo</p></OrgContentGate>
      </>,
    );
  }

  beforeEach(() => {
    [apiGet, apiPut, apiDelete, reload, removeAllChannels].forEach((m) => m.mockReset());
    setOrgPin(null);
    resetOrgSelectionPage();
    setOrgPickerForced(false);
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: { ...orig, reload } });
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: orig });
  });

  it('entry (no marker): DELETEs the leftover selection, then a REQUIRED picker with no content behind it', async () => {
    routeEntry({ ...base, org: ACME, org_selection: LEFTOVER }, { ...base, org_selection: sel() });
    mountShell();
    expect(screen.queryByTestId('product-content')).toBeNull();
    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith('/api/me/org-choice'));
    expect(await screen.findByText('Imobiliária Acme')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByLabelText('Fechar')).toBeNull(); // non-dismissible
    expect(screen.queryByTestId('product-content')).toBeNull();
    // the leftover org is never adopted on an entry page load
    expect(getOrgPin()).toBeNull();
    expect(reload).not.toHaveBeenCalled();
    expect(apiDelete).toHaveBeenCalledTimes(1);
    expect(hasOrgVisitMarker()).toBe(false); // set only after a choice
  });

  it('the DELETE precedes the access refetch the picker is built from', async () => {
    routeEntry({ ...base, org_selection: LEFTOVER }, { ...base, org_selection: sel() });
    mountShell();
    await screen.findByText('Imobiliária Acme');
    const accessCalls = apiGet.mock.calls
      .map((c, i) => [c[0], apiGet.mock.invocationCallOrder[i]] as const)
      .filter(([p]) => p === '/api/me/access');
    expect(accessCalls.length).toBeGreaterThanOrEqual(2);
    expect(apiDelete.mock.invocationCallOrder[0]).toBeLessThan(accessCalls[accessCalls.length - 1][1]);
  });

  it('choosing on entry sets the visit marker, pins, reloads', async () => {
    routeEntry({ ...base, org_selection: sel() }, { ...base, org_selection: sel() });
    apiPut.mockResolvedValue({});
    mountShell();
    await userEvent.click(await screen.findByText('Imobiliária Acme'));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
    expect(apiPut).toHaveBeenCalledWith('/api/me/org-choice', { org_id: 'o1' });
    expect(hasOrgVisitMarker()).toBe(true);
    expect(getOrgPin()).toBe('o1');
  });

  it('reload within the visit (marker + live selection): no DELETE, no picker, content renders', async () => {
    markOrgVisit();
    route({ ...base, org: ACME, org_selection: LEFTOVER });
    mountShell();
    expect(await screen.findByTestId('product-content')).toBeInTheDocument();
    await waitFor(() => expect(getOrgPin()).toBe('o1'));
    expect(apiDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('entry: the choices request fires before the DELETE resolves, the list shows, choosing waits for the DELETE', async () => {
    let releaseDelete: () => void = () => {};
    apiDelete.mockImplementation(() => new Promise<void>((r) => { releaseDelete = r; }));
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/me/access') return { ...base, org_selection: sel() };
      if (path === '/api/me/org-choices') return choices;
      throw new Error(`unexpected ${path}`);
    });
    mountShell();
    await waitFor(() => expect(apiDelete).toHaveBeenCalledTimes(1));
    // DELETE still pending, yet the list is already rendered (no "Carregando")
    const btn = await screen.findByText('Imobiliária Acme');
    expect(apiGet).toHaveBeenCalledWith('/api/me/org-choices');
    expect(screen.queryByTestId('org-picker-loading')).toBeNull();
    const button = btn.closest('button') as HTMLButtonElement;
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(apiPut).not.toHaveBeenCalled();
    releaseDelete();
    await waitFor(() => expect(button).not.toBeDisabled());
    apiPut.mockResolvedValue({});
    await userEvent.click(button);
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith('/api/me/org-choice', { org_id: 'o1' }));
  });

  it('org-scoped widgets (useOrgEntryPending) are not mounted while the picker is required, mounted after', async () => {
    const widgetFetch = vi.fn();
    function Widget() { widgetFetch(); return <span data-testid="bell" />; }
    function Header() { return useOrgEntryPending() ? null : <Widget />; }
    routeEntry({ ...base, org_selection: sel() }, { ...base, org_selection: sel() });
    mount(<><OrgSelectionGate /><Header /></>);
    await screen.findByText('Imobiliária Acme');
    expect(screen.queryByTestId('bell')).toBeNull();
    expect(widgetFetch).not.toHaveBeenCalled();
  });

  it('org-scoped widgets mount for non-staff and within a visit (no change)', async () => {
    function Header() { return useOrgEntryPending() ? null : <span data-testid="bell" />; }
    route({ ...base, org_selection: sel({ available: false, required: false }) });
    mount(<><OrgSelectionGate /><Header /></>);
    expect(await screen.findByTestId('bell')).toBeInTheDocument();
  });

  it('sessionStorage throwing => treated as an entry (fail toward prompting)', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied'); });
    routeEntry({ ...base, org: ACME, org_selection: LEFTOVER }, { ...base, org_selection: sel() });
    mountShell();
    await waitFor(() => expect(apiDelete).toHaveBeenCalledWith('/api/me/org-choice'));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.queryByTestId('product-content')).toBeNull();
  });

  it('non-staff entry: no DELETE, no picker, content renders, marker set', async () => {
    route({ ...base, org_selection: sel({ available: false, required: false }) });
    mountShell();
    expect(await screen.findByTestId('product-content')).toBeInTheDocument();
    expect(apiDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(hasOrgVisitMarker()).toBe(true);
  });

  it('409 org_selection_required within a visit reopens the REQUIRED picker and hides the content', async () => {
    markOrgVisit();
    let required = false;
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/me/access') {
        return required
          ? { ...base, org_selection: sel() }
          : { ...base, org_selection: sel({ required: false, selection_id: 's' }) };
      }
      if (path === '/api/me/org-choices') return choices;
      throw new Error(`unexpected ${path}`);
    });
    mountShell();
    expect(await screen.findByTestId('product-content')).toBeInTheDocument();
    // another tab's entry ended this selection: the next gated call answers 409
    required = true;
    notifyOrgSelectionChanged(); // what the api client does on org_selection_required
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId('product-content')).toBeNull());
    expect(screen.queryByLabelText('Fechar')).toBeNull();
    expect(apiDelete).not.toHaveBeenCalled(); // a 409 is not an entry
  });
});
