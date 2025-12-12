// frontend-app/src/components/__tests__/fixtures/watchlistFixtures.js
// shared watchlist fixtures for watchlist-related component and page tests.

// Base WatchlistItem fixture matching src/types/monitoring.ts (snake_case fields).
export const baseWatchlistItem = {
  ticker: 'NET',
  status: 'Buy Ready',
  date_added: '2025-09-20',
  is_favourite: true,
  is_leader: true,
  is_at_pivot: true,
  has_pullback_setup: true,
  last_refresh_status: 'PASS',
  last_refresh_at: '2025-09-21T10:00:00Z',
  failed_stage: null,
  current_price: 86.0,
  pivot_price: 86.0,
  pivot_proximity_percent: -1.05,
  vol_last: 12_000_000,
  vol_50d_avg: 10_000_000,
  vol_vs_50d_ratio: 3.1,
  day_change_pct: 2.5,
};

// Helper to create WatchlistItem variants.
export const makeWatchlistItem = (overrides = {}) => ({
  ...baseWatchlistItem,
  ...overrides,
});

// Base ArchivedWatchlistItem fixture.
export const baseArchivedWatchlistItem = {
  ticker: 'CRM',
  archived_at: '2025-09-21T10:00:00Z',
  reason: 'FAILEDHEALTHCHECK',
  failed_stage: 'vcp',
};

// Helper to create ArchivedWatchlistItem variants.
export const makeArchivedWatchlistItem = (overrides = {}) => ({
  ...baseArchivedWatchlistItem,
  ...overrides,
});
