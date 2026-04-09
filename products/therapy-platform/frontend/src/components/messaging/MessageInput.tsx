import { useState, useRef, useCallback } from 'react';
import { Send, ImageIcon, Mic, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useUploadAttachment } from '@/hooks/useMessages';

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

interface MessageInputProps {
  onSend: (data: { message_type: 'text' | 'image' | 'audio'; content?: string; file_url?: string; file_type?: string; file_size?: number }) => void;
  disabled?: boolean;
}

export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const audioInputRef = useRef<HTMLInputElement>(null);
  const uploadMutation = useUploadAttachment();

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const maxHeight = 4 * 24; // 4 lines approx
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  }, []);

  const handleSendText = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend({ message_type: 'text', content: trimmed });
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendText();
    }
  };

  const handleFileUpload = async (file: File, type: 'image' | 'audio') => {
    if (file.size > MAX_FILE_SIZE) {
      toast.error('Arquivo muito grande', { description: 'Tamanho maximo: 50MB' });
      return;
    }

    try {
      const result = await uploadMutation.mutateAsync(file);
      const fileData = result.data ?? result;
      onSend({
        message_type: type,
        file_url: fileData.url,
        file_type: file.type,
        file_size: file.size,
      });
    } catch {
      // Error handled by mutation
    }
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileUpload(file, 'image');
    e.target.value = '';
  };

  const handleAudioSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileUpload(file, 'audio');
    e.target.value = '';
  };

  const isUploading = uploadMutation.isPending;

  return (
    <div className="border-t bg-card p-3">
      <div className="flex items-end gap-2">
        {/* Attachment buttons */}
        <div className="flex gap-1 pb-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={disabled || isUploading}
            onClick={() => imageInputRef.current?.click()}
          >
            <ImageIcon className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={disabled || isUploading}
            onClick={() => audioInputRef.current?.click()}
          >
            <Mic className="h-4 w-4" />
          </Button>
        </div>

        {/* Hidden file inputs */}
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleImageSelect}
        />
        <input
          ref={audioInputRef}
          type="file"
          accept="audio/*"
          className="hidden"
          onChange={handleAudioSelect}
        />

        {/* Text area */}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            adjustHeight();
          }}
          onKeyDown={handleKeyDown}
          placeholder="Digite uma mensagem..."
          rows={1}
          disabled={disabled || isUploading}
          className={cn(
            'flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring',
            'disabled:cursor-not-allowed disabled:opacity-50',
            'min-h-[36px] max-h-[96px]'
          )}
        />

        {/* Send button */}
        <Button
          type="button"
          size="icon"
          className="h-9 w-9 shrink-0"
          disabled={disabled || isUploading || !text.trim()}
          onClick={handleSendText}
        >
          {isUploading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
