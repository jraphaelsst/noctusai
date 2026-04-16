import { Link } from "react-router-dom";
import { useCampaigns, Campaign } from "@/hooks/useCampaigns";
import { Loader2, AlertCircle, Megaphone, Plus } from "lucide-react";

const STATUS_BADGE: Record<Campaign["status"], { label: string; cls: string }> = {
  rascunho: { label: "Rascunho", cls: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300" },
  agendada: { label: "Agendada", cls: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300" },
  enviando: { label: "Enviando", cls: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300" },
  enviada: { label: "Enviada", cls: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300" },
  pausada: { label: "Pausada", cls: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300" },
  cancelada: { label: "Cancelada", cls: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300" },
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export default function Campaigns() {
  const { data, isLoading, isError } = useCampaigns();
  const campaigns: Campaign[] = data?.data ?? [];

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando campanhas...</p>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <AlertCircle className="h-8 w-8 text-destructive" />
        <p className="text-sm text-muted-foreground">Erro ao carregar campanhas. Tente novamente.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Campanhas</h1>
          <p className="text-sm text-muted-foreground">
            Crie, agende e acompanhe suas campanhas de e-mail marketing.
          </p>
        </div>
        <Link
          to="/campaigns/new"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Nova Campanha
        </Link>
      </div>

      {/* Campaign List */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Enviados</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Destinatarios</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Data</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {campaigns.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center">
                  <Megaphone className="mx-auto h-8 w-8 text-muted-foreground/50" />
                  <p className="mt-2 text-sm text-muted-foreground">Nenhuma campanha criada.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Crie sua primeira campanha para comecar a enviar e-mails.
                  </p>
                </td>
              </tr>
            ) : (
              campaigns.map((c) => {
                const badge = STATUS_BADGE[c.status];
                return (
                  <tr key={c.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link to={`/campaigns/${c.id}`} className="font-medium text-foreground hover:text-primary transition-colors">
                        {c.nome}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                      {c.total_sent.toLocaleString("pt-BR")}
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell text-muted-foreground">
                      {c.total_recipients.toLocaleString("pt-BR")}
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground">
                      {fmtDate(c.created_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
