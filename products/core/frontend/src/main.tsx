/**
 * NoctusAI Core — Frontend entry point.
 *
 * Migrated to the seed framework via `createProductApp({ authProvider })` —
 * Phase 4 of `core-seed-wiring`. Core supplies its own auth provider (custom
 * JWT + refresh-token) because core IS the identity provider that Supabase
 * delegates to for every consumer product. The framework owns routing,
 * providers, error boundary, suspense; core owns auth + layout branching.
 */
import React, { lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { createProductApp } from '@noctusai/seed';
import { coreAuthProvider } from './lib/seed-auth-adapter';
import { CoreLayout } from './components/layout/CoreLayout';
import { notificationHooks, openInProduct } from './components/NotificationBell';
import './index.css';

// Pages — lazy-wrapped so the framework's Suspense fallback renders.
const Login = lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const Landing = lazy(() => import('./pages/Landing'));
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Pricing = lazy(() => import('./pages/Pricing').then(m => ({ default: m.Pricing })));
const BillingSettings = lazy(() => import('./pages/BillingSettings').then(m => ({ default: m.BillingSettings })));
const CheckoutSuccess = lazy(() => import('./pages/CheckoutSuccess').then(m => ({ default: m.CheckoutSuccess })));
const CheckoutCancel = lazy(() => import('./pages/CheckoutCancel').then(m => ({ default: m.CheckoutCancel })));
const TeamManagement = lazy(() => import('./pages/TeamManagement').then(m => ({ default: m.TeamManagement })));
const AccountSettings = lazy(() => import('./pages/AccountSettings').then(m => ({ default: m.AccountSettings })));
const Security = lazy(() => import('./pages/Security').then(m => ({ default: m.Security })));
const BrandIdentity = lazy(() => import('./pages/BrandIdentity').then(m => ({ default: m.BrandIdentity })));
const CreditosUso = lazy(() => import('./pages/credits/CreditosUso').then(m => ({ default: m.CreditosUso })));
const OrgSettings = lazy(() => import('./pages/OrgSettings').then(m => ({ default: m.OrgSettings })));
const APIKeys = lazy(() => import('./pages/APIKeys').then(m => ({ default: m.APIKeys })));
const Onboarding = lazy(() => import('./pages/Onboarding').then(m => ({ default: m.Onboarding })));
const EsqueciSenha = lazy(() => import('./pages/EsqueciSenha').then(m => ({ default: m.EsqueciSenha })));
const RedefinirSenha = lazy(() => import('./pages/RedefinirSenha').then(m => ({ default: m.RedefinirSenha })));
const AcceptInvite = lazy(() => import('./pages/AcceptInvite').then(m => ({ default: m.AcceptInvite })));

// Unknown-path fallback. For a platform admin / marketing user it loads the code-split admin
// surface and renders the matching admin page; for EVERYONE ELSE it renders the plain NotFound, so
// an admin URL is indistinguishable from any other unknown URL (no redirect, no "forbidden").
const CatchAll = lazy(() => import('./pages/CatchAll'));

const App = createProductApp({
  authProvider: coreAuthProvider,
  notifications: { hooks: notificationHooks, onNavigateProduct: openInProduct },
  Layout: CoreLayout,
  NotFound: CatchAll,
  Login,
  Landing,
  unauthRedirect: '/login',
  publicRoutes: [
    { path: '/invite/:token', component: AcceptInvite },
    // Central-login recovery (sso-entry contract). PUBLIC on purpose; keep above any catch-all.
    { path: '/esqueci-senha', component: EsqueciSenha },
    { path: '/redefinir-senha', component: RedefinirSenha },
  ],
  routes: [
    { path: '/', component: Dashboard },
    { path: '/painel', component: Dashboard },
    { path: '/pricing', component: Pricing },
    { path: '/billing', component: BillingSettings },
    { path: '/checkout/success', component: CheckoutSuccess },
    { path: '/checkout/cancel', component: CheckoutCancel },
    { path: '/team', component: TeamManagement },
    { path: '/settings', component: AccountSettings },
    { path: '/security', component: Security },
    { path: '/org-settings', component: OrgSettings },
    { path: '/org-settings/identidade', component: BrandIdentity },
    { path: '/org-settings/creditos', component: CreditosUso },
    { path: '/api-keys', component: APIKeys },
    { path: '/settings/api-keys', component: APIKeys },
    { path: '/onboarding', component: Onboarding },
  ],
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
