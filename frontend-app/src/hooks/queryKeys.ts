// frontend-app/src/hooks/queryKeys.ts
// shared query keys for monitoring-related React Query hooks.

export const WATCHLIST_QUERY_KEY = ['monitoring', 'watchlist'] as const;
export type WatchlistQueryKey = typeof WATCHLIST_QUERY_KEY;

export const ARCHIVE_QUERY_KEY = ['monitoring', 'archive'] as const;
export type ArchiveQueryKey = typeof ARCHIVE_QUERY_KEY;