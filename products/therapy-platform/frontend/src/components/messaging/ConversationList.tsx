import { useState, useMemo } from 'react';
import { Search, Plus, BellOff, HeadphonesIcon } from 'lucide-react';
import { Input } from '@noctusai/seed/components/ui/input';
import { Button } from '@noctusai/seed/components/ui/button';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { ScrollArea } from '@noctusai/seed/components/ui/scroll-area';
import { Tabs, TabsList, TabsTrigger } from '@noctusai/seed/components/ui/tabs';
import { cn } from '@/lib/utils';
import { NewConversation } from './NewConversation';
import type { Conversation, ConversationFilter } from '@/types/messaging';

interface ConversationListProps {
  conversations: Conversation[];
  selectedId?: string;
  onSelect: (id: string) => void;
  isLoading?: boolean;
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return '';
  const now = Date.now();
  const d = new Date(dateStr).getTime();
  const diffMs = now - d;
  const diffMin = Math.floor(diffMs / 60000);
  const diffH = Math.floor(diffMs / 3600000);
  const diffD = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'agora';
  if (diffMin < 60) return `${diffMin}min`;
  if (diffH < 24) return `${diffH}h`;
  if (diffD === 1) return 'ontem';
  if (diffD < 7) return `${diffD}d`;
  return new Date(dateStr).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
}

function getInitials(name: string): string {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

const FILTER_TABS: { value: ConversationFilter; label: string }[] = [
  { value: 'todas', label: 'Todas' },
  { value: 'nao_lidas', label: 'Nao lidas' },
  { value: 'pacientes', label: 'Pacientes' },
  { value: 'terapeutas', label: 'Terapeutas' },
  { value: 'clinicas', label: 'Clinicas' },
  { value: 'suporte', label: 'Suporte' },
];

export function ConversationList({ conversations, selectedId, onSelect, isLoading }: ConversationListProps) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ConversationFilter>('todas');
  const [newConvOpen, setNewConvOpen] = useState(false);

  const filtered = useMemo(() => {
    let items = conversations;

    // Apply text search
    if (search.trim()) {
      const q = search.toLowerCase();
      items = items.filter(c =>
        c.other_participant_name.toLowerCase().includes(q)
      );
    }

    // Apply tab filter
    if (filter === 'nao_lidas') {
      items = items.filter(c => c.unread_count > 0);
    } else if (filter === 'pacientes') {
      items = items.filter(c => c.other_participant_type === 'user' && !c.is_support);
    } else if (filter === 'terapeutas') {
      items = items.filter(c => c.other_participant_type === 'user' && !c.is_support);
    } else if (filter === 'clinicas') {
      items = items.filter(c => c.other_participant_type === 'clinic');
    } else if (filter === 'suporte') {
      items = items.filter(c => c.is_support);
    }

    // Sort: support always first, then by last_message_at DESC
    return items.sort((a, b) => {
      if (a.is_support && !b.is_support) return -1;
      if (!a.is_support && b.is_support) return 1;
      const aTime = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
      const bTime = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
      return bTime - aTime;
    });
  }, [conversations, search, filter]);

  return (
    <div className="flex flex-col h-full border-r bg-card">
      {/* Header */}
      <div className="p-3 sm:p-4 space-y-3 border-b">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Mensagens</h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setNewConvOpen(true)}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar conversas..."
            className="pl-9 h-9"
          />
        </div>

        <Tabs value={filter} onValueChange={(v) => setFilter(v as ConversationFilter)}>
          <TabsList className="w-full h-auto flex-wrap">
            {FILTER_TABS.map(tab => (
              <TabsTrigger key={tab.value} value={tab.value} className="text-xs px-2 py-1">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* Conversation items */}
      <ScrollArea className="flex-1">
        {isLoading ? (
          <div className="space-y-2 p-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 p-3 animate-pulse">
                <div className="h-10 w-10 rounded-full bg-muted" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-24 bg-muted rounded" />
                  <div className="h-2.5 w-40 bg-muted rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6 text-center">
            <p className="text-sm text-muted-foreground">Nenhuma conversa encontrada</p>
            <Button
              variant="link"
              size="sm"
              className="mt-2"
              onClick={() => setNewConvOpen(true)}
            >
              Iniciar nova conversa
            </Button>
          </div>
        ) : (
          <div className="py-1">
            {filtered.map((conv) => (
              <button
                key={conv.id}
                onClick={() => onSelect(conv.id)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 sm:px-4 py-3 text-left transition-colors hover:bg-accent',
                  selectedId === conv.id && 'bg-accent',
                  conv.is_support && 'border-l-2 border-l-primary'
                )}
              >
                {/* Avatar */}
                {conv.is_support ? (
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <HeadphonesIcon className="h-5 w-5 text-primary" />
                  </div>
                ) : (
                  <Avatar className="h-10 w-10 shrink-0">
                    <AvatarFallback className="text-xs bg-muted">
                      {getInitials(conv.other_participant_name)}
                    </AvatarFallback>
                  </Avatar>
                )}

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn(
                      'text-sm truncate',
                      conv.unread_count > 0 ? 'font-semibold' : 'font-medium'
                    )}>
                      {conv.other_participant_name}
                    </span>
                    <span className="text-[10px] text-muted-foreground shrink-0">
                      {formatRelativeTime(conv.last_message_at)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    <p className={cn(
                      'text-xs truncate',
                      conv.unread_count > 0 ? 'text-foreground' : 'text-muted-foreground'
                    )}>
                      {conv.last_message_preview || 'Nenhuma mensagem'}
                    </p>
                    <div className="flex items-center gap-1 shrink-0">
                      {conv.is_muted && (
                        <BellOff className="h-3 w-3 text-muted-foreground" />
                      )}
                      {conv.unread_count > 0 && (
                        <Badge className="h-5 min-w-[20px] px-1.5 text-[10px] bg-primary text-primary-foreground">
                          {conv.unread_count > 99 ? '99+' : conv.unread_count}
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}
      </ScrollArea>

      <NewConversation
        open={newConvOpen}
        onOpenChange={setNewConvOpen}
        onConversationCreated={onSelect}
      />
    </div>
  );
}
