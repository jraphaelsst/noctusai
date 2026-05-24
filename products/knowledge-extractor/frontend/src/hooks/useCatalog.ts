/**
 * Catalog hooks — read the processed-knowledge catalog.
 *
 *   useCatalog()              → modules + totals overview
 *   useModule(module)         → lessons within one module (null = not loaded)
 *   useLesson(module, lesson) → a single lesson's transcript + summary
 *
 * Canonical `{ data, loading, error, reload }` shape. Every fetch
 * resolves to a value (the empty/typed shape on failure or 404) so a
 * consumer never reasons over `undefined`.
 */
import { useCallback, useEffect, useState } from "react";

import {
  getCatalog,
  getLesson,
  getModule,
  type Catalog,
  type LessonDetail,
  type ModuleDetail,
} from "@/lib/api";

const EMPTY_CATALOG: Catalog = {
  modules: [],
  totals: { modules: 0, lessons: 0, transcripts: 0, summaries: 0 },
};

export function useCatalog(): {
  data: Catalog;
  loading: boolean;
  error: Error | null;
  reload: () => void;
} {
  const [data, setData] = useState<Catalog>(EMPTY_CATALOG);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [tick, setTick] = useState<number>(0);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    getCatalog()
      .then((resp) => {
        if (!alive) return;
        setData(resp ?? EMPTY_CATALOG);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setData(EMPTY_CATALOG);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [tick]);

  return { data, loading, error, reload };
}

export function useModule(module: string | null): {
  data: ModuleDetail | null;
  loading: boolean;
  error: Error | null;
} {
  const [data, setData] = useState<ModuleDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!module) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);

    getModule(module)
      .then((resp) => {
        if (!alive) return;
        setData(resp ?? { module, lessons: [] });
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setData({ module, lessons: [] });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [module]);

  return { data, loading, error };
}

export function useLesson(
  module: string | null,
  lesson: string | null,
): {
  data: LessonDetail | null;
  loading: boolean;
  error: Error | null;
} {
  const [data, setData] = useState<LessonDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!module || !lesson) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);

    getLesson(module, lesson)
      .then((resp) => {
        if (!alive) return;
        setData(
          resp ?? { module, lesson, transcript: null, summary: null },
        );
      })
      .catch((err: unknown) => {
        if (!alive) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        setData({ module, lesson, transcript: null, summary: null });
      })
      .finally(() => {
        if (alive) setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [module, lesson]);

  return { data, loading, error };
}
