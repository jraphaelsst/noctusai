/**
 * Editable board columns — `StageHeaderMenu`, `DeleteStageDialog`,
 * `AddStageColumn`, `mergeVisibleStageOrder`, and `PipelineBoard`'s opt-in
 * wiring (`editableHeaders`, `reorderableColumns`, `canEditStages`,
 * `roleLabels`).
 *
 * The overriding assertion is the OPT-IN contract: a `PipelineBoard` rendered
 * without the new props shows no header menu, no add slot and no column drag
 * handle, and fires no extra request — every existing consumer (social-wiring,
 * erp-imobiliario, orbity, academia) is unchanged.
 */
/// <reference types="@testing-library/jest-dom" />
import * as React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';

import { AddStageColumn } from './AddStageColumn';
import { DeleteStageDialog } from './DeleteStageDialog';
import { PipelineBoard } from './PipelineBoard';
import { StageHeaderMenu } from './StageHeaderMenu';
import { createPipelineHooks } from './createPipelineHooks';
import { mergeVisibleStageOrder } from './stageOrder';
import type { PipelineApi, PipelineColumn, PipelineStage } from './types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

interface Card {
  id: string;
  valor: number;
}

function stage(id: string, posicao: number, extra: Partial<PipelineStage> = {}): PipelineStage {
  return { id, slug: id, label: id.toUpperCase(), cor: 'secondary', posicao, papel: null, ativo: true, ...extra };
}

const S_A = stage('a', 0);
const S_B = stage('b', 1, { papel: 'final' });
const S_C = stage('c', 2);

function board(): PipelineColumn<Card>[] {
  return [
    { etapa: 'a', stage: S_A, total: 1, valorTotal: 10, cards: [{ id: 'k1', valor: 10 }] },
    { etapa: 'b', stage: S_B, total: 0, valorTotal: 0, cards: [] },
    { etapa: 'c', stage: S_C, total: 0, valorTotal: 0, cards: [] },
  ];
}

let api: PipelineApi;
let queryClient: QueryClient;

