export default function Automations() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Automacoes</h1>
          <p className="text-sm text-muted-foreground">
            Configure fluxos automaticos de e-mail baseados em gatilhos e acoes.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
          Nova Automacao
        </button>
      </div>

      {/* Automations List */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Gatilho</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Inscritos</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Criada em</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                <p className="text-sm">Nenhuma automacao configurada.</p>
                <p className="text-xs mt-1">Crie automacoes para enviar e-mails automaticamente com base em gatilhos como cadastro, tag, ou data.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
