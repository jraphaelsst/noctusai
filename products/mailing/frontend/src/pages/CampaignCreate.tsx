export default function CampaignCreate() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Nova Campanha</h1>
        <p className="text-sm text-muted-foreground">
          Configure os detalhes da campanha, escolha o template e a lista de destinatarios.
        </p>
      </div>

      {/* Form */}
      <div className="space-y-5 max-w-2xl">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Nome da Campanha</label>
          <input
            type="text"
            placeholder="Ex: Newsletter Abril 2026"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Template</label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          >
            <option value="">Selecione um template</option>
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            Escolha um template previamente criado para usar nesta campanha.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Lista de Destinatarios</label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          >
            <option value="">Selecione uma lista</option>
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            A campanha sera enviada para todos os contatos ativos da lista selecionada.
          </p>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Agendamento</label>
          <input
            type="datetime-local"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Deixe em branco para enviar imediatamente ou escolha uma data/hora.
          </p>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            className="inline-flex items-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            disabled
          >
            Criar Campanha
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
