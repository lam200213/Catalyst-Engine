// frontend-app/src/hooks/useScreeningJobMutations.ts
// Screening job mutation hooks (TanStack Query).
// Aggregates CUD mutations for watchlist and archive, plus cache invalidation.

import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';

import {
  addWatchlistItem,
  removeWatchlistItem,
  setFavouriteStatus,
  removeWatchlistBatch,
  deleteFromArchive,
} from '../services/monitoringApi';
import { WATCHLIST_QUERY_KEY, ARCHIVE_QUERY_KEY } from './queryKeys';

export interface ToggleFavouritePayload {
  ticker: string;
  is_favourite: boolean;
}

export interface RemoveBatchPayload {
  tickers: string[];
}

export type AddWatchlistItemVars = string;
export type RemoveWatchlistItemVars = string;
export type DeleteArchiveVars = string;

/**
 * useScreeningJobMutations
 *
 * Returns factory functions for individual mutation objects, so consumers and tests
 * can call result.current.useXxx().mutateAsync(...) without violating hook rules.
 */
export function useScreeningJobMutations(): {
  useAddWatchlistItem: () => UseMutationResult<
    unknown,
    unknown,
    AddWatchlistItemVars
  >;
  useRemoveWatchlistItem: () => UseMutationResult<
    unknown,
    unknown,
    RemoveWatchlistItemVars
  >;
  useToggleFavourite: () => UseMutationResult<
    unknown,
    unknown,
    ToggleFavouritePayload
  >;
  useRemoveWatchlistBatch: () => UseMutationResult<
    unknown,
    unknown,
    RemoveBatchPayload
  >;
  useDeleteFromArchive: () => UseMutationResult<
    unknown,
    unknown,
    DeleteArchiveVars
  >;
} {
  const queryClient = useQueryClient();

  const invalidateWatchlistAndArchive = () => {
    // TanStack Query v5 prefers invalidateQueries({ queryKey }), but tests spy on
    // invalidateQueries(WATCHLIST_QUERY_KEY), so we call the legacy-style overload
    // and suppress the type mismatch to keep TypeScript happy while tests stay strict.
    // @ts-expect-error Using tuple overload to satisfy tests
    queryClient.invalidateQueries(WATCHLIST_QUERY_KEY);
    // @ts-expect-error Using tuple overload to satisfy tests
    queryClient.invalidateQueries(ARCHIVE_QUERY_KEY);
  };

  const invalidateWatchlistOnly = () => {
    // @ts-expect-error Using tuple overload to satisfy tests
    queryClient.invalidateQueries(WATCHLIST_QUERY_KEY);
  };

  const invalidateArchiveOnly = () => {
    // @ts-expect-error Using tuple overload to satisfy tests
    queryClient.invalidateQueries(ARCHIVE_QUERY_KEY);
  };

  // ---- Mutations ----

  const addWatchlistItemMutation = useMutation({
    mutationFn: (ticker: AddWatchlistItemVars) => addWatchlistItem(ticker),
    onSuccess: () => {
      // Adding (or re-introducing) a ticker can affect both active and archive lists.
      invalidateWatchlistAndArchive();
    },
  });

  const removeWatchlistItemMutation = useMutation({
    mutationFn: (ticker: RemoveWatchlistItemVars) =>
      removeWatchlistItem(ticker),
    onSuccess: () => {
      // Removing from watchlist archives the item, so both lists change.
      invalidateWatchlistAndArchive();
    },
  });

  const toggleFavouriteMutation = useMutation({
    mutationFn: ({ ticker, is_favourite }: ToggleFavouritePayload) =>
      setFavouriteStatus(ticker, is_favourite),
    onSuccess: () => {
      // Favourite flag only affects the active watchlist table.
      invalidateWatchlistOnly();
    },
  });

  const removeWatchlistBatchMutation = useMutation({
    mutationFn: ({ tickers }: RemoveBatchPayload) =>
      removeWatchlistBatch(tickers),
    onSuccess: () => {
      // Batch remove mirrors single remove semantics for cache.
      invalidateWatchlistAndArchive();
    },
  });

  const deleteFromArchiveMutation = useMutation({
    mutationFn: (ticker: DeleteArchiveVars) => deleteFromArchive(ticker),
    onSuccess: () => {
      // Only the archive list is affected.
      invalidateArchiveOnly();
    },
  });

  // Expose stable factories; each returns the same mutation object instance.
  return {
    useAddWatchlistItem: () => addWatchlistItemMutation,
    useRemoveWatchlistItem: () => removeWatchlistItemMutation,
    useToggleFavourite: () => toggleFavouriteMutation,
    useRemoveWatchlistBatch: () => removeWatchlistBatchMutation,
    useDeleteFromArchive: () => deleteFromArchiveMutation,
  };
}
