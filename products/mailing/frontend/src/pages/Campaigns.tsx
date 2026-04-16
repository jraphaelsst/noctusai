export default function Campaigns() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Campanhas</h1>
          <p className="text-sm text-muted-foreground">
            Crie, agende e acompanhe suas campanhas de e-mail marketing.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
          Nova Campanha
        </button>
      </div>

      {/* Campaign List */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Enviados</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Aberturas</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Cliques</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Data</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                <p className="text-sm">Nenhuma campanha criada.</p>
                <p className="text-xs mt-1">Crie sua primeira campanha para comecar a enviar e-mails.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Status badge reference (hidden) */}
      <div className="hidden space-x-2">
        <span className="inline-flex rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">Rascunho</span>
        <span className="inline-flex rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">Agendada</span>
        <span className="inline-flex rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">Enviada</span>
        <span className="inline-flex rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">Cancelada</span>
      </div>
    </div>
  );
}
