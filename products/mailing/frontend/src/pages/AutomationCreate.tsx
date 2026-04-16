export default function AutomationCreate() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Nova Automacao</h1>
        <p className="text-sm text-muted-foreground">
          Defina o gatilho, as etapas e os e-mails que serao enviados automaticamente.
        </p>
      </div>

      {/* Form */}
      <div className="space-y-5 max-w-2xl">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Nome da Automacao</label>
          <input
            type="text"
            placeholder="Ex: Onboarding Novos Contatos"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Tipo de Gatilho</label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          >
            <option value="">Selecione o gatilho</option>
            <option value="contact_created">Contato criado</option>
            <option value="tag_added">Tag adicionada</option>
            <option value="list_joined">Entrou em lista</option>
            <option value="date_field">Data especifica</option>
            <option value="manual">Inscricao manual</option>
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            O gatilho determina quando a automacao sera iniciada para cada contato.
          </p>
        </div>

        {/* Steps Section */}
        <div className="space-y-3">
          <label className="block text-sm font-medium text-foreground">Etapas</label>
          <div className="rounded-lg border border-dashed border-border bg-muted/30 p-6 text-center">
            <p className="text-sm text-muted-foreground">Nenhuma etapa adicionada.</p>
            <p className="text-xs text-muted-foreground mt-1">
              Adicione etapas como "Enviar e-mail", "Aguardar X dias" ou "Adicionar tag".
            </p>
            <button
              className="mt-4 inline-flex items-center gap-2 rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-muted transition-colors"
              disabled
            >
              Adicionar Etapa
            </button>
          </div>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            className="inline-flex items-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            disabled
          >
            Criar Automacao
          </button>
          <button
            className="inline-flex items-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
            disabled
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
