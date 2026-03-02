import { useEffect, useState, useRef, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || "http://localhost:8000";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

type SSOState =
  | { status: "loading"; message: string }
  | { status: "rate_limited"; retryIn: number }
  | { status: "error"; message: string };

function isSessionValid(expiresAt: number | undefined): boolean {
  if (!expiresAt) return false;
  return expiresAt > Math.floor(Date.now() / 1000) + 60;
}

export default function SSOCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<SSOState>({ status: "loading", message: "Verificando sessao..." });
  const cancelledRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const clearTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = undefined; }
  }, []);

  const callBackend = useCallback(async (token: string): Promise<boolean> => {
    setState({ status: "loading", message: "Autenticando via NoctusAI..." });
    const response = await fetch(`${CORE_API_URL}/api/sso/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });

    if (response.status === 429) {
      const retryAfter = parseInt(response.headers.get("Retry-After") || "60", 10);
      startCountdown(retryAfter, token);
      return false;
    }
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Erro ao validar token SSO");
    }

    const { access_token, refresh_token } = await response.json();
    const { error } = await supabase.auth.setSession({ access_token, refresh_token });
    if (error) throw new Error(error.message);
    return true;
  }, []);

  const startCountdown = useCallback((seconds: number, token: string) => {
    clearTimer();
    let remaining = seconds;
    setState({ status: "rate_limited", retryIn: remaining });
    timerRef.current = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) { clearTimer(); handleSSO(token); }
      else setState({ status: "rate_limited", retryIn: remaining });
    }, 1000);
  }, [clearTimer]);

  const handleSSO = useCallback(async (token: string) => {
    if (cancelledRef.current) return;
    try {
      setState({ status: "loading", message: "Verificando sessao..." });
      const { data: { session } } = await supabase.auth.getSession();
      if (cancelledRef.current) return;
      if (session && isSessionValid(session.expires_at)) { navigate("/", { replace: true }); return; }

      if (session) {
        setState({ status: "loading", message: "Renovando sessao..." });
        const { data: { session: refreshed }, error } = await supabase.auth.refreshSession();
        if (cancelledRef.current) return;
        if (refreshed && !error && isSessionValid(refreshed.expires_at)) { navigate("/", { replace: true }); return; }
      }

      if (cancelledRef.current) return;
      const success = await callBackend(token);
      if (cancelledRef.current) return;
      if (success) navigate("/", { replace: true });
    } catch (err: any) {
      if (!cancelledRef.current) setState({ status: "error", message: err.message || "Erro ao processar login SSO." });
    }
  }, [navigate, callBackend]);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) { setState({ status: "error", message: "Token SSO nao encontrado na URL." }); return; }
    cancelledRef.current = false;
    handleSSO(token);
    return () => { cancelledRef.current = true; clearTimer(); };
  }, [searchParams, handleSSO, clearTimer]);

  if (state.status === "rate_limited") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full bg-card rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-4xl">&#9202;</div>
          <h1 className="text-xl font-semibold">Aguardando limite de requisicoes</h1>
          <p className="text-muted-foreground">Tentando novamente em:</p>
          <div className="text-3xl font-bold text-primary">{state.retryIn}s</div>
          <a href={CORE_URL} className="inline-block mt-2 text-sm text-muted-foreground hover:text-foreground underline">Voltar ao NoctusAI</a>
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="max-w-md w-full bg-card rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-destructive text-4xl">!</div>
          <h1 className="text-xl font-semibold">Erro no login SSO</h1>
          <p className="text-muted-foreground">{state.message}</p>
          <div className="flex flex-col gap-2">
            <button onClick={() => { const t = searchParams.get("token"); if (t) handleSSO(t); }} className="px-4 py-2 bg-primary text-primary-foreground rounded hover:opacity-90 transition">Tentar novamente</button>
            <a href={CORE_URL} className="inline-block px-4 py-2 text-muted-foreground hover:text-foreground transition">Voltar ao NoctusAI</a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center space-y-4">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto" />
        <p className="text-muted-foreground">{state.message}</p>
      </div>
    </div>
  );
}
