export default function Templates() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Templates</h1>
          <p className="text-sm text-muted-foreground">
            Crie e gerencie templates de e-mail reutilizaveis para suas campanhas.
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors">
          Novo Template
        </button>
      </div>

      {/* Template Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Empty state */}
        <div className="col-span-full rounded-lg border border-dashed border-border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">Nenhum template criado.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Templates permitem padronizar o visual dos seus e-mails e agilizar a criacao de campanhas.
          </p>
        </div>
      </div>

      {/* Example card layout (hidden, shows structure) */}
      <div className="hidden">
        <div className="rounded-lg border border-border bg-card p-5 space-y-3 hover:shadow-md transition-shadow">
          <div className="flex items-start justify-between">
            <h3 className="font-semibold text-foreground">Nome do Template</h3>
            <span className="inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
              Categoria
            </span>
          </div>
          <p className="text-sm text-muted-foreground">Assunto: Exemplo de assunto</p>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>Ultima edicao: --</span>
          </div>
        </div>
      </div>
    </div>
  );
}
