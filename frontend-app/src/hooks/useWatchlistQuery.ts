// frontend-app/src/hooks/useWatchlistQuery.ts
// Watchlist & Archive query hooks (TanStack Query)

import { useQuery, type UseQueryOptions } from '@tanstack/react-query';

import { WATCHLIST_QUERY_KEY, ARCHIVE_QUERY_KEY } from './queryKeys';
import {
  getWatchlist,
  getWatchlistArchive,
} from '../services/monitoringApi';
import type {
  GetWatchlistResponse,
  GetWatchlistArchiveResponse,
} from '../types/monitoring';

/**
 * useWatchlistQuery
 *
 * Wraps GET /monitor/watchlist.
 * Data shape conforms to GetWatchlistResponse from the contracts.
 * Accepts options to allow polling (refetchInterval) or other overrides.
 */
export function useWatchlistQuery(options?: Partial<UseQueryOptions<GetWatchlistResponse, Error>>) {
  return useQuery<GetWatchlistResponse, Error>({
    queryKey: WATCHLIST_QUERY_KEY,
    queryFn: async () => {
      const response = await getWatchlist();
      // Axios wrapper returns { data: GetWatchlistResponse }      
      return response.data;
    },
    retry: false,
    ...options, // Spread options to allow refetchInterval
  });
}

/**
 * useWatchlistArchiveQuery
 *
 * Wraps GET /monitor/archive.
 */
export function useWatchlistArchiveQuery(options?: Partial<UseQueryOptions<GetWatchlistArchiveResponse, Error>>) {
  return useQuery<GetWatchlistArchiveResponse, Error>({
    queryKey: ARCHIVE_QUERY_KEY,
    queryFn: async () => {
      const response = await getWatchlistArchive();
      return response.data;
    },
    retry: false,
    ...options,
  });
}