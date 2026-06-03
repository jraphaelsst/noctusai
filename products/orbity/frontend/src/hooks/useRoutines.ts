/**
 * Routines hooks for Orbity — re-exports from useTasks.ts.
 *
 * The routines domain is defined alongside tasks in the backend
 * (tasks_router.py / tasks.py schemas). This file provides a dedicated
 * import seam so page components can `import ... from '@/hooks/useRoutines'`
 * without coupling to the tasks file — cleaner per-entity file convention.
 */
export type { Routine, RoutineCadence, RoutineCreateData, RoutineUpdateData } from './useTasks';
export {
  useRoutines,
  useCreateRoutine,
  useUpdateRoutine,
  useDeleteRoutine,
  useRunDueRoutines,
} from './useTasks';
