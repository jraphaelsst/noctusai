import { useMemo } from 'react';
import { Card } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { useAtividades } from '@/hooks/useAtividades';
import { usePropostas } from '@/hooks/usePropostas';
import { TIPOS_ATIVIDADE } from '@/lib/etapasConfig';
import { formatDate } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';
import { Phone, Mail, Users, MessageSquare, MapPin, FileText, Handshake, MoreHorizontal, DollarSign, Clock } from 'lucide-react';

const ATIVIDADE_ICONS: Record<string, React.ElementType> = {
  ligacao: Phone,
  email: Mail,
  reuniao: Users,
  whatsapp: MessageSquare,
  visita: MapPin,
  proposta: FileText,
  negociacao: Handshake,
  outro: MoreHorizontal,
};

const ATIVIDADE_COLORS: Record<string, string> = {
  ligacao: 'bg-blue-100 text-blue-700',
  email: 'bg-purple-100 text-purple-700',
  reuniao: 'bg-green-100 text-green-700',
  whatsapp: 'bg-emerald-100 text-emerald-700',
  visita: 'bg-orange-100 text-orange-700',
  proposta: 'bg-indigo-100 text-indigo-700',
  negociacao: 'bg-yellow-100 text-yellow-700',
  outro: 'bg-gray-100 text-gray-700',
};

interface TimelineEvent {
  id: string;
  type: 'atividade' | 'proposta';
  date: string;
  title: string;
  description?: string;
  icon: React.ElementType;
  iconColor: string;
  badge?: string;
  user?: string;
}

interface ClienteHistoricoProps {
  clienteId: string;
}

export function ClienteHistorico({ clienteId }: ClienteHistoricoProps) {
  const { data: atividades } = useAtividades(clienteId);
  const { data: propostasResult } = usePropostas({ cliente_id: clienteId });

  const events = useMemo<TimelineEvent[]>(() => {
    const propostas = propostasResult?.data || [];
    const items: TimelineEvent[] = [];

    // Map atividades to events
    if (atividades) {
      for (const a of atividades) {
        const tipoConfig = TIPOS_ATIVIDADE.find((t) => t.value === a.tipo);
        items.push({
          id: `atividade-${a.id}`,
          type: 'atividade',
          date: a.data_execucao || a.created_at,
          title: tipoConfig?.label || a.tipo,
          description: a.descricao,
          icon: ATIVIDADE_ICONS[a.tipo] || MoreHorizontal,
          iconColor: ATIVIDADE_COLORS[a.tipo] || ATIVIDADE_COLORS.outro,
          badge: 'Atividade',
          user: a.usuario?.nome,
        });
      }
    }

    // Map propostas to events
    for (const p of propostas) {
      items.push({
        id: `proposta-${p.id}`,
        type: 'proposta',
        date: p.created_at,
        title: `Proposta — ${formatCurrency(p.valor_proposta)}`,
        description: p.observacoes || undefined,
        icon: DollarSign,
        iconColor: 'bg-emerald-100 text-emerald-700',
        badge: p.status.charAt(0).toUpperCase() + p.status.slice(1).replace('_', ' '),
        user: undefined,
      });

      // Also add historico entries from proposal if available
      if (p.historico) {
        for (const h of p.historico) {
          items.push({
            id: `proposta-hist-${p.id}-${h.timestamp}`,
            type: 'proposta',
            date: h.timestamp,
            title: h.action,
            description: h.details ? JSON.stringify(h.details) : undefined,
            icon: Clock,
            iconColor: 'bg-slate-100 text-slate-700',
            badge: 'Histórico',
          });
        }
      }
    }

    // Sort newest first
    items.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

    return items;
  }, [atividades, propostasResult]);

  if (events.length === 0) {
    return (
      <Card className="p-8 text-center">
        <Clock className="w-12 h-12 mx-auto text-muted-foreground/50 mb-3" />
        <p className="text-muted-foreground">Nenhum evento registrado</p>
      </Card>
    );
  }

  return (
    <Card className="p-4 sm:p-6">
      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-5 top-0 bottom-0 w-px bg-border" />

        <div className="space-y-6">
          {events.map((event) => {
            const Icon = event.icon;
            return (
              <div key={event.id} className="relative flex gap-4 pl-2">
                <div className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full ${event.iconColor} flex-shrink-0`}>
                  <Icon className="w-4 h-4" />
                </div>

                <div className="flex-1 min-w-0 pt-0.5">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="font-medium text-sm">{event.title}</span>
                    {event.badge && (
                      <Badge variant="outline" className="text-xs">
                        {event.badge}
                      </Badge>
                    )}
                    {event.user && (
                      <span className="text-xs text-muted-foreground">
                        por {event.user}
                      </span>
                    )}
                  </div>
                  {event.description && (
                    <p className="text-sm text-muted-foreground">{event.description}</p>
                  )}
                  <p className="text-xs text-muted-foreground mt-1">
                    {formatDate(event.date, true)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
