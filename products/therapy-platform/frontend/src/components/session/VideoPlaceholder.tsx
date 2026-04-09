import { Video, User } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VideoPlaceholderProps {
  therapistName: string;
  patientName: string;
  isActive: boolean;
}

function ParticipantBox({ name, isLarge }: { name: string; isLarge?: boolean }) {
  const initials = name
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('');

  return (
    <div
      className={cn(
        'relative flex flex-col items-center justify-center rounded-xl bg-gray-800',
        isLarge ? 'flex-1' : 'h-32 w-44 md:h-40 md:w-56',
      )}
    >
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-gray-600 text-xl font-semibold text-white md:h-20 md:w-20 md:text-2xl">
        {initials || <User className="h-8 w-8" />}
      </div>
      <span className="mt-2 text-sm text-gray-300">{name}</span>
    </div>
  );
}

export function VideoPlaceholder({ therapistName, patientName, isActive }: VideoPlaceholderProps) {
  return (
    <div className="relative flex h-full w-full flex-col items-center justify-center gap-4 bg-gray-900 p-4">
      {isActive && (
        <div className="absolute left-4 top-4 flex items-center gap-2 rounded-full bg-green-600/80 px-3 py-1 text-sm text-white">
          <Video className="h-4 w-4" />
          Video call ativa
        </div>
      )}

      <div className="flex flex-1 w-full items-center justify-center gap-4">
        <ParticipantBox name={therapistName} isLarge />
        <ParticipantBox name={patientName} isLarge />
      </div>

      {/* Picture-in-picture style self view */}
      <div className="absolute bottom-20 right-4">
        <ParticipantBox name="Voce" />
      </div>
    </div>
  );
}
