import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './lib/auth-context';
import { isAuthenticated } from './lib/api';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Pricing } from './pages/Pricing';
import { BillingSettings } from './pages/BillingSettings';
import { CheckoutSuccess } from './pages/CheckoutSuccess';
import { CheckoutCancel } from './pages/CheckoutCancel';
import { AdminLayout } from './components/AdminLayout';
import { AdminDashboard } from './pages/admin/AdminDashboard';
import { AdminOrganizations } from './pages/admin/AdminOrganizations';
import { AdminSubscriptions } from './pages/admin/AdminSubscriptions';
import { AdminApiKeys } from './pages/admin/AdminApiKeys';
import { AdminPlans } from './pages/admin/AdminPlans';
import { AdminProducts } from './pages/admin/AdminProducts';
import { AdminBilling } from './pages/admin/AdminBilling';
import { AdminWebhooks } from './pages/admin/AdminWebhooks';
import { AdminAnalytics } from './pages/admin/AdminAnalytics';
import { AdminSettings } from './pages/admin/AdminSettings';
import { Onboarding } from './pages/Onboarding';
import { TeamManagement } from './pages/TeamManagement';
import { AcceptInvite } from './pages/AcceptInvite';
import { AccountSettings } from './pages/AccountSettings';
import { OrgSettings } from './pages/OrgSettings';
import './index.css';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { loading } = useAuth();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (loading) return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  return <>{children}</>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  const { isAdmin, loading } = useAuth();
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  if (loading) return <div className="loading-screen"><div className="spinner" /><p>Carregando...</p></div>;
  if (!isAdmin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/pricing" element={<ProtectedRoute><Pricing /></ProtectedRoute>} />
          <Route path="/billing" element={<ProtectedRoute><BillingSettings /></ProtectedRoute>} />
          <Route path="/checkout/success" element={<ProtectedRoute><CheckoutSuccess /></ProtectedRoute>} />
          <Route path="/checkout/cancel" element={<ProtectedRoute><CheckoutCancel /></ProtectedRoute>} />
          <Route path="/team" element={<ProtectedRoute><TeamManagement /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><AccountSettings /></ProtectedRoute>} />
          <Route path="/org-settings" element={<ProtectedRoute><OrgSettings /></ProtectedRoute>} />
          <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />

          {/* Public route — accept invitation (no ProtectedRoute wrapper) */}
          <Route path="/invite/:token" element={<AcceptInvite />} />

          {/* Admin routes */}
          <Route path="/admin" element={<AdminRoute><AdminLayout /></AdminRoute>}>
            <Route index element={<AdminDashboard />} />
            <Route path="orgs" element={<AdminOrganizations />} />
            <Route path="subs" element={<AdminSubscriptions />} />
            <Route path="api-keys" element={<AdminApiKeys />} />
            <Route path="plans" element={<AdminPlans />} />
            <Route path="products" element={<AdminProducts />} />
            <Route path="billing" element={<AdminBilling />} />
            <Route path="webhooks" element={<AdminWebhooks />} />
            <Route path="analytics" element={<AdminAnalytics />} />
            <Route path="settings" element={<AdminSettings />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
