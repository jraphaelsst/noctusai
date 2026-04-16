export default function Dashboard() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Visao geral das suas campanhas de e-mail e metricas de engajamento.
        </p>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Total Contatos</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">Contatos ativos na base</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Enviados</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">E-mails enviados este mes</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Taxa de Abertura</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
          <p className="text-xs text-muted-foreground">Media das campanhas recentes</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Taxa de Clique</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
          <p className="text-xs text-muted-foreground">Click-through rate medio</p>
        </div>
      </div>

      {/* Recent Campaigns */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Campanhas Recentes</h2>
        <div className="rounded-lg border border-border bg-card">
          <div className="p-8 text-center text-muted-foreground">
            <p className="text-sm">Nenhuma campanha encontrada.</p>
            <p className="text-xs mt-1">Crie sua primeira campanha para ver os resultados aqui.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
