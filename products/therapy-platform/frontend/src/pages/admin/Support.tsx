import { useState } from 'react';
import { HeadphonesIcon } from 'lucide-react';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { ConversationList } from '@/components/messaging/ConversationList';
import { ChatThread } from '@/components/messaging/ChatThread';
import { useAdminSupportConversations } from '@/hooks/useAdmin';
import { cn } from '@/lib/utils';
import type { Conversation } from '@/types/messaging';

export default function AdminSupport() {
  const [selectedId, setSelectedId] = useState<string | undefined>();
  const { data, isLoading } = useAdminSupportConversations();

  const conversations = ((data?.data ?? []) as Conversation[]).map(c => ({
    ...c,
    is_support: true,
  }));

  const selected = conversations.find(c => c.id === selectedId) ?? null;
  const unreadCount = conversations.reduce((sum, c) => sum + c.unread_count, 0);

  return (
    <div className="container mx-auto p-6 space-y-4">
      <div className="flex items-center gap-3">
        <HeadphonesIcon className="h-6 w-6" />
        <h1 className="text-2xl font-bold">Suporte</h1>
        {unreadCount > 0 && (
          <Badge className="bg-primary text-primary-foreground">
            {unreadCount} nao lida{unreadCount > 1 ? 's' : ''}
          </Badge>
        )}
      </div>

      <div className="border rounded-lg h-[calc(100vh-12rem)] flex overflow-hidden">
        {/* Conversation list */}
        <div className={cn(
          'w-full md:w-80 lg:w-96 shrink-0',
          selectedId && 'hidden md:block'
        )}>
          <ConversationList
            conversations={conversations}
            selectedId={selectedId}
            onSelect={setSelectedId}
            isLoading={isLoading}
          />
        </div>

        {/* Chat thread */}
        <div className={cn(
          'flex-1',
          !selectedId && 'hidden md:flex'
        )}>
          <ChatThread
            conversation={selected}
            onBack={() => setSelectedId(undefined)}
            showBackButton={!!selectedId}
          />
        </div>
      </div>
    </div>
  );
}
