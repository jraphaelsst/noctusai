/**
 * useProductSite — the public-site controls of /admin/products. Verifies the
 * cache-write contract (server row merged into the list), contiguous featured
 * positions, the 7th-refusal (no request, no swap), server detail shown inline,
 * and a re-sync after a failed multi-step change.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useState } from 'react';

const { mockPatch } = vi.hoisted(() => ({ mockPatch: vi.fn() }));
vi.mock('../lib/api', () => ({ api: { patch: mockPatch, get: vi.fn() } }));

import { featuredOf, REFUSAL_FULL, useProductSite, type SiteProduct } from './useProductSite';

const mk = (id: string, destaque: number | null, exibir = true): SiteProduct => ({
  id, nome: id.toUpperCase(), exibir_no_site: exibir, destaque_no_site: destaque,
});

function setup(initial: SiteProduct[]) {
  const refetch = vi.fn().mockResolvedValue(undefined);
  const hook = renderHook(() => {
    const [products, setProducts] = useState(initial);
    return { products, ...useProductSite(products, setProducts, refetch) };
  });
  return { hook, refetch };
}

beforeEach(() => {
  vi.clearAllMocks();
  // echo the body back as the server row
  mockPatch.mockImplementation(async (path: string, body: object) => ({
    data: { id: path.split('/').pop(), ...body },
  }));
});

describe('useProductSite', () => {
  it('feature: appends at n+1 and writes the server row into the list', async () => {
    const { hook } = setup([mk('a', 1), mk('b', null)]);
    await act(() => hook.result.current.feature(hook.result.current.products[1]));
    expect(mockPatch).toHaveBeenCalledWith('/api/products/b', { destaque_no_site: 2 });
    expect(featuredOf([...hook.result.current.products]).map(p => p.id)).toEqual(['a', 'b']);
  });

  it('feature: a 7th is refused locally with the owner copy, no request, nothing swapped', async () => {
    const six = ['a', 'b', 'c', 'd', 'e', 'f'].map((id, i) => mk(id, i + 1));
    const { hook } = setup([...six, mk('g', null)]);
    await act(() => hook.result.current.feature(hook.result.current.products[6]));
    expect(mockPatch).not.toHaveBeenCalled();
    expect(hook.result.current.error).toEqual({ id: 'g', message: REFUSAL_FULL });
    expect(featuredOf([...hook.result.current.products])).toHaveLength(6);
  });

  it('unfeature: clears the slot and moves the following ones up', async () => {
    const { hook } = setup([mk('a', 1), mk('b', 2), mk('c', 3)]);
    await act(() => hook.result.current.unfeature(hook.result.current.products[0]));
    expect(mockPatch.mock.calls.map(c => [c[0], c[1]])).toEqual([
      ['/api/products/a', { destaque_no_site: null }],
      ['/api/products/b', { destaque_no_site: 1 }],
      ['/api/products/c', { destaque_no_site: 2 }],
    ]);
    expect(featuredOf([...hook.result.current.products]).map(p => p.id)).toEqual(['b', 'c']);
  });

  it('move: swaps two positions through null (positions are unique)', async () => {
    const { hook } = setup([mk('a', 1), mk('b', 2)]);
    await act(() => hook.result.current.move(hook.result.current.products[1], -1));
    expect(mockPatch.mock.calls.map(c => c[1])).toEqual([
      { destaque_no_site: null }, { destaque_no_site: 2 }, { destaque_no_site: 1 },
    ]);
    expect(featuredOf([...hook.result.current.products]).map(p => p.id)).toEqual(['b', 'a']);
  });

  it('setExibir off on a featured product un-features it first, then hides', async () => {
    const { hook } = setup([mk('a', 1), mk('b', 2)]);
    await act(() => hook.result.current.setExibir(hook.result.current.products[0], false));
    expect(mockPatch.mock.calls.map(c => c[1])).toEqual([
      { destaque_no_site: null }, { destaque_no_site: 1 }, { exibir_no_site: false },
    ]);
  });

  it('a server refusal shows its pt-BR detail inline and re-syncs', async () => {
    mockPatch.mockRejectedValueOnce(new Error('Escreva a descrição pública antes de mostrar o produto no site.'));
    const { hook, refetch } = setup([mk('a', null, false)]);
    await act(() => hook.result.current.setExibir(hook.result.current.products[0], true));
    expect(hook.result.current.error).toEqual({
      id: 'a', message: 'Escreva a descrição pública antes de mostrar o produto no site.',
    });
    expect(refetch).toHaveBeenCalled();
    expect(hook.result.current.busyId).toBeNull();
  });
});
