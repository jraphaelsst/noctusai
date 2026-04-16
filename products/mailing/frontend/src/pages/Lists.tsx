export default function Lists() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Listas</h1>
          <p className="text-sm text-muted-foreground">
            Organize seus contatos em listas segmentadas para campanhas direcionadas.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
          Nova Lista
        </button>
      </div>

      {/* Lists Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Tipo</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Contatos</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Criada em</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                <p className="text-sm">Nenhuma lista criada.</p>
                <p className="text-xs mt-1">Crie listas para organizar seus contatos e enviar campanhas segmentadas.</p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
