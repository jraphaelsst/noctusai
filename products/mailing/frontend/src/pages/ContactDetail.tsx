import { useParams } from "react-router-dom";

export default function ContactDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Detalhe do Contato</h1>
        <p className="text-sm text-muted-foreground">
          Visualize informacoes completas e historico de envios do contato #{id}.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Contact Info */}
        <div className="lg:col-span-1 space-y-4">
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Informacoes</h2>
            <div className="space-y-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Nome</p>
                <p className="text-sm text-foreground">--</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">E-mail</p>
                <p className="text-sm text-foreground">--</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Empresa</p>
                <p className="text-sm text-foreground">--</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Tags</p>
                <p className="text-sm text-foreground">--</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Status</p>
                <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                  --
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Send History */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-lg border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground">Historico de Envios</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Campanha</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Data</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Aberto</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Clicou</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      Nenhum envio registrado para este contato.
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
