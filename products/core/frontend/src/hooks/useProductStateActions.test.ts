/**
 * useProductStateActions — the ONE mechanism behind the product
 * status/deploy-scope toggles, consumed by both `/admin/products` and the
 * core dashboard cards. Verifies: success calls `onChanged(id)` + shows a
 * saved toast, failure shows `toast.error` (never a blocking alert), and the
 * busy key is set during the call and cleared afterwards either way.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const { mockPost, mockToastSuccess, mockToastError } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockToastSuccess: vi.fn(),
  mockToastError: vi.fn(),
}));

vi.mock('../lib/api', () => ({
  api: { get: vi.fn(), post: mockPost, patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('sonner', () => ({
  toast: { success: mockToastSuccess, error: mockToastError },
}));

import { useProductStateActions } from './useProductStateActions';

const PRODUCT = { id: 'prod-1' };

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useProductStateActions', () => {
  it('setActivation: hits POST /activation, calls onChanged(id), shows a saved toast, clears busy', async () => {
    mockPost.mockResolvedValueOnce({});
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useProductStateActions(onChanged));

    expect(result.current.busyId).toBeNull();

    await act(async () => {
      await result.current.setActivation(PRODUCT, false);
    });

    expect(mockPost).toHaveBeenCalledWith('/api/products/prod-1/activation', { ativo: false });
    expect(onChanged).toHaveBeenCalledWith('prod-1');
    expect(mockToastSuccess).toHaveBeenCalledTimes(1);
    expect(mockToastSuccess.mock.calls[0][0]).toMatch(/desativado/i);
    expect(mockToastSuccess.mock.calls[0][0]).toMatch(/~1 min/);
    expect(mockToastError).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.busyId).toBeNull());
  });

  it('setActivation(true): the saved toast says "ativado", not "desativado"', async () => {
    mockPost.mockResolvedValueOnce({});
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useProductStateActions(onChanged));

    await act(async () => {
      await result.current.setActivation(PRODUCT, true);
    });

    expect(mockToastSuccess.mock.calls[0][0]).toMatch(/ativado/i);
    expect(mockToastSuccess.mock.calls[0][0]).not.toMatch(/desativado/i);
  });

  it('setDeployScope: hits POST /deploy-scope, calls onChanged(id), shows a plain saved toast', async () => {
    mockPost.mockResolvedValueOnce({});
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useProductStateActions(onChanged));

    await act(async () => {
      await result.current.setDeployScope(PRODUCT, 'live');
    });

    expect(mockPost).toHaveBeenCalledWith('/api/products/prod-1/deploy-scope', { deploy_scope: 'live' });
    expect(onChanged).toHaveBeenCalledWith('prod-1');
    expect(mockToastSuccess).toHaveBeenCalledTimes(1);
  });

  it('on failure: shows toast.error (never a native alert), skips onChanged + the saved toast, clears busy', async () => {
    mockPost.mockRejectedValueOnce(new Error('boom'));
    const onChanged = vi.fn();
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const { result } = renderHook(() => useProductStateActions(onChanged));

    await act(async () => {
      await result.current.setActivation(PRODUCT, false);
    });

    expect(mockToastError).toHaveBeenCalledWith('boom');
    expect(mockToastSuccess).not.toHaveBeenCalled();
    expect(onChanged).not.toHaveBeenCalled();
    expect(alertSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.busyId).toBeNull());
    alertSpy.mockRestore();
  });

  it('sets busyId to the product id while the mutation is in flight', async () => {
    let resolvePost: (v: unknown) => void = () => {};
    mockPost.mockReturnValueOnce(new Promise(resolve => { resolvePost = resolve; }));
    const onChanged = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useProductStateActions(onChanged));

    let pending: Promise<void>;
    act(() => {
      pending = result.current.setActivation(PRODUCT, false);
    });

    await waitFor(() => expect(result.current.busyId).toBe('prod-1'));

    await act(async () => {
      resolvePost({});
      await pending;
    });

    expect(result.current.busyId).toBeNull();
  });
});
