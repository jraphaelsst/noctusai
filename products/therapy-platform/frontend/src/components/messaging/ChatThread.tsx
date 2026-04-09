import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { ArrowLeft, MessageSquare } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { MessageBubble } from './MessageBubble';
import { MessageInput } from './MessageInput';
import { ConversationActions } from './ConversationActions';
import {
  useMessages,
  useSendMessage,
  useMarkAsRead,
  useDeleteMessage,
  useReportMessage,
} from '@/hooks/useMessages';
import {
  useArchiveConversation,
  useMuteConversation,
} from '@/hooks/useConversations';
import { useBlockUser } from '@/hooks/useMessages';
import type { Conversation, Message } from '@/types/messaging';

interface ChatThreadProps {
  conversation: Conversation | null;
  onBack?: () => void;
  showBackButton?: boolean;
}

function getInitials(name: string): string {
  return name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
}

function groupMessagesByDate(messages: Message[]): { date: string; messages: Message[] }[] {
  const groups: Record<string, Message[]> = {};
  for (const msg of messages) {
    const date = new Date(msg.created_at).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: 'long',
      year: 'numeric',
    });
    if (!groups[date]) groups[date] = [];
    groups[date].push(msg);
  }
  return Object.entries(groups).map(([date, messages]) => ({ date, messages }));
}

export function ChatThread({ conversation, onBack, showBackButton }: ChatThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [page] = useState(1);
  const [reportDialogOpen, setReportDialogOpen] = useState(false);
  const [reportMessageId, setReportMessageId] = useState<string | null>(null);
  const [reportReason, setReportReason] = useState('');

  const { data: messagesData, isLoading } = useMessages(conversation?.id, page);
  const sendMessage = useSendMessage();
  const markAsRead = useMarkAsRead();
  const deleteMessage = useDeleteMessage();
  const reportMessage = useReportMessage();
  const archiveConversation = useArchiveConversation();
  const muteConversation = useMuteConversation();
  const blockUser = useBlockUser();

  const messages = useMemo(() => {
    const items = messagesData?.data ?? [];
    // API returns newest first; reverse for chronological display
    return [...items].reverse();
  }, [messagesData]);

  // Mark as read when conversation is opened
  useEffect(() => {
    if (conversation?.id && conversation.unread_count > 0) {
      markAsRead.mutate(conversation.id);
    }
  }, [conversation?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const handleSend = useCallback((data: {
    message_type: 'text' | 'image' | 'audio';
    content?: string;
    file_url?: string;
    file_type?: string;
    file_size?: number;
  }) => {
    if (!conversation) return;
    sendMessage.mutate({
      conversationId: conversation.id,
      ...data,
    });
  }, [conversation, sendMessage]);

  const handleDelete = useCallback((messageId: string) => {
    deleteMessage.mutate(messageId);
  }, [deleteMessage]);

  const handleOpenReport = useCallback((messageId: string) => {
    setReportMessageId(messageId);
    setReportReason('');
    setReportDialogOpen(true);
  }, []);

  const handleSubmitReport = useCallback(() => {
    if (!reportMessageId || !reportReason.trim()) return;
    reportMessage.mutate({ messageId: reportMessageId, reason: reportReason.trim() });
    setReportDialogOpen(false);
    setReportMessageId(null);
    setReportReason('');
  }, [reportMessageId, reportReason, reportMessage]);

  const handleConversationReport = useCallback((reason: string) => {
    if (!conversation) return;
    reportMessage.mutate({ messageId: conversation.id, reason });
  }, [conversation, reportMessage]);

  // Empty state
  if (!conversation) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-background">
        <MessageSquare className="h-12 w-12 text-muted-foreground/30 mb-4" />
        <p className="text-lg font-medium text-muted-foreground">
          Selecione uma conversa
        </p>
        <p className="text-sm text-muted-foreground mt-1">
          ou inicie uma nova para comecar
        </p>
      </div>
    );
  }

  const dateGroups = groupMessagesByDate(messages);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-background">
      {/* Header */}
      <div className="h-14 border-b flex items-center gap-3 px-3 sm:px-4 bg-card shrink-0">
        {showBackButton && (
          <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
        )}

        <Avatar className="h-8 w-8 shrink-0">
          <AvatarFallback className="text-xs bg-muted">
            {getInitials(conversation.other_participant_name)}
          </AvatarFallback>
        </Avatar>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">
            {conversation.other_participant_name}
          </p>
        </div>

        <ConversationActions
          conversation={conversation}
          onArchive={() => archiveConversation.mutate(conversation.id)}
          onMute={(mute) => muteConversation.mutate({ conversationId: conversation.id, mute })}
          onBlock={() => blockUser.mutate(conversation.id)}
          onReport={handleConversationReport}
        />
      </div>

      {/* Messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 sm:px-4 py-3">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className={cn(
                  'flex',
                  i % 2 === 0 ? 'justify-start' : 'justify-end'
                )}
              >
                <div className="h-10 rounded-2xl bg-muted animate-pulse" style={{ width: `${120 + Math.random() * 100}px` }} />
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-muted-foreground">Nenhuma mensagem ainda. Diga ola!</p>
          </div>
        ) : (
          dateGroups.map((group) => (
            <div key={group.date}>
              <div className="flex justify-center my-4">
                <span className="text-[10px] text-muted-foreground bg-muted px-3 py-0.5 rounded-full">
                  {group.date}
                </span>
              </div>
              {group.messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onDelete={handleDelete}
                  onReport={handleOpenReport}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* Message input */}
      <MessageInput
        onSend={handleSend}
        disabled={sendMessage.isPending}
      />

      {/* Report dialog for individual messages */}
      <Dialog open={reportDialogOpen} onOpenChange={setReportDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Denunciar mensagem</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground">
              Descreva o motivo da denuncia
            </label>
            <Input
              value={reportReason}
              onChange={(e) => setReportReason(e.target.value)}
              placeholder="Ex: Conteudo inapropriado, spam..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReportDialogOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSubmitReport} disabled={!reportReason.trim()}>
              Enviar denuncia
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
