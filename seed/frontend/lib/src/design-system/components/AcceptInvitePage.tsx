/**
 * NoctusAI Shared Accept Invite Page
 *
 * Reusable page that handles the full invitation acceptance flow:
 * 1. Validates the invite token via GET to the accept endpoint
 * 2. Shows a signup form (nome + password + confirm password)
 * 3. Submits to the product's accept endpoint
 * 4. Shows success/error states
 *
 * Does NOT use Supabase client — calls the backend directly via fetch.
 * The backend handles auth user creation from the invitation record.
 *
 * Zero external dependencies beyond React + lucide-react.
 */
import { useState, useEffect } from "react";
import type { LucideIcon } from "lucide-react";
import { Loader2, CheckCircle2, AlertTriangle } from "lucide-react";

export interface AcceptInvitePageProps {
  /** Human-readable product name (e.g., "ERP Imobiliario") */
  productName: string;
  /** Lucide icon component for branding */
  brandIcon: LucideIcon;
  /** Backend endpoint for accepting invitations (e.g., "/api/team/accept") */
  acceptEndpoint: string;
  /** Backend base URL (e.g., from VITE_BACKEND_API_URL) */
  apiBaseUrl: string;
  /** Called after successful acceptance */
  onAccepted?: () => void;
  /** Path for "already have account" link (default "/login") */
  loginPath?: string;
  /** Invite token — if not provided, extracted from URL search params (?token=...) */
  token?: string;
}

type PageState = "loading" | "form" | "submitting" | "success" | "error";

interface InviteInfo {
  email: string;
  role?: string;
  org_name?: string;
}

const INPUT_CLS =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50";

