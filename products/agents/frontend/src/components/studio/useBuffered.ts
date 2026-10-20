/**
 * Working copy of ONE server value (a criterion, a stage, the parameters). The server answer is the
 * truth: the buffer reseeds from it whenever the user has no unsaved edits, and when the server's
 * value moves under unsaved edits the buffer is kept and `moved` raises the conflict banner.
 */
import { useCallback, useEffect, useState } from "react";

export function useBuffered<T>(server: T) {
  const serverJson = JSON.stringify(server);
  const [value, setValue] = useState<T>(server);
  const [base, setBase] = useState(serverJson);
  const dirty = JSON.stringify(value) !== base;
  const moved = serverJson !== base;

  useEffect(() => {
    if (!dirty && moved) {
      setValue(JSON.parse(serverJson) as T);
      setBase(serverJson);
    }
  }, [dirty, moved, serverJson]);

  const reload = useCallback(() => {
    setValue(JSON.parse(serverJson) as T);
    setBase(serverJson);
  }, [serverJson]);

  const markSaved = useCallback((saved: T) => setBase(JSON.stringify(saved)), []);

  return { value, setValue, dirty, conflict: dirty && moved, reload, markSaved };
}
