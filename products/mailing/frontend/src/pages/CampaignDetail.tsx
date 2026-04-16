import { useParams } from "react-router-dom";

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Detalhe da Campanha</h1>
        <p className="text-sm text-muted-foreground">
          Acompanhe as metricas e o log de envios da campanha #{id}.
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Enviados</p>
          <p className="text-3xl font-bold text-foreground">--</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Entregues</p>
          <p className="text-3xl font-bold text-foreground">--</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Aberturas</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-5 space-y-2">
          <p className="text-sm font-medium text-muted-foreground">Cliques</p>
          <p className="text-3xl font-bold text-foreground">--%</p>
        </div>
      </div>

      {/* Campaign Info */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <h2 className="text-lg font-semibold text-foreground">Informacoes da Campanha</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Template</p>
            <p className="font-medium text-foreground">--</p>
          </div>
          <div>
            <p className="text-muted-foreground">Lista</p>
            <p className="font-medium text-foreground">--</p>
          </div>
          <div>
            <p className="text-muted-foreground">Status</p>
            <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">--</span>
          </div>
          <div>
            <p className="text-muted-foreground">Enviada em</p>
            <p className="font-medium text-foreground">--</p>
          </div>
        </div>
      </div>

      {/* Send Log */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Log de Envios</h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Contato</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Aberto em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Clicou em</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhum envio registrado para esta campanha.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