function makeHooks() {
  return createPipelineHooks<Card>(
    {
      queryKey: 'edboard',
      boardEndpoint: '/api/board',
      stagesEndpoint: '/api/board/etapas',
      moveEndpoint: '/api/cards',
      getCardId: (c) => c.id,
      getCardValue: (c) => c.valor,
      entityLabel: 'carta',
    },
    api,
  );
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  api = {
    // Cast to the client's own generic method types: a concrete vi.fn()
    // return can't satisfy `<T>(…) => Promise<T>` (CI seed typecheck).
    get: vi.fn(async (path: string) =>
      path === '/api/board' ? { data: board() } : { data: [S_A, S_B, stage('x', 3, { ativo: false }), S_C] },
    ) as unknown as PipelineApi['get'],
    post: vi.fn(async () => ({ data: null })) as unknown as PipelineApi['post'],
    patch: vi.fn(async () => ({ data: null })) as unknown as PipelineApi['patch'],
    delete: vi.fn(async () => ({ data: { cards_movidos: 0 } })) as unknown as PipelineApi['delete'],
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// ── mergeVisibleStageOrder ───────────────────────────────────────────────────

describe('mergeVisibleStageOrder', () => {
  it('refills only the visible slots; hidden (inactive) stages keep their exact slot', () => {
    const all = [stage('a', 0), stage('hidden', 1), stage('b', 2), stage('c', 3)];
    expect(mergeVisibleStageOrder(all, ['c', 'a', 'b'])).toEqual(['c', 'hidden', 'a', 'b']);
  });

  it('orders the full list by posicao then slug, like the backend', () => {
    const all = [stage('b', 1), stage('a', 1), stage('z', 0)];
    expect(mergeVisibleStageOrder(all, ['b', 'a', 'z'])).toEqual(['b', 'a', 'z']);
  });

  it('falls back to the visible order when the stage list is empty or out of step', () => {
    expect(mergeVisibleStageOrder([], ['b', 'a'])).toEqual(['b', 'a']);
    expect(mergeVisibleStageOrder([stage('a', 0)], ['new', 'a'])).toEqual(['new', 'a']);
  });
});

// ── StageHeaderMenu ──────────────────────────────────────────────────────────

function renderMenu(overrides: Partial<React.ComponentProps<typeof StageHeaderMenu>> = {}) {
  const props = {
    stage: S_A,
    stages: [S_A, S_B, S_C],
    cardCount: 0,
    onRename: vi.fn(),
    onRecolor: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  };
  render(<StageHeaderMenu {...props} />);
  return props;
}

describe('StageHeaderMenu', () => {
  it('renames inline from the menu: Enter saves the trimmed label', () => {
    const props = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa A' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Renomear' }));
    const input = screen.getByRole('textbox', { name: 'Novo nome para A' });
    fireEvent.change(input, { target: { value: '  Qualificação  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(props.onRename).toHaveBeenCalledWith('Qualificação');
  });

  it('renames on double-click of the title; Escape cancels without saving', () => {
    const props = renderMenu();
    fireEvent.doubleClick(screen.getByRole('heading', { name: 'A' }));
    const input = screen.getByRole('textbox', { name: 'Novo nome para A' });
    fireEvent.change(input, { target: { value: 'Outro' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(props.onRename).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'A' })).toBeInTheDocument();
  });

  it('does not save an empty or unchanged label', () => {
    const props = renderMenu();
    fireEvent.doubleClick(screen.getByRole('heading', { name: 'A' }));
    fireEvent.blur(screen.getByRole('textbox', { name: 'Novo nome para A' }));
    expect(props.onRename).not.toHaveBeenCalled();
  });

  it('recolours from the swatches', () => {
    const props = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa A' }));
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Cor success para A' }));
    expect(props.onRecolor).toHaveBeenCalledWith('success');
  });

  it('deletes an empty stage through the shared dialog', () => {
    const props = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa A' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Excluir etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }));
    expect(props.onDelete).toHaveBeenCalledTimes(1);
  });

  it('a stage holding cards requires a TARGET, defaulting to the first other stage', () => {
    const props = renderMenu({ cardCount: 3 });
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa A' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Excluir etapa' }));
    const select = screen.getByRole('combobox', { name: 'Mover cartas para' });
    expect(select).toHaveValue('b');
    fireEvent.change(select, { target: { value: 'c' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }));
    expect(props.onDelete).toHaveBeenCalledWith('c');
  });

  it('a stage carrying a papel cannot be deleted — the dialog explains, with the role label', () => {
    const props = renderMenu({ stage: S_B, roleLabels: { final: 'Ganho' } });
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa B' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Excluir etapa' }));
    expect(screen.getByText('Ganho')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmar exclusão' })).toBeNull();
    expect(props.onDelete).not.toHaveBeenCalled();
  });

  it('isolates its controls from a column drag handle (mousedown/keydown do not bubble)', () => {
    const onMouseDown = vi.fn();
    const onKeyDown = vi.fn();
    render(
      <div onMouseDown={onMouseDown} onKeyDown={onKeyDown}>
        <StageHeaderMenu stage={S_A} stages={[S_A]} cardCount={0} onRename={vi.fn()} onRecolor={vi.fn()} onDelete={vi.fn()} />
      </div>,
    );
    const trigger = screen.getByRole('button', { name: 'Opções da etapa A' });
    fireEvent.mouseDown(trigger);
    fireEvent.keyDown(trigger, { key: 'Enter' });
    expect(onMouseDown).not.toHaveBeenCalled();
    expect(onKeyDown).not.toHaveBeenCalled();
    // The title text stays a grab surface.
    fireEvent.mouseDown(screen.getByRole('heading', { name: 'A' }));
    expect(onMouseDown).toHaveBeenCalledTimes(1);
  });
});

describe('DeleteStageDialog', () => {
  it('disables confirm when cards need a target and no other stage exists', () => {
    render(
      <DeleteStageDialog stage={S_A} stages={[S_A]} cardCount={2} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole('button', { name: 'Confirmar exclusão' })).toBeDisabled();
  });
});

