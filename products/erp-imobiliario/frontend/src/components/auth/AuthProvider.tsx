import { useEffect } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { useAuthStore } from '@/store/authStore';

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { setUser } = useAuthStore();

  // Atualizar última atividade do usuário - o banco gerencia o timestamp automaticamente
  const updateLastActivity = async (userId: string) => {
    try {
      await supabase
        .from('profiles')
        .update({ last_activity_at: new Date().toISOString() })
        .eq('id', userId);
    } catch (error) {
      console.error('Erro ao atualizar última atividade:', error);
    }
  };

  // Registrar ação de login/logout
  const registerAuthAction = async (userId: string, action: 'login' | 'logout') => {
    try {
      await supabase.from("user_actions_log").insert({
        usuario_id: userId,
        tipo_acao: action,
        tipo_entidade: 'auth',
        descricao: action === 'login' ? 'Fez login na plataforma' : 'Fez logout da plataforma',
      });
    } catch (error) {
      console.error('Erro ao registrar ação de auth:', error);
    }
  };

  useEffect(() => {
    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        updateLastActivity(session.user.id);
      }
    });

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user ?? null);
      if (session?.user) {
        updateLastActivity(session.user.id);
        
        // Registrar login/logout
        if (event === 'SIGNED_IN') {
          setTimeout(() => registerAuthAction(session.user.id, 'login'), 0);
        } else if (event === 'SIGNED_OUT') {
          setTimeout(() => registerAuthAction(session.user.id, 'logout'), 0);
        }
      }
    });

    return () => subscription.unsubscribe();
  }, [setUser]);

  // Atualizar atividade periodicamente enquanto o usuário está ativo
  useEffect(() => {
    const interval = setInterval(async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.user) {
        updateLastActivity(session.user.id);
      }
    }, 5 * 60 * 1000); // A cada 5 minutos

    return () => clearInterval(interval);
  }, []);

  return <>{children}</>;
}