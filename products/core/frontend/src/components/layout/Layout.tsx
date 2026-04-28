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
  ArrowLeft,
  Zap,
  Users,
  LogOut,
  PackageOpen,
  Brain,
  FileText,
} from 'lucide-react';
import { useAuth } from '../../lib/auth-context';
import { api } from '../../lib/api';
import { NotificationBell } from '../NotificationBell';
import { AppShell, Sidebar, Header, useTheme } from '@noctusai/lib/design-system';
import type { NavGroup, NavItem } from '@noctusai/lib/design-system';

const NAV_GROUPS: NavGroup[] = [
  {
    key: 'admin',
    label: 'Administracao',
    icon: Settings,
    defaultOpen: true,
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
      { name: 'Digest de auditoria', href: '/admin/audit-digest', icon: FileText },
      { name: 'Logout Behavior', href: '/admin/logout-behavior', icon: LogOut },
      { name: 'Templates', href: '/admin/templates', icon: PackageOpen },
      { name: 'Configuracoes', href: '/admin/settings', icon: Settings },
    ],
  },
];

const FOOTER_NAV: NavItem[] = [
  { name: 'Voltar ao Painel', href: '/', icon: ArrowLeft },
];

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
  };

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
          navGroups={NAV_GROUPS}
          standaloneItems={FOOTER_NAV}
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
