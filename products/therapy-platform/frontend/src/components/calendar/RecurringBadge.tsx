import { Repeat } from 'lucide-react';
import { cn } from '@/lib/utils';
import { RECURRING_FREQUENCY_LABELS, type RecurringFrequency } from '@/types/scheduling';

interface RecurringBadgeProps {
  frequency?: RecurringFrequency;
  className?: string;
}

export function RecurringBadge({ frequency, className }: RecurringBadgeProps) {
  const label = frequency ? RECURRING_FREQUENCY_LABELS[frequency] : 'Recorrente';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-800',
        className
      )}
    >
      <Repeat className="h-3 w-3" />
      {label}
    </span>
  );
}
