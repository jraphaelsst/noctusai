/**
 * Tests for `<ApiKeysPanel/>`.
 *
 * Coverage:
 *   1. Loading — Skeleton block, aria-busy
 *   2. Empty — "Nenhuma chave gerenciável" message
 *   3. Error — role="alert", the honest 503 message distinct from a generic one
 *   4. Success — masked hint + source badge rendered, never the secret itself
 *   5. Save (free-text field) → PUT with the typed value
 *   6. Save (CHOICE field, options non-empty) → renders a <select>, PUT on submit
 *   7. Remove → DELETE
 *   8. Test action → renders the pass/fail result inline
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { createApiKeysHooks } from './createApiKeysHooks';
import { ApiKeysPanel } from './ApiKeysPanel';
import { ApiError } from '../../api';
import type { ApiClient } from '../../api';
import type { ApiKeyStatus, ApiKeysStatus } from './createApiKeysHooks';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

afterEach(cleanup);

const SECRET_KEY: ApiKeyStatus = {
  key: 'openai_api_key',
  label: 'OpenAI API Key',
  description: 'Usada para IA.',
  is_secret: true,
  testable: true,
  input_type: 'password',
  placeholder: 'sk-...',
  configured: true,
  options: [],
  default: null,
  hint: '...b3f9',
  source: 'local',
  updated_at: '2026-09-17T00:00:00Z',
};

const CHOICE_KEY: ApiKeyStatus = {
  key: 'llm_vision_provider',
  label: 'Provedor de leitura de documentos',
  description: 'Qual IA transcreve páginas.',
  is_secret: false,
  testable: false,
  input_type: 'select',
  placeholder: '',
  configured: false,
  options: [
    { value: 'openai', label: 'OpenAI', description: 'Usa a OpenAI.' },
    { value: 'anthropic', label: 'Anthropic', description: 'Usa a Anthropic.' },
  ],
  default: 'openai',
  hint: null,
  source: null,
  updated_at: null,
};

function makeApi(overrides: Record<string, any> = {}): ApiClient {
  return {
    get: vi.fn(async () => ({ items: [SECRET_KEY], total: 1 } as ApiKeysStatus)),
    put: vi.fn(async () => SECRET_KEY),
    post: vi.fn(async () => ({ key: SECRET_KEY.key, success: true, message: 'Chave válida.' })),
    delete: vi.fn(async () => ({ ...SECRET_KEY, configured: false, source: null })),
    patch: vi.fn(),
    ...overrides,
  } as unknown as ApiClient;
}

function renderPanel(api: ApiClient) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const hooks = createApiKeysHooks(api);
  const utils = render(
    <QueryClientProvider client={client}>
      <ApiKeysPanel hooks={hooks} />
    </QueryClientProvider>,
  );
  return { ...utils, api };
}

// ── 1. Loading ──────────────────────────────────────────────────────────────

describe('ApiKeysPanel: loading', () => {
  it('renders a Skeleton block while the query is in flight', () => {
    const api = makeApi({ get: vi.fn((): Promise<any> => new Promise(() => {})) });
    renderPanel(api);
    expect(screen.getByRole('status', { name: 'Carregando chaves de API' })).toBeInTheDocument();
  });
});

// ── 2. Empty ──────────────────────────────────────────────────────────────────

describe('ApiKeysPanel: empty', () => {
  it('renders the empty message when no keys are managed', async () => {
    const api = makeApi({ get: vi.fn(async () => ({ items: [], total: 0 })) });
    renderPanel(api);
    expect(await screen.findByTestId('api-keys-empty')).toBeInTheDocument();
  });
});

// ── 3. Error ──────────────────────────────────────────────────────────────────

describe('ApiKeysPanel: error', () => {
  it('renders a generic alert for a non-503 failure', async () => {
    const api = makeApi({
      get: vi.fn(async () => {
        throw new Error('Boom 500');
      }),
    });
    renderPanel(api);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Boom 500');
  });

  it('renders the honest ENCRYPTION_KEY message on a 503', async () => {
    const api = makeApi({
      get: vi.fn(async () => {
        throw new ApiError(503, 'ENCRYPTION_KEY not configured');
      }),
    });
    renderPanel(api);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Servidor sem chave de criptografia configurada');
  });
});

// ── 4. Success — masked hint, never the secret ───────────────────────────────

describe('ApiKeysPanel: success', () => {
  it('renders the label, masked hint, and source badge — never the raw secret', async () => {
    const api = makeApi();
    renderPanel(api);
    expect(await screen.findByText('OpenAI API Key')).toBeInTheDocument();
    expect(screen.getByTestId('api-key-hint-openai_api_key')).toHaveTextContent('...b3f9');
    expect(screen.getByTestId('api-key-configured-openai_api_key')).toBeInTheDocument();
  });
});

// ── 5. Save — free-text ───────────────────────────────────────────────────────

describe('ApiKeysPanel: save (free-text)', () => {
  it('PUTs the typed value', async () => {
    const { api } = renderPanel(makeApi());
    const input = (await screen.findByLabelText('OpenAI API Key')) as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'sk-new-value' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/api/settings/api-keys/openai_api_key', {
        value: 'sk-new-value',
      }),
    );
  });
});

// ── 6. Save — CHOICE field ────────────────────────────────────────────────────

describe('ApiKeysPanel: save (choice field)', () => {
  it('renders a <select> for a key with options, and PUTs the chosen value', async () => {
    const api = makeApi({
      get: vi.fn(async () => ({ items: [CHOICE_KEY], total: 1 })),
    });
    renderPanel(api);
    const select = (await screen.findByLabelText(
      'Provedor de leitura de documentos',
    )) as HTMLSelectElement;
    expect(select.tagName).toBe('SELECT');

    fireEvent.change(select, { target: { value: 'anthropic' } });
    fireEvent.click(screen.getByRole('button', { name: 'Salvar' }));

    await waitFor(() =>
      expect(api.put).toHaveBeenCalledWith('/api/settings/api-keys/llm_vision_provider', {
        value: 'anthropic',
      }),
    );
  });
});

// ── 7. Remove ──────────────────────────────────────────────────────────────────

describe('ApiKeysPanel: remove', () => {
  it('DELETEs the key', async () => {
    const { api } = renderPanel(makeApi());
    const removeButton = await screen.findByLabelText('Remover OpenAI API Key');
    fireEvent.click(removeButton);

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/api/settings/api-keys/openai_api_key'),
    );
  });
});

// ── 8. Test action ─────────────────────────────────────────────────────────────

describe('ApiKeysPanel: test action', () => {
  it('renders the pass result inline', async () => {
    renderPanel(makeApi());
    const testButton = await screen.findByRole('button', { name: 'Testar' });
    fireEvent.click(testButton);

    const result = await screen.findByTestId('api-key-test-result-openai_api_key');
    expect(result).toHaveTextContent('Chave válida.');
  });

  it('renders the failure result inline', async () => {
    const api = makeApi({
      post: vi.fn(async () => ({ key: 'openai_api_key', success: false, message: 'Chave inválida.' })),
    });
    renderPanel(api);
    const testButton = await screen.findByRole('button', { name: 'Testar' });
    fireEvent.click(testButton);

    const result = await screen.findByTestId('api-key-test-result-openai_api_key');
    expect(result).toHaveTextContent('Chave inválida.');
  });
});
