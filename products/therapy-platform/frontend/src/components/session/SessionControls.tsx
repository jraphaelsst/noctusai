import { useState } from 'react';
import { Mic, MicOff, Video, VideoOff, Monitor, MessageSquare, PhoneOff, Clock } from 'lucide-react';
import { Button } from '@noctusai/seed/components/ui/button';
import { cn } from '@/lib/utils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@noctusai/seed/components/ui/alert-dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@noctusai/seed/components/ui/tooltip';

interface SessionControlsProps {
  isTherapist: boolean;
  isRecording: boolean;
  elapsedSeconds: number;
  isChatOpen: boolean;
  onToggleChat: () => void;
  onEndSession: () => void;
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function SessionControls({
  isTherapist,
  isRecording,
  elapsedSeconds,
  isChatOpen,
  onToggleChat,
  onEndSession,
}: SessionControlsProps) {
  const [micOn, setMicOn] = useState(true);
  const [camOn, setCamOn] = useState(true);

  return (
    <div className="flex items-center justify-between border-t bg-gray-900 px-4 py-3 md:px-8">
      {/* Left: recording indicator + timer */}
      <div className="flex items-center gap-4">
        {isRecording && (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
            Gravando
          </div>
        )}
        <div className="flex items-center gap-1.5 text-sm text-gray-300">
          <Clock className="h-4 w-4" />
          {formatElapsed(elapsedSeconds)}
        </div>
      </div>

      {/* Center: media controls */}
      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-11 w-11 rounded-full',
                micOn ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-red-600 text-white hover:bg-red-500',
              )}
              onClick={() => setMicOn((v) => !v)}
            >
              {micOn ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{micOn ? 'Desativar microfone' : 'Ativar microfone'}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-11 w-11 rounded-full',
                camOn ? 'bg-gray-700 text-white hover:bg-gray-600' : 'bg-red-600 text-white hover:bg-red-500',
              )}
              onClick={() => setCamOn((v) => !v)}
            >
              {camOn ? <Video className="h-5 w-5" /> : <VideoOff className="h-5 w-5" />}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{camOn ? 'Desativar camera' : 'Ativar camera'}</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-11 w-11 rounded-full bg-gray-700 text-gray-500 cursor-not-allowed"
              disabled
            >
              <Monitor className="h-5 w-5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Compartilhar tela (em breve)</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'h-11 w-11 rounded-full',
                isChatOpen ? 'bg-blue-600 text-white hover:bg-blue-500' : 'bg-gray-700 text-white hover:bg-gray-600',
              )}
              onClick={onToggleChat}
            >
              <MessageSquare className="h-5 w-5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Chat</TooltipContent>
        </Tooltip>
      </div>

      {/* Right: end session */}
      <div>
        {isTherapist ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" className="gap-2 rounded-full px-5">
                <PhoneOff className="h-4 w-4" />
                Encerrar Sessao
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Encerrar sessao?</AlertDialogTitle>
                <AlertDialogDescription>
                  A gravacao sera finalizada e o resumo automatico sera gerado. Deseja continuar?
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancelar</AlertDialogCancel>
                <AlertDialogAction onClick={onEndSession} className="bg-red-600 hover:bg-red-700">
                  Encerrar
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <div className="w-36" /> // spacer for non-therapist
        )}
      </div>
    </div>
  );
}
