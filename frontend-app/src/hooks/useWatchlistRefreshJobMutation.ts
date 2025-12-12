// frontend-app/src/hooks/useWatchlistRefreshJobMutation.ts
// watchlist health refresh job mutation hook.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { runWatchlistRefreshJob } from '../services/schedulerApi';
import { WATCHLIST_QUERY_KEY, ARCHIVE_QUERY_KEY } from './queryKeys';

export interface WatchlistRefreshJobData {
  job_id: string;
}

/**
 * useWatchlistRefreshJobMutation
 *
 * Wraps the scheduler watchlist refresh job endpoint in a TanStack Query mutation.
 * Call mutateAsync() to start a new refresh job and receive the job_id payload.
 * Exposes isLoading and error for UI state (e.g., disabling buttons, toasts).
 * Added cache invalidation on success to trigger UI updates.
 */
export function useWatchlistRefreshJobMutation() {
  // Initialize queryClient so it can be used in onSuccess
  const queryClient = useQueryClient();

  const mutation = useMutation<WatchlistRefreshJobData, unknown, void>({
    // No variables are required to start the job.
    mutationFn: async () => {
      // The scheduler API is expected to return { data: { job_id: string } }.
      const response = await runWatchlistRefreshJob();
      return response.data as WatchlistRefreshJobData;
    },
    onSuccess: () => {
      // Invalidate queries immediately to show PENDING status 
      // or fresh data if the job was instant.
      // @ts-expect-error Using tuple overload to satisfy existing patterns
      queryClient.invalidateQueries(WATCHLIST_QUERY_KEY);
      // @ts-expect-error Using tuple overload
      queryClient.invalidateQueries(ARCHIVE_QUERY_KEY);
    },
  });

  // FIX: TanStack Query v5 renamed 'isLoading' to 'isPending' for mutations.
  // We map it here to ensure the consuming component (WatchlistPage)
  // receives the correct flag immediately when the button is pressed.
  return {
    ...mutation,
    isLoading: mutation.isPending
  };
}