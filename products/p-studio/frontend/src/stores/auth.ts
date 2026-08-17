import { create } from "zustand";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "@/lib/supabase";
import { api } from "@/lib/api";
import type { Me } from "@/types";

interface AuthState {
  session: Session | null;
  me: Me | null;
  loading: boolean;
  error: string | null;
  init: () => void;
  signOut: () => Promise<void>;
}

let initialized = false;

/**
 * Sessão do Supabase + perfil vindo de `GET /api/me`. Carregar o perfil no
 * boot serve a dois propósitos: saber quem é o usuário e provar que o backend
 * responde antes de renderizar qualquer tela.
 */
export const useAuth = create<AuthState>((set, get) => ({
  session: null,
  me: null,
  loading: true,
  error: null,

  init: () => {
    if (initialized) return;
    initialized = true;

    const carregarPerfil = async (session: Session | null) => {
      if (!session) {
        set({ session: null, me: null, loading: false, error: null });
        return;
      }
      set({ session, loading: true });
      try {
        const me = await api.get<Me>("/api/me");
        set({ me, loading: false, error: null });
      } catch (e: any) {
        set({ me: null, loading: false, error: e.message ?? "Erro ao carregar perfil" });
      }
    };

    supabase.auth.getSession().then(({ data }) => carregarPerfil(data.session));
    supabase.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT") {
        set({ session: null, me: null, loading: false, error: null });
      } else if (event === "SIGNED_IN" && session?.user.id !== get().session?.user.id) {
        carregarPerfil(session);
      } else if (session) {
        set({ session });
      }
    });
  },

  signOut: async () => {
    await supabase.auth.signOut();
    set({ session: null, me: null, error: null });
  },
}));
