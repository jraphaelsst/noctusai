/**
 * Tests for `<ResourceManager/>` — the canonical page-scoped-CRUD shell.
 *
 * Drives the component against a fake `ApiClient` (the seam) and asserts
 * the full lifecycle: list render → create (POST + reload) → edit (PATCH)
 * → delete (window.confirm + DELETE). No monkeypatching of our code; the
 * api client is the injected dependency.
 *
 * Rendered with `@testing-library/react`; matchers from
 * `@testing-library/jest-dom` (registered in the seed framework's vitest
 * setup). `window.confirm` is stubbed (jsdom does not implement it).
 */
/// <reference types="@testing-library/jest-dom" />
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';

import { ResourceManager } from './ResourceManager';
import type { ApiClient } from '../api';

interface Row {
  id: string;
  title: string;
  description: string | null;
}

function makeApi(rows: Row[]): ApiClient {
  return {
    get: vi.fn(async () => ({ items: rows })),
    post: vi.fn(async () => ({ id: 'new', title: 'X', description: null })),
    patch: vi.fn(async () => ({ id: '1', title: 'Y', description: null })),
    put: vi.fn(async () => ({})),
    delete: vi.fn(async () => ({ ok: true })),
  } as unknown as ApiClient;
}

const COLUMNS = [
  { key: 'title', header: 'Título' },
  { key: 'description', header: 'Descrição' },
];
const FIELDS = [
  { name: 'title', label: 'Título', required: true },
  { name: 'description', label: 'Descrição', type: 'textarea' as const },
];

function renderRM(api: ApiClient) {
  return render(
    <ResourceManager<Row>
      title="Itens"
      api={api}
      apiPath="/api/items"
      singularName="Item"
      columns={COLUMNS}
      fields={FIELDS}
    />,
  );
}

describe('<ResourceManager/>', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('lists rows returned by api.get (extracts `items`)', async () => {
    const api = makeApi([{ id: '1', title: 'Alpha', description: 'first' }]);
    renderRM(api);
    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/items');
  });

  it('shows the empty state when there are genuinely no rows', async () => {
    const api = makeApi([]);
    renderRM(api);
    expect(await screen.findByText(/Nenhum\(a\) item/i)).toBeInTheDocument();
  });

  it('creates via the modal → POST with the form payload, then reloads', async () => {
    const api = makeApi([]);
    renderRM(api);
    await screen.findByText(/Nenhum\(a\) item/i);

    fireEvent.click(screen.getByText(/Novo\(a\) Item/i));
    fireEvent.change(screen.getByLabelText(/Título/i), { target: { value: 'Beta' } });
    fireEvent.click(screen.getByText('Criar'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/items', { title: 'Beta', description: '' }));
    // reload after mutation: get called twice (mount + post-create)
    await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  });

  it('edits an existing row → PATCH to /{id} without createOnly fields', async () => {
    const api = makeApi([{ id: '42', title: 'Gamma', description: 'g' }]);
    renderRM(api);
    await screen.findByText('Gamma');

    fireEvent.click(screen.getByText('Editar'));
    fireEvent.change(screen.getByLabelText(/Título/i), { target: { value: 'Gamma2' } });
    fireEvent.click(screen.getByText('Salvar'));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/api/items/42', { title: 'Gamma2', description: 'g' }),
    );
  });

  it('deletes after confirm → DELETE to /{id}', async () => {
    const api = makeApi([{ id: '7', title: 'Delta', description: null }]);
    renderRM(api);
    await screen.findByText('Delta');

    fireEvent.click(screen.getByText('Excluir'));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/items/7'));
    expect(window.confirm).toHaveBeenCalled();
  });

  it('surfaces a fetch error instead of a silent zero state', async () => {
    const api = makeApi([]);
    (api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    renderRM(api);
    expect(await screen.findByText(/Tentar novamente/i)).toBeInTheDocument();
  });
});
