import { useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Building2,
  CreditCard,
  KeyRound,
  ClipboardList,
  Package,
  Wallet,
  Webhook,
  BarChart3,
  Settings,
  Zap,
  Users,
  LogOut,
  PackageOpen,
  Brain,
  FileText,
  Globe,
  BookOpen,
  UserPlus,
} from 'lucide-react';
import { useAuth } from '../../lib/auth-context';
import { api } from '../../lib/api';
import { NotificationBell } from '../NotificationBell';
import { AppShell, Sidebar, Header, useTheme } from '@noctusai/lib/design-system';
import type { NavGroup } from '@noctusai/lib/design-system';

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'admin',
    label: 'Administracao',
    icon: Settings,
    items: [
      { name: 'Dashboard', href: '/admin', icon: LayoutDashboard },
      { name: 'Usuarios', href: '/admin/users', icon: Users },
      { name: 'Organizacoes', href: '/admin/orgs', icon: Building2 },
      { name: 'Assinaturas', href: '/admin/subs', icon: CreditCard },
      { name: 'Chaves API', href: '/admin/api-keys', icon: KeyRound },
      { name: 'Chaves LLM', href: '/api-keys', icon: Brain },
      { name: 'Planos', href: '/admin/plans', icon: ClipboardList },
      { name: 'Produtos', href: '/admin/products', icon: Package },
      { name: 'Faturamento', href: '/admin/billing', icon: Wallet },
      { name: 'Webhooks', href: '/admin/webhooks', icon: Webhook },
      { name: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
      { name: 'Fleet Control', href: '/admin/fleet', icon: Zap },
      { name: 'Digest de auditoria', href: '/admin/audit-digest', icon: FileText },
      { name: 'Logout Behavior', href: '/admin/logout-behavior', icon: LogOut },
      { name: 'Templates', href: '/admin/templates', icon: PackageOpen },
      { name: 'Configuracoes', href: '/admin/settings', icon: Settings },
    ],
  },
  {
    key: 'website',
    label: 'Website',
    icon: Globe,
    items: [
      { name: 'Documentação', href: '/admin/website/docs', icon: BookOpen },
      { name: 'Configurações', href: '/admin/website/settings', icon: Settings },
      { name: 'Leads', href: '/admin/website/leads', icon: UserPlus },
    ],
  },
];

/**
 * A `marketing` user reaches only `/admin/website/*` (`CoreLayout`'s gate),
 * so the sidebar must show only the `website` group — derived from the SAME
 * `NAV_GROUPS` array (never a second hand-maintained list, contract §6 /
 * `docs/11 §Sidebar`). Any other role sees the full set (today: `admin`,
 * the only role `CoreLayout` otherwise lets through).
 */
export function visibleNavGroups(role: string | undefined): NavGroup[] {
  if (role === 'marketing') return NAV_GROUPS.filter((group) => group.key === 'website');
  return NAV_GROUPS;
}

export function Layout({ children }: { children?: React.ReactNode }) {
  const { user, logout, refresh } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();

  function handleLogout() {
    logout();
    navigate('/login');
  }

  const handleUpdateProfile = async (data: { name: string; email: string; phone: string }) => {
    await api.patch('/api/auth/profile', { nome: data.name });
    refresh();
  };

  const handleUpdatePassword = async (newPassword: string) => {
    await api.post('/api/auth/change-password', { new_password: newPassword });
  };

  const ROLE_LABELS: Record<string, string> = {
    admin: 'Administrador',
    manager: 'Gerente',
    user: 'Membro',
    marketing: 'Marketing',
  };

  const navGroups = visibleNavGroups(user?.role);

  const headerUser = {
    name: user?.nome || '',
    email: user?.email || '',
    role: ROLE_LABELS[user?.role || ''] || 'Membro',
    avatar: user?.avatar_url,
  };

  return (
    <AppShell
      sidebar={
        <Sidebar
          brandIcon={Zap}
          brandTitle="NoctusAI"
          brandSubtitle="Admin"
          brandHref="/"
          navGroups={navGroups}
        />
      }
      header={({ onMenuToggle }) => (
        <Header
          user={headerUser}
          onMenuToggle={onMenuToggle}
          onLogout={handleLogout}
          theme={theme}
          onThemeToggle={toggleTheme}
          onUpdateProfile={handleUpdateProfile}
          onUpdatePassword={handleUpdatePassword}
          actions={<NotificationBell />}
        />
      )}
    >
      <div className="p-4 sm:p-6 lg:p-8">{children}</div>
    </AppShell>
  );
}
