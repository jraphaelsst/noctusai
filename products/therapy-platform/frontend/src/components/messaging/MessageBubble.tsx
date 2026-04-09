import { useState } from 'react';
import { cn } from '@/lib/utils';
import { Trash2, Flag } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { AttachmentPreview } from './AttachmentPreview';
import type { Message } from '@/types/messaging';

interface MessageBubbleProps {
  message: Message;
  onDelete: (messageId: string) => void;
  onReport: (messageId: string) => void;
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message, onDelete, onReport }: MessageBubbleProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  if (message.message_type === 'system') {
    return (
      <div className="flex justify-center my-2">
        <span className="text-xs text-muted-foreground bg-muted px-3 py-1 rounded-full">
          {message.content}
        </span>
      </div>
    );
  }

  const isOwn = message.is_own;
  const isMedia = message.message_type === 'image' || message.message_type === 'audio';

  return (
    <div className={cn('flex mb-2 group', isOwn ? 'justify-end' : 'justify-start')}>
      <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownMenuTrigger asChild>
          <div
            className={cn(
              'max-w-[75%] sm:max-w-[65%] rounded-2xl px-3 py-2 cursor-context-menu relative',
              isOwn
                ? 'bg-primary text-primary-foreground rounded-br-md'
                : 'bg-muted text-foreground rounded-bl-md'
            )}
          >
            {isMedia ? (
              <AttachmentPreview message={message} />
            ) : (
              <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
            )}

            {message.message_type === 'ai' && message.ai_processed_content && !isMedia && (
              <p className={cn(
                'text-xs italic mt-1',
                isOwn ? 'text-primary-foreground/70' : 'text-muted-foreground'
              )}>
                {message.ai_processed_content}
              </p>
            )}

            <p className={cn(
              'text-[10px] mt-0.5 text-right',
              isOwn ? 'text-primary-foreground/60' : 'text-muted-foreground'
            )}>
              {formatTime(message.created_at)}
            </p>
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={isOwn ? 'end' : 'start'}>
          {isOwn && (
            <DropdownMenuItem
              onClick={() => onDelete(message.id)}
              className="text-destructive cursor-pointer"
            >
              <Trash2 className="h-4 w-4 mr-2" />
              Excluir
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            onClick={() => onReport(message.id)}
            className="cursor-pointer"
          >
            <Flag className="h-4 w-4 mr-2" />
            Denunciar
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
