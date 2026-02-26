import { useEffect, useState, useRef, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";

const CORE_API_URL = import.meta.env.VITE_CORE_API_URL || "http://localhost:8001";
const CORE_URL = import.meta.env.VITE_CORE_URL || "http://localhost:5173";

type SSOState =
  | { status: "loading"; message: string }
  | { status: "rate_limited"; retryIn: number }
  | { status: "error"; message: string };

function isSessionValid(expiresAt: number | undefined): boolean {
  if (!expiresAt) return false;
  // Valid if expires more than 60s from now
  return expiresAt > Math.floor(Date.now() / 1000) + 60;
}

export default function SSOCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [state, setState] = useState<SSOState>({ status: "loading", message: "Verificando sessão..." });
  const cancelledRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = undefined;
    }
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

    const { error: sessionError } = await supabase.auth.setSession({
      access_token,
      refresh_token,
    });

    if (sessionError) {
      throw new Error(sessionError.message);
    }

    return true;
  }, []);

  const startCountdown = useCallback((seconds: number, token: string) => {
    clearTimer();
    let remaining = seconds;
    setState({ status: "rate_limited", retryIn: remaining });

    timerRef.current = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearTimer();
        // Auto-retry
        handleSSO(token);
      } else {
        setState({ status: "rate_limited", retryIn: remaining });
      }
    }, 1000);
  }, [clearTimer]);

  const handleSSO = useCallback(async (token: string) => {
    if (cancelledRef.current) return;

    try {
      // Stage 1: Check existing session
      setState({ status: "loading", message: "Verificando sessão..." });
      const { data: { session: existingSession } } = await supabase.auth.getSession();

      if (cancelledRef.current) return;

      if (existingSession && isSessionValid(existingSession.expires_at)) {
        navigate("/", { replace: true });
        return;
      }

      // Stage 2: Try refresh if we have an expired session
      if (existingSession) {
        setState({ status: "loading", message: "Renovando sessão..." });
        const { data: { session: refreshed }, error: refreshError } = await supabase.auth.refreshSession();

        if (cancelledRef.current) return;

        if (refreshed && !refreshError && isSessionValid(refreshed.expires_at)) {
          navigate("/", { replace: true });
          return;
        }
      }

      // Stage 3: Call backend
      if (cancelledRef.current) return;
      const success = await callBackend(token);

      if (cancelledRef.current) return;
      if (success) {
        navigate("/", { replace: true });
      }
    } catch (err: any) {
      if (!cancelledRef.current) {
        setState({ status: "error", message: err.message || "Erro ao processar login SSO." });
      }
    }
  }, [navigate, callBackend]);

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) {
      setState({ status: "error", message: "Token SSO não encontrado na URL." });
      return;
    }

    cancelledRef.current = false;
    handleSSO(token);

    return () => {
      cancelledRef.current = true;
      clearTimer();
    };
  }, [searchParams, handleSSO, clearTimer]);

  // Rate limited — countdown UI
  if (state.status === "rate_limited") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-yellow-500 text-4xl">&#9202;</div>
          <h1 className="text-xl font-semibold text-gray-900">Aguardando limite de requisições</h1>
          <p className="text-gray-600">
            O servidor atingiu o limite temporário. Tentando novamente em:
          </p>
          <div className="text-3xl font-bold text-blue-600">{state.retryIn}s</div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-1000"
              style={{ width: `${Math.max(0, ((60 - state.retryIn) / 60) * 100)}%` }}
            />
          </div>
          <a
            href={CORE_URL}
            className="inline-block mt-2 text-sm text-gray-500 hover:text-gray-700 underline"
          >
            Voltar ao NoctusAI
          </a>
        </div>
      </div>
    );
  }

  // Error — retry button
  if (state.status === "error") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="max-w-md w-full bg-white rounded-lg shadow p-8 text-center space-y-4">
          <div className="text-red-500 text-4xl">!</div>
          <h1 className="text-xl font-semibold text-gray-900">Erro no login SSO</h1>
          <p className="text-gray-600">{state.message}</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => {
                const token = searchParams.get("token");
                if (token) handleSSO(token);
              }}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition"
            >
              Tentar novamente
            </button>
            <a
              href={CORE_URL}
              className="inline-block px-4 py-2 text-gray-600 hover:text-gray-800 transition"
            >
              Voltar ao NoctusAI
            </a>
          </div>
        </div>
      </div>
    );
  }

  // Loading — progressive message
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center space-y-4">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto" />
        <p className="text-gray-600">{state.message}</p>
      </div>
    </div>
  );
}
