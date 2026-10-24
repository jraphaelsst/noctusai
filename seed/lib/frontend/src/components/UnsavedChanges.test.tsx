import * as React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import {
  UNSAVED_CHANGES_MESSAGE,
  UnsavedChangesNotice,
  changedFields,
  sameFieldValue,
  useBeforeUnloadGuard,
  useUnsavedChanges,
} from './UnsavedChanges';

type Draft = { matricula: string; cartorio: string | null; tags: string[] };
const SAVED: Draft = { matricula: '123', cartorio: null, tags: ['a'] };

function Card({ loading = false, fields }: { loading?: boolean; fields?: (keyof Draft)[] }) {
  const saved = loading ? undefined : SAVED;
  const [draft, setDraft] = React.useState<Draft>(saved ?? { matricula: '', cartorio: '', tags: [] });
  const { dirty, changed } = useUnsavedChanges(draft, saved, { fields });
  return (
    <div>
      <input aria-label="matricula" value={draft.matricula} onChange={(e) => setDraft({ ...draft, matricula: e.target.value })} />
      <input aria-label="cartorio" value={draft.cartorio ?? ''} onChange={(e) => setDraft({ ...draft, cartorio: e.target.value })} />
      <span data-testid="changed">{changed.join(',')}</span>
      <UnsavedChangesNotice dirty={dirty} />
    </div>
  );
}

afterEach(() => vi.restoreAllMocks());

describe('sameFieldValue / changedFields', () => {
  it('treats null, undefined and "" as the same empty value', () => {
    expect(sameFieldValue(null, '')).toBe(true);
    expect(sameFieldValue(undefined, null)).toBe(true);
    expect(sameFieldValue('', 'x')).toBe(false);
  });

  it('compares arrays and objects structurally', () => {
    expect(sameFieldValue(['a', { b: 1 }], ['a', { b: 1 }])).toBe(true);
    expect(sameFieldValue({ a: 1 }, { a: 2 })).toBe(false);
    expect(sameFieldValue([1], [1, 2])).toBe(false);
  });

  it('lists only the changed fields, honours `fields`, and is clean while loading', () => {
    expect(changedFields({ ...SAVED, matricula: '9' }, SAVED)).toEqual(['matricula']);
    expect(changedFields({ ...SAVED, matricula: '9' }, SAVED, ['cartorio'])).toEqual([]);
    expect(changedFields(SAVED, undefined)).toEqual([]);
  });
});

describe('useUnsavedChanges + UnsavedChangesNotice', () => {
  it('is clean on mount, says "não salvas" after an edit, and clean again when reverted', () => {
    render(<Card />);
    expect(screen.queryByText(UNSAVED_CHANGES_MESSAGE)).toBeNull();
    fireEvent.change(screen.getByLabelText('matricula'), { target: { value: '124' } });
    expect(screen.getByRole('status').textContent).toBe(UNSAVED_CHANGES_MESSAGE);
    expect(screen.getByTestId('changed').textContent).toBe('matricula');
    fireEvent.change(screen.getByLabelText('matricula'), { target: { value: '123' } });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('typing then clearing an empty field is not a change (null ≡ "")', () => {
    render(<Card />);
    fireEvent.change(screen.getByLabelText('cartorio'), { target: { value: 'x' } });
    expect(screen.getByRole('status')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('cartorio'), { target: { value: '' } });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('never reports dirty while the saved value is still loading', () => {
    render(<Card loading />);
    fireEvent.change(screen.getByLabelText('matricula'), { target: { value: 'x' } });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('guards a page unload only while dirty', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    render(<Card />);
    expect(add.mock.calls.some(([t]) => t === 'beforeunload')).toBe(false);
    fireEvent.change(screen.getByLabelText('matricula'), { target: { value: '124' } });
    const call = add.mock.calls.find(([t]) => t === 'beforeunload');
    expect(call).toBeTruthy();
    const ev = new Event('beforeunload', { cancelable: true });
    act(() => {
      (call![1] as EventListener)(ev);
    });
    expect(ev.defaultPrevented).toBe(true);
    fireEvent.change(screen.getByLabelText('matricula'), { target: { value: '123' } });
    expect(remove.mock.calls.some(([t]) => t === 'beforeunload')).toBe(true);
  });
});

describe('useBeforeUnloadGuard', () => {
  function Guard({ active }: { active: boolean }) {
    useBeforeUnloadGuard(active);
    return null;
  }
  it('listens only while active', () => {
    const add = vi.spyOn(window, 'addEventListener');
    const { rerender } = render(<Guard active={false} />);
    expect(add.mock.calls.some(([t]) => t === 'beforeunload')).toBe(false);
    rerender(<Guard active />);
    expect(add.mock.calls.some(([t]) => t === 'beforeunload')).toBe(true);
  });
});
