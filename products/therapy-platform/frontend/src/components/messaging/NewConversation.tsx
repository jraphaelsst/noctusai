import { useState, useCallback } from 'react';
import { Search, HeadphonesIcon, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@noctusai/seed/components/ui/dialog';
import { Input } from '@noctusai/seed/components/ui/input';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Avatar, AvatarFallback } from '@noctusai/seed/components/ui/avatar';
import { ScrollArea } from '@noctusai/seed/components/ui/scroll-area';
import { useQuery } from '@tanstack/react-query';
import { api, useAuthStore } from '@noctusai/seed/infra';
import { useStartConversation } from '@/hooks/useConversations';

interface SearchUser {
  id: string;
  name: string;
  email: string;
  role: string;
  avatar_url?: string;
}

const ROLE_LABELS: Record<string, string> = {
  paciente: 'Paciente',
  terapeuta: 'Terapeuta',
  clinica: 'Clinica',
  admin: 'Admin',
};

interface NewConversationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConversationCreated: (conversationId: string) => void;
}

export function NewConversation({ open, onOpenChange, onConversationCreated }: NewConversationProps) {
  const [search, setSearch] = useState('');
  const [messageText, setMessageText] = useState('');
  const [selectedUser, setSelectedUser] = useState<SearchUser | null>(null);
  const { user } = useAuthStore();
  const startConversation = useStartConversation();

  const { data: searchResults, isLoading } = useQuery<SearchUser[]>({
    queryKey: ['user-search', search],
    queryFn: async () => {
      if (!search.trim() || search.length < 2) return [];
      const res = await api.get(`/api/users/search?q=${encodeURIComponent(search)}`);
      return res.data ?? res;
    },
    placeholderData: (prev) => prev,
    enabled: !!user && search.length >= 2,
    staleTime: 30 * 1000,
  });

  const getInitials = (name: string) => {
    return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
  };

  const handleSelectUser = (u: SearchUser) => {
    setSelectedUser(u);
    setMessageText('');
  };

  const handleStartSupport = useCallback(async () => {
    try {
      const result = await startConversation.mutateAsync({
        is_support: true,
        initial_message: 'Ola, preciso de ajuda.',
      });
      const conv = result.data ?? result;
      onConversationCreated(conv.id);
      onOpenChange(false);
      resetState();
    } catch {
      // Error handled by mutation
    }
  }, [startConversation, onConversationCreated, onOpenChange]);

  const handleSendFirst = useCallback(async () => {
    if (!selectedUser || !messageText.trim()) return;
    try {
      const result = await startConversation.mutateAsync({
        participant_user_id: selectedUser.id,
        initial_message: messageText.trim(),
      });
      const conv = result.data ?? result;
      onConversationCreated(conv.id);
      onOpenChange(false);
      resetState();
    } catch {
      // Error handled by mutation
    }
  }, [selectedUser, messageText, startConversation, onConversationCreated, onOpenChange]);

  const resetState = () => {
    setSearch('');
    setSelectedUser(null);
    setMessageText('');
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) resetState(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Nova conversa</DialogTitle>
        </DialogHeader>

        {!selectedUser ? (
          <div className="space-y-3">
            {/* Support option */}
            <button
              onClick={handleStartSupport}
              disabled={startConversation.isPending}
              className="w-full flex items-center gap-3 p-3 rounded-lg border hover:bg-accent transition-colors text-left"
            >
              <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <HeadphonesIcon className="h-5 w-5 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">Suporte da Plataforma</p>
                <p className="text-xs text-muted-foreground">Fale com nossa equipe</p>
              </div>
            </button>

            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome ou email..."
                className="pl-9"
              />
            </div>

            <ScrollArea className="h-[300px]">
              {isLoading && (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              )}
              {searchResults && searchResults.length === 0 && search.length >= 2 && (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Nenhum usuario encontrado
                </p>
              )}
              {searchResults?.map((u) => (
                <button
                  key={u.id}
                  onClick={() => handleSelectUser(u)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-accent transition-colors text-left"
                >
                  <Avatar className="h-9 w-9 shrink-0">
                    <AvatarFallback className="text-xs bg-muted">
                      {getInitials(u.name)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{u.name}</p>
                    <p className="text-xs text-muted-foreground truncate">{u.email}</p>
                  </div>
                  <Badge variant="secondary" className="text-[10px] shrink-0">
                    {ROLE_LABELS[u.role] || u.role}
                  </Badge>
                </button>
              ))}
            </ScrollArea>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 rounded-lg bg-muted">
              <Avatar className="h-9 w-9 shrink-0">
                <AvatarFallback className="text-xs">
                  {getInitials(selectedUser.name)}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{selectedUser.name}</p>
                <Badge variant="secondary" className="text-[10px]">
                  {ROLE_LABELS[selectedUser.role] || selectedUser.role}
                </Badge>
              </div>
              <button
                onClick={() => setSelectedUser(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Trocar
              </button>
            </div>

            <textarea
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              placeholder="Escreva sua primeira mensagem..."
              rows={3}
              className="w-full resize-none rounded-lg border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setSelectedUser(null)}
                className="px-4 py-2 text-sm rounded-lg hover:bg-accent transition-colors"
              >
                Voltar
              </button>
              <button
                onClick={handleSendFirst}
                disabled={!messageText.trim() || startConversation.isPending}
                className="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {startConversation.isPending ? 'Enviando...' : 'Enviar'}
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
