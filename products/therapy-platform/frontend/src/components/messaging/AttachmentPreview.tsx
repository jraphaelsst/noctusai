import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogTrigger,
} from '@noctusai/seed/components/ui/dialog';
import type { Message } from '@/types/messaging';

interface AttachmentPreviewProps {
  message: Message;
}

export function AttachmentPreview({ message }: AttachmentPreviewProps) {
  const [open, setOpen] = useState(false);

  if (message.message_type === 'image' && message.file_url) {
    return (
      <div className="space-y-1">
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <img
              src={message.file_url}
              alt="Imagem enviada"
              className="max-w-[300px] max-h-[200px] rounded-lg cursor-pointer object-cover hover:opacity-90 transition-opacity"
            />
          </DialogTrigger>
          <DialogContent className="max-w-[90vw] max-h-[90vh] p-2">
            <img
              src={message.file_url}
              alt="Imagem enviada"
              className="w-full h-full object-contain"
            />
          </DialogContent>
        </Dialog>
        {message.ai_processed_content && (
          <p className="text-xs italic text-muted-foreground">
            Descricao: {message.ai_processed_content}
          </p>
        )}
      </div>
    );
  }

  if (message.message_type === 'audio' && message.file_url) {
    return (
      <div className="space-y-1">
        <audio controls className="max-w-[280px]">
          <source src={message.file_url} type={message.file_type || 'audio/mpeg'} />
          Seu navegador nao suporta audio.
        </audio>
        {message.ai_processed_content && (
          <p className="text-xs italic text-muted-foreground">
            Transcricao: {message.ai_processed_content}
          </p>
        )}
      </div>
    );
  }

  return null;
}
