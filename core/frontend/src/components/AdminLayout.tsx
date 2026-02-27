import React, { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth-context';

const NAV_ITEMS = [
  { to: '/admin', label: 'Dashboard', icon: '📊', end: true },
  { to: '/admin/orgs', label: 'Organizações', icon: '🏢', end: false },
  { to: '/admin/subs', label: 'Assinaturas', icon: '💳', end: false },
  { to: '/admin/api-keys', label: 'Chaves API', icon: '🔑', end: false },
  { to: '/admin/plans', label: 'Planos', icon: '📋', end: false },
  { to: '/admin/billing', label: 'Faturamento', icon: '💰', end: false },
  { to: '/admin/webhooks', label: 'Webhooks', icon: '🔗', end: false },
  { to: '/admin/analytics', label: 'Analytics', icon: '📈', end: false },
  { to: '/admin/settings', label: 'Configurações', icon: '⚙️', end: false },
];

export function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <div className="admin-layout">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="admin-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <aside className={`admin-sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="admin-sidebar-header">
          <span className="logo-icon">⚡</span>
          <h2>NoctusAI</h2>
          <span className="admin-badge">Admin</span>
        </div>

        <nav className="admin-nav">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `admin-nav-item ${isActive ? 'active' : ''}`}
              onClick={() => setSidebarOpen(false)}
            >
              <span className="admin-nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="admin-sidebar-footer">
          <button className="admin-nav-item" onClick={() => navigate('/')}>
            <span className="admin-nav-icon">←</span>
            Voltar ao Painel
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="admin-content">
        <header className="admin-header">
          <button className="admin-menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            ☰
          </button>
          <div className="admin-header-right">
            <span className="admin-user-name">{user?.nome}</span>
            <button className="btn-logout" onClick={handleLogout}>Sair</button>
          </div>
        </header>
        <main className="admin-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
