import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, clearToken, setToken, isAuthenticated, getRefreshToken, setRefreshToken } from './api';
import { useActivityRefresh } from '@noctusai/shared/design-system/useActivityRefresh';

interface User {
  id: string;
  nome: string;
  email: string;
  role: string;
  org_id: string;
  avatar_url?: string;
}

interface Organization {
  id: string;
  nome: string;
  slug: string;
  plano: string;
  category?: string;
}

interface AuthState {
  user: User | null;
  organization: Organization | null;
  isAdmin: boolean;
  loading: boolean;
}

interface AuthContextType extends AuthState {
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  organization: null,
  isAdmin: false,
  loading: true,
  logout: () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    organization: null,
    isAdmin: false,
    loading: true,
  });

  async function fetchProfile() {
    if (!isAuthenticated()) {
      setState({ user: null, organization: null, isAdmin: false, loading: false });
      return;
    }

    try {
      const data = await api.get('/api/auth/me');
      setState({
        user: data.user,
        organization: data.organization,
        isAdmin: data.user?.role === 'admin',
        loading: false,
      });
    } catch {
      clearToken();
      setState({ user: null, organization: null, isAdmin: false, loading: false });
    }
  }

  useEffect(() => {
    // Handle OAuth callback: check URL hash for access_token
    handleOAuthCallback().then(() => fetchProfile());
  }, []);

  async function handleOAuthCallback() {
    const hash = window.location.hash;
    if (!hash) return;

    // Parse hash fragment: #access_token=...&token_type=...&...
    const params = new URLSearchParams(hash.substring(1));
    const accessToken = params.get('access_token');

    if (!accessToken) return;

    // Clean up the URL hash
    window.history.replaceState(null, '', window.location.pathname + window.location.search);

    // Store the token
    setToken(accessToken);

    // Ensure noctus_users profile exists via OAuth callback
    try {
      // Determine provider from URL params or default to 'google'
      const provider = params.get('provider') || 'google';
      await api.post('/api/auth/oauth/callback', { provider });
    } catch {
      // Profile creation failed, but token is set — fetchProfile will handle it
    }
  }

  function logout() {
    clearToken();
    setState({ user: null, organization: null, isAdmin: false, loading: false });
  }

  // Proactive token refresh while user is active (every 5 min)
  const handleTokenRefresh = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) return;
    try {
      const res = await api.post('/api/auth/refresh', { refresh_token: refreshToken });
      if (res.access_token) setToken(res.access_token);
      if (res.refresh_token) setRefreshToken(res.refresh_token);
    } catch {
      // Refresh failed — token expired, user will be redirected on next API call
    }
  }, []);

  useActivityRefresh({
    onRefresh: handleTokenRefresh,
    enabled: !!state.user,
  });

  return (
    <AuthContext.Provider value={{ ...state, logout, refresh: fetchProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
