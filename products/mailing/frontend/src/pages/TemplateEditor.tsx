export default function TemplateEditor() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Editor de Template</h1>
        <p className="text-sm text-muted-foreground">
          Crie ou edite o conteudo HTML do seu template de e-mail.
        </p>
      </div>

      {/* Form */}
      <div className="space-y-5 max-w-4xl">
        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Nome do Template</label>
          <input
            type="text"
            placeholder="Ex: Newsletter Mensal"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Assunto</label>
          <input
            type="text"
            placeholder="Ex: Novidades de abril - {{empresa}}"
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Categoria</label>
          <select
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled
          >
            <option value="">Selecione uma categoria</option>
            <option value="newsletter">Newsletter</option>
            <option value="promocional">Promocional</option>
            <option value="transacional">Transacional</option>
            <option value="onboarding">Onboarding</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-foreground">Corpo HTML</label>
          <textarea
            rows={16}
            placeholder="<html>&#10;  <body>&#10;    <h1>Ola {{nome}},</h1>&#10;    <p>Conteudo do e-mail aqui...</p>&#10;  </body>&#10;</html>"
            className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-y"
            disabled
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Use variaveis como {"{{nome}}"}, {"{{empresa}}"}, {"{{email}}"} para personalizacao.
          </p>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            className="inline-flex items-center rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            disabled
          >
            Salvar Template
          </button>
          <button
            className="inline-flex items-center rounded-md border border-input bg-background px-6 py-2.5 text-sm font-medium hover:bg-muted transition-colors"
            disabled
          >
            Pre-visualizar
          </button>
        </div>
      </div>
    </div>
  );
}
