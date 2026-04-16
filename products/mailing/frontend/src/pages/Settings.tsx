export default function Settings() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Configuracoes</h1>
        <p className="text-sm text-muted-foreground">
          Configure seu dominio de envio, remetente padrao e preferencias do sistema de mailing.
        </p>
      </div>

      {/* Domain Verification */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Verificacao de Dominio</h2>
        <p className="text-sm text-muted-foreground">
          Verifique seu dominio para melhorar a entregabilidade e autenticar seus e-mails com SPF, DKIM e DMARC.
        </p>

        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Dominio</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">SPF</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">DKIM</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">DMARC</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhum dominio verificado. Adicione um dominio para comecar.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <button
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          disabled
        >
          Adicionar Dominio
        </button>
      </div>

      {/* Sender Configuration */}
      <div className="rounded-lg border border-border bg-card p-6 space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Remetente Padrao</h2>
        <p className="text-sm text-muted-foreground">
          Configure o nome e e-mail de remetente padrao para suas campanhas.
        </p>

        <div className="space-y-4 max-w-lg">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Nome do Remetente</label>
            <input
              type="text"
              placeholder="Ex: Equipe NoctusAI"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">E-mail do Remetente</label>
            <input
              type="email"
              placeholder="Ex: contato@seudominio.com"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">E-mail de Resposta (Reply-To)</label>
            <input
              type="email"
              placeholder="Ex: suporte@seudominio.com"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled
            />
          </div>
          <button
            className="inline-flex items-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            disabled
          >
            Salvar Configuracoes
          </button>
        </div>
      </div>
    </div>
  );
}
