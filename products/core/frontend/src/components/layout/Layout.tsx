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
  ShieldCheck,
} from 'lucide-react';
import { useAuth } from '../../lib/auth-context';
import { CoreHeader } from './CoreHeader';
import { AppShell, Sidebar } from '@noctusai/lib/design-system';
import type { NavGroup } from '@noctusai/lib/design-system';

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'admin',
    label: 'Administracao',
    icon: Settings,
    items: [],
    groups: [
      {
        key: 'visao-geral',
        label: 'Visão geral',
        icon: LayoutDashboard,
        items: [
          { name: 'Dashboard', href: '/admin', icon: LayoutDashboard },
          { name: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
          { name: 'Digest de auditoria', href: '/admin/audit-digest', icon: FileText },
          { name: 'Fleet Control', href: '/admin/fleet', icon: Zap },
        ],
      },
      {
        key: 'clientes',
        label: 'Clientes',
        icon: Users,
        items: [
          { name: 'Usuarios', href: '/admin/users', icon: Users },
          { name: 'Organizacoes', href: '/admin/orgs', icon: Building2 },
        ],
      },
      {
        key: 'comercial',
        label: 'Comercial',
        icon: Wallet,
        items: [
          { name: 'Produtos', href: '/admin/products', icon: Package },
          { name: 'Planos', href: '/admin/plans', icon: ClipboardList },
          { name: 'Assinaturas', href: '/admin/subs', icon: CreditCard },
          { name: 'Faturamento', href: '/admin/billing', icon: Wallet },
        ],
      },
      {
        key: 'plataforma',
        label: 'Plataforma',
        icon: Settings,
        items: [
          { name: 'Chaves API', href: '/admin/api-keys', icon: KeyRound },
          { name: 'Chaves LLM', href: '/api-keys', icon: Brain },
          { name: 'Webhooks', href: '/admin/webhooks', icon: Webhook },
          { name: 'Templates', href: '/admin/templates', icon: PackageOpen },
          { name: 'Logout Behavior', href: '/admin/logout-behavior', icon: LogOut },
          { name: 'Configuracoes', href: '/admin/settings', icon: Settings },
          { name: 'Segurança', href: '/security', icon: ShieldCheck },
        ],
      },
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
  const { user } = useAuth();

  const navGroups = visibleNavGroups(user?.role);

  return (
    <AppShell
      sidebar={
        <Sidebar
          brandIcon={Zap}
          brandTitle="NoctusAI"
          brandSubtitle="Admin"
          brandHref="/"
          storageKey="core"
          navGroups={navGroups}
        />
      }
      header={({ onMenuToggle }) => (
        <CoreHeader onMenuToggle={onMenuToggle} profileEditable />
      )}
    >
      <div className="p-4 sm:p-6 lg:p-8">{children}</div>
    </AppShell>
  );
}
