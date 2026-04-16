export default function Contacts() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Contatos</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie sua base de contatos, segmente por tags e acompanhe o status de cada um.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
          Novo Contato
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Buscar por nome, e-mail ou empresa..."
          className="flex h-10 flex-1 rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          disabled
        />
        <button className="inline-flex items-center rounded-md border border-input bg-background px-4 text-sm font-medium hover:bg-muted transition-colors">
          Filtrar
        </button>
      </div>

      {/* Contacts Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Empresa</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Tags</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                <p className="text-sm">Nenhum contato cadastrado.</p>
                <p className="text-xs mt-1">Importe contatos ou adicione manualmente para comecar.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