describe('AddStageColumn', () => {
  it('adds a column from the trailing slot', () => {
    const onCreate = vi.fn();
    render(<AddStageColumn onCreate={onCreate} />);
    fireEvent.click(screen.getByRole('button', { name: '+ coluna' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Nome da nova etapa' }), {
      target: { value: 'Negociação' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    expect(onCreate).toHaveBeenCalledWith('Negociação');
    expect(screen.getByRole('button', { name: '+ coluna' })).toBeInTheDocument();
  });
});

// ── PipelineBoard opt-in wiring ──────────────────────────────────────────────

function renderBoard(props: Record<string, unknown> = {}) {
  const hooks = makeHooks();
  render(
    <QueryClientProvider client={queryClient}>
      <PipelineBoard hooks={hooks} renderCard={(c: Card) => <span>{c.id}</span>} {...props} />
    </QueryClientProvider>,
  );
  return hooks;
}

describe('PipelineBoard — editable columns are opt-in', () => {
  it('DEFAULT: no header menu, no add slot, no column handle, no stage-list request', async () => {
    renderBoard();
    await screen.findByText('k1');
    expect(screen.queryByRole('button', { name: /Opções da etapa/ })).toBeNull();
    expect(screen.queryByTestId('pipeline-add-stage')).toBeNull();
    expect(document.querySelectorAll('[data-kanban-column-handle]')).toHaveLength(0);
    expect(screen.getByRole('heading', { name: 'A' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Configurar etapas' })).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalledWith('/api/board/etapas');
  });

  it('editableHeaders: renames a column from its header (PATCH label)', async () => {
    // Keep the PATCH in flight so the assertion sees the OPTIMISTIC header,
    // not a refetch of this fake server (which never persists the rename).
    (api.patch as any).mockImplementationOnce(() => new Promise(() => {}));
    renderBoard({ editableHeaders: true });
    await screen.findByText('k1');
    fireEvent.doubleClick(screen.getByRole('heading', { name: 'C' }));
    const input = screen.getByRole('textbox', { name: 'Novo nome para C' });
    fireEvent.change(input, { target: { value: 'Contrato' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith('/api/board/etapas/c', { label: 'Contrato' }),
    );
    // Optimistic: the header shows the new name before any refetch.
    expect(await screen.findByRole('heading', { name: 'Contrato' })).toBeInTheDocument();
  });

  it('editableHeaders: deletes a column holding cards with its target (DELETE reassign_to)', async () => {
    renderBoard({ editableHeaders: true });
    await screen.findByText('k1');
    fireEvent.click(screen.getByRole('button', { name: 'Opções da etapa A' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Excluir etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar exclusão' }));
    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/api/board/etapas/a', { reassign_to: 'b' }),
    );
  });

  it('editableHeaders: "+ coluna" creates a stage (POST label)', async () => {
    renderBoard({ editableHeaders: true });
    await screen.findByText('k1');
    fireEvent.click(screen.getByRole('button', { name: '+ coluna' }));
    fireEvent.change(screen.getByRole('textbox', { name: 'Nome da nova etapa' }), {
      target: { value: 'Pós-venda' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/board/etapas', { label: 'Pós-venda' }),
    );
  });

  it('reorderableColumns: every column header becomes a drag handle', async () => {
    renderBoard({ reorderableColumns: true });
    await screen.findByText('k1');
    expect(document.querySelectorAll('[data-kanban-column-handle]')).toHaveLength(3);
  });

  it('canEditStages={false} withholds every stage-editing affordance', async () => {
    renderBoard({ editableHeaders: true, reorderableColumns: true, canEditStages: false });
    await screen.findByText('k1');
    expect(screen.queryByRole('button', { name: /Opções da etapa/ })).toBeNull();
    expect(screen.queryByTestId('pipeline-add-stage')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Configurar etapas' })).toBeNull();
    expect(document.querySelectorAll('[data-kanban-column-handle]')).toHaveLength(0);
  });
});

// ── createPipelineHooks: column edits land on the board optimistically ──────

describe('useReorderStages / useUpdateStage — board cache', () => {
  it('reorders the BOARD columns optimistically and rolls back on error', async () => {
    const hooks = makeHooks();
    queryClient.setQueryData(['edboard', {}], board());
    let reject!: (e: Error) => void;
    (api.post as any).mockImplementationOnce(() => new Promise((_, r) => (reject = r)));

    const { result } = renderHook(() => hooks.useReorderStages(), { wrapper });
    act(() => result.current.mutate(['c', 'a', 'b']));

    await waitFor(() =>
      expect(
        (queryClient.getQueryData(['edboard', {}]) as PipelineColumn<Card>[]).map((c) => c.etapa),
      ).toEqual(['c', 'a', 'b']),
    );
    expect(api.post).toHaveBeenCalledWith('/api/board/etapas/reordenar', { ordem: ['c', 'a', 'b'] });

    await act(async () => {
      reject(new Error('boom'));
    });
    await waitFor(() =>
      expect(
        (queryClient.getQueryData(['edboard', {}]) as PipelineColumn<Card>[]).map((c) => c.etapa),
      ).toEqual(['a', 'b', 'c']),
    );
  });

  it('patches the column header stage optimistically on a rename', async () => {
    const hooks = makeHooks();
    queryClient.setQueryData(['edboard', {}], board());
    (api.patch as any).mockImplementationOnce(() => new Promise(() => {}));

    const { result } = renderHook(() => hooks.useUpdateStage(), { wrapper });
    act(() => result.current.mutate({ id: 'a', input: { label: 'Novo' } }));

    await waitFor(() =>
      expect((queryClient.getQueryData(['edboard', {}]) as PipelineColumn<Card>[])[0].stage.label).toBe(
        'Novo',
      ),
    );
  });
});
