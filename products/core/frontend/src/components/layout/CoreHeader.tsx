/**
 * CoreHeader: thin product-local wrapper OVER the canonical seed `Header`
 * (@noctusai/lib/design-system). It is NOT a re-implementation: it is the
 * declared named seam where core binds the seed Header to its own auth,
 * theme, logout semantics and notification bell, so the five core surfaces
 * (Layout, Dashboard, BillingSettings, Pricing, TeamManagement) configure it
 * ONCE instead of repeating the wiring.
 */
import type { ComponentProps, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header, useTheme } from '@noctusai/lib/design-system';
import { useAuth } from '../../lib/auth-context';
import { api } from '../../lib/api';
import { NotificationBell } from '../NotificationBell';

export const LOGOUT_LABEL = 'Sair de todos os dispositivos';

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  manager: 'Gerente',
  user: 'Membro',
  marketing: 'Marketing',
};

type SeedHeaderProps = ComponentProps<typeof Header>;

export interface CoreHeaderProps {
  /** Page-specific actions, rendered BEFORE the NotificationBell. */
  actions?: ReactNode;
  variant?: SeedHeaderProps['variant'];
  onMenuToggle?: SeedHeaderProps['onMenuToggle'];
  /** Enables the profile/password dialogs (needs the auth `refresh`). */
  profileEditable?: boolean;
}

export function CoreHeader({ actions, variant, onMenuToggle, profileEditable = false }: CoreHeaderProps) {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  const headerUser = {
    name: user?.nome || '',
    email: user?.email || '',
    role: ROLE_LABELS[user?.role || ''] || 'Membro',
    avatar: user?.avatar_url,
  };

  async function handleLogout() {
    await logout();
    navigate('/login');
  }

  const editProps = profileEditable
    ? {
        onUpdateProfile: async (data: { name: string; email: string; phone: string }) => {
          await api.patch('/api/auth/profile', { nome: data.name });
          refresh();
        },
        onUpdatePassword: async (newPassword: string) => {
          await api.post('/api/auth/change-password', { new_password: newPassword });
        },
      }
    : {};

  return (
    <Header
      user={headerUser}
      variant={variant}
      onMenuToggle={onMenuToggle}
      onLogout={handleLogout}
      logoutLabel={LOGOUT_LABEL}
      theme={theme}
      onThemeToggle={toggleTheme}
      actions={
        <div className="flex items-center gap-2">
          {actions}
          <NotificationBell />
        </div>
      }
      {...editProps}
    />
  );
}
