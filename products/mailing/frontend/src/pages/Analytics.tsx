export default function Analytics() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe as metricas de desempenho das suas campanhas e automacoes de e-mail.
        </p>
      </div>

      {/* Overview Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Total Enviados</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">Ultimos 30 dias</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Taxa de Entrega</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
          <p className="text-xs text-muted-foreground">Entregues / enviados</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Taxa de Abertura</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
          <p className="text-xs text-muted-foreground">Media geral</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Taxa de Clique</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
          <p className="text-xs text-muted-foreground">Click-through rate</p>
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-lg border border-border bg-card p-5 space-y-4">
          <h2 className="text-lg font-semibold text-foreground">Envios por Dia</h2>
          <div className="h-64 flex items-center justify-center rounded-md bg-muted/30 border border-dashed border-border">
            <p className="text-sm text-muted-foreground">Grafico de envios diarios (placeholder)</p>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-5 space-y-4">
          <h2 className="text-lg font-semibold text-foreground">Aberturas vs Cliques</h2>
          <div className="h-64 flex items-center justify-center rounded-md bg-muted/30 border border-dashed border-border">
            <p className="text-sm text-muted-foreground">Grafico comparativo (placeholder)</p>
          </div>
        </div>
      </div>

      {/* Additional Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Bounces</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">E-mails rejeitados</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Descadastros</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">Unsubscribes este mes</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Spam Reports</p>
          <p className="text-3xl font-bold text-foreground">--</p>
          <p className="text-xs text-muted-foreground">Marcados como spam</p>
        </div>
      </div>
    </div>
  );
}
