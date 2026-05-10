import { useState } from 'react';
import { MoreVertical, Archive, BellOff, Bell, Ban, Flag } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@noctusai/seed/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@noctusai/seed/components/ui/alert-dialog';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@noctusai/seed/components/ui/dialog';
import { Input } from '@noctusai/seed/components/ui/input';
import type { Conversation } from '@/types/messaging';

interface ConversationActionsProps {
  conversation: Conversation;
  onArchive: () => void;
  onMute: (mute: boolean) => void;
  onBlock: () => void;
  onReport: (reason: string) => void;
}

export function ConversationActions({
  conversation,
  onArchive,
  onMute,
  onBlock,
  onReport,
}: ConversationActionsProps) {
  const [blockOpen, setBlockOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState('');

  const handleReport = () => {
    if (!reportReason.trim()) return;
    onReport(reportReason.trim());
    setReportReason('');
    setReportOpen(false);
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onArchive} className="cursor-pointer">
            <Archive className="h-4 w-4 mr-2" />
            Arquivar
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={() => onMute(!conversation.is_muted)}
            className="cursor-pointer"
          >
            {conversation.is_muted ? (
              <>
                <Bell className="h-4 w-4 mr-2" />
                Ativar som
              </>
            ) : (
              <>
                <BellOff className="h-4 w-4 mr-2" />
                Silenciar
              </>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {!conversation.is_support && (
            <DropdownMenuItem
              onClick={() => setBlockOpen(true)}
              className="text-destructive cursor-pointer"
            >
              <Ban className="h-4 w-4 mr-2" />
              Bloquear usuario
            </DropdownMenuItem>
          )}
          <DropdownMenuItem
            onClick={() => setReportOpen(true)}
            className="cursor-pointer"
          >
            <Flag className="h-4 w-4 mr-2" />
            Denunciar
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Block confirmation */}
      <AlertDialog open={blockOpen} onOpenChange={setBlockOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Bloquear usuario</AlertDialogTitle>
            <AlertDialogDescription>
              Tem certeza que deseja bloquear {conversation.other_participant_name}?
              Voce nao recebera mais mensagens desta pessoa.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={onBlock} className="bg-destructive text-destructive-foreground">
              Bloquear
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Report dialog */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Denunciar conversa</DialogTitle>
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
            <Button variant="outline" onClick={() => setReportOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleReport} disabled={!reportReason.trim()}>
              Enviar denuncia
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
