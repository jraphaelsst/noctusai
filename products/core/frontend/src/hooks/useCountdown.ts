import { useCallback, useEffect, useState } from 'react';

/** Whole seconds left until a deadline set by `start(seconds)`; 0 when idle/finished. */
export function useCountdown() {
  const [deadline, setDeadline] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (deadline === null) return;
    // poll-budget: 1s; 0 calls/tick (local countdown); worst 0/day per open tab; hidden=runs
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      if (t >= deadline) setDeadline(null);
    }, 250);
    return () => clearInterval(id);
  }, [deadline]);

  const start = useCallback((seconds: number) => {
    const t = Date.now();
    setNow(t);
    setDeadline(t + seconds * 1000);
  }, []);

  const secondsLeft = deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000));
  return { secondsLeft, start };
}
