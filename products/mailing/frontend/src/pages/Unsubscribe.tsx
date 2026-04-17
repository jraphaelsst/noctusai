import { useState } from "react";
import { useParams } from "react-router-dom";
import { api } from '@noctusai/seed/infra';
import { Loader2, MailX, CheckCircle, AlertCircle } from "lucide-react";

type State = "idle" | "loading" | "success" | "error";

export default function Unsubscribe() {
  const { token } = useParams<{ token: string }>();
  const [state, setState] = useState<State>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleConfirm() {
    if (!token) return;
    setState("loading");
    try {
      await api.post(`/api/unsubscribe/${token}`);
      setState("success");
    } catch (err: any) {
      setState("error");
      setErrorMsg(err?.message ?? "Token invalido ou expirado.");
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6 text-center">
        {state === "idle" && (
          <>
            <div className="space-y-2">
              <MailX className="mx-auto h-12 w-12 text-muted-foreground" />
              <h1 className="text-2xl font-bold text-foreground">Descadastro</h1>
              <p className="text-sm text-muted-foreground">
                Voce esta se descadastrando da nossa lista de e-mails.
              </p>
            </div>

            <div className="rounded-lg border border-border bg-card p-6 space-y-4">
              <p className="text-sm text-foreground">
                Ao confirmar, voce deixara de receber nossos e-mails de marketing.
                E-mails transacionais importantes ainda poderao ser enviados.
              </p>

              <div className="space-y-3">
                <button
                  onClick={handleConfirm}
                  className="inline-flex w-full items-center justify-center rounded-md bg-destructive px-6 py-2.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
                >
                  Confirmar Descadastro
                </button>
                <a
                  href="/"
                  className="inline-flex w-full items-center justify-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
                >
                  Cancelar — quero continuar recebendo
                </a>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              Se voce nao solicitou este descadastro, pode ignorar esta pagina.
            </p>
          </>
        )}

        {state === "loading" && (
          <div className="space-y-3">
            <Loader2 className="mx-auto h-10 w-10 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Processando descadastro...</p>
          </div>
        )}

        {state === "success" && (
          <div className="space-y-4">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <h1 className="text-2xl font-bold text-foreground">Descadastro Confirmado</h1>
            <p className="text-sm text-muted-foreground">
              Voce foi removido da nossa lista de e-mails de marketing. Caso mude de ideia, entre em contato conosco.
            </p>
          </div>
        )}

        {state === "error" && (
          <div className="space-y-4">
            <AlertCircle className="mx-auto h-12 w-12 text-destructive" />
            <h1 className="text-2xl font-bold text-foreground">Erro no Descadastro</h1>
            <p className="text-sm text-muted-foreground">
              {errorMsg}
            </p>
            <button
              onClick={() => setState("idle")}
              className="inline-flex items-center justify-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
            >
              Tentar Novamente
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
