export default function Unsubscribe() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="space-y-2">
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
              className="inline-flex w-full items-center justify-center rounded-md bg-destructive px-6 py-2.5 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors"
              disabled
            >
              Confirmar Descadastro
            </button>
            <button
              className="inline-flex w-full items-center justify-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
              disabled
            >
              Cancelar — quero continuar recebendo
            </button>
          </div>
        </div>

        <p className="text-xs text-muted-foreground">
          Se voce nao solicitou este descadastro, pode ignorar esta pagina.
        </p>
      </div>
    </div>
  );
}
