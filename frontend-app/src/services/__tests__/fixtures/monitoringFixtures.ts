// frontend-app/src/services/__tests__/fixtures/monitoringFixtures.ts
// monitoring service test fixtures.

import type {
  WatchlistItem,
  GetWatchlistResponse,
  ArchivedWatchlistItem,
  GetWatchlistArchiveResponse,
  AddWatchlistItemResponse,
  WatchlistFavouriteResponse,
  WatchlistBatchRemoveResponse,
  DeleteArchiveResponse,
} from '../../../types/monitoring';

export const mockWatchlistItemNET: WatchlistItem = {
  ticker: 'NET',
  status: 'Buy Ready',
  date_added: '2025-09-20T10:00:00Z',
  is_favourite: false,
  last_refresh_status: 'PASS',
  last_refresh_at: '2025-09-21T10:00:00Z',
  failed_stage: null,
  current_price: 86.0,
  pivot_price: 86.0,
  pivot_proximity_percent: -1.05,
  is_at_pivot: true,
  has_pullback_setup: false,
  is_leader: true,
  vol_last: 12000000,
  vol_50d_avg: 10000000,
  vol_vs_50d_ratio: 1.2,
  day_change_pct: -0.5,
};

export const mockGetWatchlistResponse: GetWatchlistResponse = {
  items: [mockWatchlistItemNET],
  metadata: { count: 1 },
};

export const mockEmptyWatchlistResponse: GetWatchlistResponse = {
  items: [],
  metadata: { count: 0 },
};

export const mockArchivedItemCRM: ArchivedWatchlistItem = {
  ticker: 'CRM',
  archived_at: '2025-09-21T10:00:00Z',
  reason: 'FAILED_HEALTH_CHECK',
  failed_stage: 'vcp',
};

export const mockGetWatchlistArchiveResponse: GetWatchlistArchiveResponse = {
  archived_items: [mockArchivedItemCRM],
  metadata: { count: 1 },
};

export const mockAddWatchlistItemResponseAAPL: AddWatchlistItemResponse = {
  message: 'Ticker AAPL added to watchlist.',
  item: {
    ...mockWatchlistItemNET,
    ticker: 'AAPL',
  },
};

export const mockWatchlistFavouriteResponseAAPL: WatchlistFavouriteResponse = {
  message: 'Watchlist item AAPL favourite set to true.',
};

export const mockWatchlistBatchRemoveResponse: WatchlistBatchRemoveResponse = {
  message: 'Successfully removed 2 tickers from the watchlist (not found: 0).',
  removed: 2,
  not_found: 0,
  removed_tickers: ['AAPL', 'NET'],
  not_found_tickers: [],
};

export const mockDeleteArchiveResponseCRM: DeleteArchiveResponse = {
  message: 'Archived ticker CRM permanently deleted from archive.',
};

// Simple example for market health (shape can be refined from DATA_CONTRACTS)
export const mockMarketHealthResponse = {
  breadth_score: 0.7,
  index_trend: 'UPTREND',
  distribution_days: 3,
};
