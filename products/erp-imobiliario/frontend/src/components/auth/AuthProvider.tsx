import { useEffect } from 'react';
import { createAuthProvider } from '@noctusai/lib/components';
import { supabase, useAuthStore } from '@noctusai/seed/infra';

const BaseAuthProvider = createAuthProvider(supabase, useAuthStore);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // ERP-specific: update last activity
  const updateLastActivity = async (userId: string) => {
    try {
      await supabase
        .from('profiles')
        .update({ last_activity_at: new Date().toISOString() })
        .eq('id', userId);
    } catch (error) {
      console.error('Erro ao atualizar ultima atividade:', error);
    }
  };

  // ERP-specific: register login/logout action
  const registerAuthAction = async (userId: string, action: 'login' | 'logout') => {
    try {
      await supabase.from("user_actions_log").insert({
        usuario_id: userId,
        tipo_acao: action,
        tipo_entidade: 'auth',
        descricao: action === 'login' ? 'Fez login na plataforma' : 'Fez logout da plataforma',
      });
    } catch (error) {
      console.error('Erro ao registrar acao de auth:', error);
    }
  };

  // ERP-specific: activity tracking + action logging on auth changes
  useEffect(() => {
    // Update activity on initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        updateLastActivity(session.user.id);
      }
    });

    // Listen for auth events to log actions + update activity
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (session?.user) {
        updateLastActivity(session.user.id);

        if (event === 'SIGNED_IN') {
          setTimeout(() => registerAuthAction(session.user.id, 'login'), 0);
        } else if (event === 'SIGNED_OUT') {
          setTimeout(() => registerAuthAction(session.user.id, 'logout'), 0);
        }
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  // ERP-specific: periodic activity heartbeat
  useEffect(() => {
    const interval = setInterval(async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.user) {
        updateLastActivity(session.user.id);
      }
    }, 5 * 60 * 1000);

    return () => clearInterval(interval);
  }, []);

  return <BaseAuthProvider>{children}</BaseAuthProvider>;
}
