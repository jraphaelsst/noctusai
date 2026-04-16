import { useParams } from "react-router-dom";

export default function AutomationDetail() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Detalhe da Automacao</h1>
          <p className="text-sm text-muted-foreground">
            Visualize as etapas, metricas e inscricoes da automacao #{id}.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="inline-flex items-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
            disabled
          >
            Editar
          </button>
          <button
            className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            disabled
          >
            Ativar
          </button>
        </div>
      </div>

      {/* Automation Info */}
      <div className="rounded-lg border border-border bg-card p-5 space-y-3">
        <h2 className="text-lg font-semibold text-foreground">Informacoes</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Gatilho</p>
            <p className="font-medium text-foreground">--</p>
          </div>
          <div>
            <p className="text-muted-foreground">Status</p>
            <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">--</span>
          </div>
          <div>
            <p className="text-muted-foreground">Total Inscritos</p>
            <p className="font-medium text-foreground">--</p>
          </div>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Etapas</h2>
        <div className="rounded-lg border border-dashed border-border bg-muted/30 p-8 text-center">
          <p className="text-sm text-muted-foreground">Nenhuma etapa configurada nesta automacao.</p>
        </div>
      </div>

      {/* Enrollments */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-foreground">Inscricoes</h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Contato</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Etapa Atual</th>
                <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Inscrito em</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhuma inscricao registrada nesta automacao.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
