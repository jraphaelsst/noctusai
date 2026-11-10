import { Link } from "react-router-dom";
import { MessageCircle } from "lucide-react";

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <MessageCircle className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Assistant</h1>
          <p className="text-sm text-muted-foreground">Leitura silenciosa de uma linha de WhatsApp.</p>
        </div>
      </div>
      <div className="rounded-lg border border-border bg-card p-6 space-y-2" data-testid="dashboard-conexao">
        <p className="text-sm text-muted-foreground">
          O Assistant só recebe e registra mensagens de texto de conversas individuais. Para começar, conecte a linha.
        </p>
        <Link to="/conexao" className="text-sm font-medium text-primary underline">
          Ir para a conexão do WhatsApp
        </Link>
      </div>
    </div>
  );
}