export function AcceptInvitePage({
  productName,
  brandIcon: BrandIcon,
  acceptEndpoint,
  apiBaseUrl,
  onAccepted,
  loginPath = "/login",
  token: tokenProp,
}: AcceptInvitePageProps) {
  const [state, setState] = useState<PageState>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [inviteInfo, setInviteInfo] = useState<InviteInfo | null>(null);

  // Form fields
  const [nome, setNome] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [nomeError, setNomeError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [confirmError, setConfirmError] = useState("");

  // Extract token from URL or prop
  const token = tokenProp ?? new URLSearchParams(window.location.search).get("token") ?? "";

  // Validate the invite token on mount
  useEffect(() => {
    if (!token) {
      setErrorMessage("Token de convite nao encontrado na URL.");
      setState("error");
      return;
    }

    async function validateToken() {
      try {
        const res = await fetch(
          `${apiBaseUrl}${acceptEndpoint}/validate?token=${encodeURIComponent(token)}`,
        );
        if (!res.ok) {
          const data = await res.json().catch(() => null);
          const msg =
            data?.detail || data?.error?.message || "Convite invalido ou expirado.";
          setErrorMessage(typeof msg === "string" ? msg : "Convite invalido ou expirado.");
          setState("error");
          return;
        }
        const data = await res.json();
        const info: InviteInfo = {
          email: data.data?.email ?? data.email ?? "",
          role: data.data?.role ?? data.role,
          org_name: data.data?.org_name ?? data.org_name,
        };
        setInviteInfo(info);
        setState("form");
      } catch {
        setErrorMessage("Erro ao validar convite. Tente novamente.");
        setState("error");
      }
    }

    validateToken();
  }, [token, apiBaseUrl, acceptEndpoint]);

  function validate(): boolean {
    let valid = true;
    setNomeError("");
    setPasswordError("");
    setConfirmError("");

    if (!nome.trim()) {
      setNomeError("Nome e obrigatorio");
      valid = false;
    }
    if (!password || password.length < 6) {
      setPasswordError("Senha deve ter no minimo 6 caracteres");
      valid = false;
    }
    if (password !== confirmPassword) {
      setConfirmError("Senhas nao conferem");
      valid = false;
    }
    return valid;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setState("submitting");
    try {
      const res = await fetch(`${apiBaseUrl}${acceptEndpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, nome: nome.trim(), password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        const msg =
          data?.detail || data?.error?.message || "Erro ao aceitar convite.";
        setErrorMessage(typeof msg === "string" ? msg : "Erro ao aceitar convite.");
        setState("error");
        return;
      }

      setState("success");
    } catch {
      setErrorMessage("Erro de conexao. Tente novamente.");
      setState("error");
    }
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-background p-4">
      <div className="w-full max-w-md bg-card rounded-lg border border-border shadow-sm">
        {/* Header */}
        <div className="flex flex-col items-center p-6 pb-2">
          <BrandIcon className="h-10 w-10 text-primary mb-2" />
          <h1 className="text-2xl font-semibold text-foreground">Aceitar Convite</h1>
          <p className="text-sm text-muted-foreground mt-1">{productName}</p>
        </div>

        {/* Content */}
        <div className="p-6 pt-4">
          {/* ── Loading ── */}
          {state === "loading" && (
            <div className="flex flex-col items-center py-8 gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Validando convite...</p>
            </div>
          )}

          {/* ── Error ── */}
          {state === "error" && (
            <div className="flex flex-col items-center py-8 gap-3">
              <AlertTriangle className="h-8 w-8 text-destructive" />
              <p className="text-sm text-destructive text-center">{errorMessage}</p>
              <a
                href={loginPath}
                className="text-sm text-primary hover:underline font-medium mt-2"
              >
                Voltar ao login
              </a>
            </div>
          )}

          {/* ── Success ── */}
          {state === "success" && (
            <div className="flex flex-col items-center py-8 gap-3">
              <CheckCircle2 className="h-8 w-8 text-green-600" />
              <p className="text-sm text-foreground font-medium">
                Conta criada com sucesso!
              </p>
              <p className="text-sm text-muted-foreground text-center">
                Voce ja pode fazer login com seu email e senha.
              </p>
              {onAccepted ? (
                <button
                  type="button"
                  onClick={onAccepted}
                  className="mt-2 inline-flex items-center justify-center h-10 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  Ir para o login
                </button>
              ) : (
                <a
                  href={loginPath}
                  className="mt-2 inline-flex items-center justify-center h-10 px-6 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  Ir para o login
                </a>
              )}
            </div>
          )}

          {/* ── Form ── */}
          {(state === "form" || state === "submitting") && inviteInfo && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Read-only email from invitation */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Email</label>
                <input
                  type="email"
                  value={inviteInfo.email}
                  disabled
                  className={INPUT_CLS}
                />
                {inviteInfo.role && (
                  <p className="text-xs text-muted-foreground">
                    Cargo: <span className="font-medium capitalize">{inviteInfo.role}</span>
                    {inviteInfo.org_name && <> em {inviteInfo.org_name}</>}
                  </p>
                )}
              </div>

              {/* Nome */}
              <div className="space-y-2">
                <label htmlFor="invite-nome" className="text-sm font-medium text-foreground">
                  Nome completo
                </label>
                <input
                  id="invite-nome"
                  type="text"
                  placeholder="Seu nome"
                  value={nome}
                  onChange={(e) => {
                    setNome(e.target.value);
                    setNomeError("");
                  }}
                  disabled={state === "submitting"}
                  className={INPUT_CLS}
                />
                {nomeError && <p className="text-xs text-destructive">{nomeError}</p>}
              </div>

              {/* Password */}
              <div className="space-y-2">
                <label htmlFor="invite-password" className="text-sm font-medium text-foreground">
                  Senha
                </label>
                <input
                  id="invite-password"
                  type="password"
                  placeholder="******"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setPasswordError("");
                  }}
                  disabled={state === "submitting"}
                  className={INPUT_CLS}
                />
                {passwordError && (
                  <p className="text-xs text-destructive">{passwordError}</p>
                )}
              </div>

              {/* Confirm password */}
              <div className="space-y-2">
                <label
                  htmlFor="invite-confirm-password"
                  className="text-sm font-medium text-foreground"
                >
                  Confirmar senha
                </label>
                <input
                  id="invite-confirm-password"
                  type="password"
                  placeholder="******"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value);
                    setConfirmError("");
                  }}
                  disabled={state === "submitting"}
                  className={INPUT_CLS}
                />
                {confirmError && (
                  <p className="text-xs text-destructive">{confirmError}</p>
                )}
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={state === "submitting"}
                className="inline-flex items-center justify-center gap-2 w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                {state === "submitting" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Criando conta...
                  </>
                ) : (
                  "Aceitar Convite"
                )}
              </button>
            </form>
          )}
        </div>

        {/* Footer */}
        {(state === "form" || state === "submitting") && (
          <div className="flex justify-center p-6 pt-0">
            <p className="text-sm text-muted-foreground">
              Ja tem uma conta?{" "}
              <a href={loginPath} className="text-primary hover:underline font-medium">
                Fazer login
              </a>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
