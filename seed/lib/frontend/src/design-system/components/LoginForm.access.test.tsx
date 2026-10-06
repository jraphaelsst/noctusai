/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Lock } from 'lucide-react';
import { LoginForm } from './LoginForm';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const supabase = {
  auth: {
    signInWithPassword: vi.fn().mockResolvedValue({
      data: { session: { access_token: 'tok' } },
      error: null,
    }),
  },
};

async function submit() {
  await userEvent.type(screen.getByLabelText('Email'), 'a@b.com');
  await userEvent.type(screen.getByLabelText('Senha'), 'secret1');
  await userEvent.click(screen.getByRole('button', { name: 'Entrar' }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('LoginForm license gate', () => {
  it('routes to no-access when has_access=false', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ has_access: false }), { status: 200 }),
    ));
    const onSuccess = vi.fn();
    const onNoAccess = vi.fn();
    render(<LoginForm brandIcon={Lock} brandTitle="X" supabase={supabase} onSuccess={onSuccess} onNoAccess={onNoAccess} accessBaseUrl="http://p" />);
    await submit();
    await waitFor(() => expect(onNoAccess).toHaveBeenCalled());
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('proceeds when has_access=true', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ has_access: true }), { status: 200 }));
    vi.stubGlobal('fetch', f);
    const onSuccess = vi.fn();
    const onNoAccess = vi.fn();
    render(<LoginForm brandIcon={Lock} brandTitle="X" supabase={supabase} onSuccess={onSuccess} onNoAccess={onNoAccess} accessBaseUrl="http://p" />);
    await submit();
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(onNoAccess).not.toHaveBeenCalled();
    expect(f.mock.calls[0][0]).toBe('http://p/api/me/access');
  });
});
