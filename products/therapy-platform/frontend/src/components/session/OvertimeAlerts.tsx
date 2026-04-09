import { useEffect, useRef } from 'react';
import { toast } from 'sonner';

const THRESHOLDS = [30, 15, 10, 5, 2, 1] as const;

interface OvertimeAlertsProps {
  minutesRemaining?: number;
}

export function OvertimeAlerts({ minutesRemaining }: OvertimeAlertsProps) {
  const firedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (minutesRemaining == null) return;

    for (const threshold of THRESHOLDS) {
      if (minutesRemaining <= threshold && !firedRef.current.has(threshold)) {
        firedRef.current.add(threshold);
        const label = threshold === 1 ? '1 minuto' : `${threshold} minutos`;
        toast.warning(`Atencao: restam ${label} na janela de sessao`, {
          duration: 6000,
        });
      }
    }
  }, [minutesRemaining]);

  // Reset when component remounts (new session)
  useEffect(() => {
    return () => {
      firedRef.current.clear();
    };
  }, []);

  return null;
}
