// frontend-app/src/types/monitoring.ts
// Monitoring service frontend contracts for watchlist and archive.

/**
 * WatchlistStatus matches the backend WatchlistStatus enum.
 *
 * Backend enum values (contracts.py / DATA_CONTRACTS.md):
 * - "Pending"
 * - "Failed"
 * - "Watch"
 * - "Buy Alert"
 * - "Buy Ready"
 *
 * This is a UI-facing label derived by the monitoring-service.
 */
export type WatchlistStatus =
  | 'Pending'
  | 'Failed'
  | 'Watch'
  | 'Buy Alert'
  | 'Buy Ready';

/**
 * LastRefreshStatus matches the backend LastRefreshStatus enum.
 *
 * Backend enum values:
 * - "PENDING"
 * - "PASS"
 * - "FAIL"
 * - "UNKNOWN"
 *
 * This reflects the internal health-check status of the last refresh run.
 */
export type LastRefreshStatus = 'PENDING' | 'PASS' | 'FAIL' | 'UNKNOWN';

/**
 * ArchiveReason matches the backend ArchiveReason enum used for archived items.
 *
 * Backend enum values:
 * - "MANUAL_DELETE"       // user explicitly removed the item
 * - "FAILED_HEALTH_CHECK"  // auto-archived by health check orchestrator
 */
export type ArchiveReason = 'MANUAL_DELETE' | 'FAILED_HEALTH_CHECK';

/**
 * WatchlistItem mirrors the GET /monitorwatchlist response item shape.
 *
 * All field names and nullability match the backend JSON contract:
 * - snake_case for multi-word fields (e.g. `is_favourite`, `vol_vs_50d_ratio`)
 */
export interface WatchlistItem {
  /** Stock symbol, uppercase (e.g., "NVDA"). */
  ticker: string;

  /**
   * UI-facing status label derived by monitoring-service.
   * Examples: "Watch", "Buy Alert", "Buy Ready".
   */
  status: WatchlistStatus;

  /**
   * ISO 8601 timestamp string when the ticker was added to the watchlist,
   * or null if the backend has no recorded date.
   * Example: "2025-09-20T10:00:00Z"
   */
  date_added: string | null;

  /** Whether the user has marked this ticker as a favourite. */
  is_favourite: boolean;

  /**
   * Internal health-check status enum for the last refresh run.
   * Drives archive behavior and status derivation.
   */
  last_refresh_status: LastRefreshStatus;

  /**
   * ISO 8601 timestamp string of the most recent refresh run,
   * or null if the item has never been refreshed.
   */
  last_refresh_at: string | null;

  /**
   * Pipeline stage where the item most recently failed
   * (e.g., "screen", "vcp", "freshness", "leadership") or null.
   */
  failed_stage: string | null;

  /**
   * Latest market price used by the refresh job, or null if unavailable.
   */
  current_price: number | null;

  /**
   * Detected VCP pivot price, if any, or null when no pivot is present.
   */
  pivot_price: number | null;

  /**
   * Distance from pivot as a percentage (negative means below pivot),
   * or null when no pivot is defined.
   * Example: -0.58 for -0.58%.
   */
  pivot_proximity_percent: number | null;

  /**
   * True when price is currently at/near the actionable pivot zone.
   * Used to drive a "pivot" badge in the UI.
   *
   * Note: name matches backend JSON (`is_at_pivot`).
   */
  is_at_pivot: boolean;

  /**
   * True when the stock is in a recognised pullback setup zone.
   * Used to drive the "PB" badge in the UI.
   *
   * Note: name matches backend JSON (`has_pullback_setup`).
   */
  has_pullback_setup: boolean;

  /**
   * Leadership flag: true if this ticker currently qualifies
   * as a leadership candidate according to leadership-service.
   */
  is_leader: boolean;

  /** Most recent session's volume, or null when unavailable. */
  vol_last: number | null;

  /** 50-day average volume, or null when unavailable. */
  vol_50d_avg: number | null;

  /**
   * Ratio of current volume to 50-day average volume (e.g., 2.1 for 2.1x),
   * or null when insufficient data is available.
   */
  vol_vs_50d_ratio: number | null;

  /**
   * Latest session price change in percent (e.g., 2.5 for +2.5),
   * or null when unavailable.
   */
  day_change_pct: number | null;

  // ✅ NEW: VCP Pattern Fields
  vcp_pass: boolean | null;
  vcpFootprint: string | null;
  is_pivot_good: boolean | null;
  pattern_age_days: number | null;
  
  // ✅ NEW: Pivot Setup Flags
  has_pivot: boolean | null;
  days_since_pivot: number | null;
  
  // ✅ NEW: Freshness Check
  fresh: boolean | null;
  message: string | null;
}

/**
 * Metadata envelope reused across watchlist-related list responses.
 * Mirrors WatchlistMetadata in the backend.
 */
export interface WatchlistMetadata {
  /** Total number of items in the corresponding list. */
  count: number;
}

/**
 * Response schema for GET /monitor/watchlist.
 *
 * Shape:
 * {
 *   "items": [ WatchlistItem, ... ],
 *   "metadata": { "count": number }
 * }
 */
export interface GetWatchlistResponse {
  /** List of active watchlist items for the current user. */
  items: WatchlistItem[];

  /** Simple metadata object including item count. */
  metadata: WatchlistMetadata;
}

/**
 * ArchivedWatchlistItem mirrors entries from archived_watchlist_items
 * as exposed by GET /monitorarchive.
 *
 * Internal fields such as `user_id` and Mongo `_id` are intentionally omitted.
 */
export interface ArchivedWatchlistItem {
  /** Stock symbol, uppercase (e.g., "CRM"). */
  ticker: string;

  /**
   * ISO 8601 timestamp string when the item was moved to the archive.
   * This is the field used for TTL expiry in MongoDB.
   */
  archived_at: string;

  /**
   * Reason the item was archived:
   * - "MANUAL_DELETE"      -> user-triggered removal
   * - "FAILED_HEALTH_CHECK" -> auto-archived by health check
   */
  reason: ArchiveReason;

  /**
   * Pipeline stage where the item failed when reason is FAILED_HEALTH_CHECK
   * (e.g., "screen", "vcp", "freshness"), or null for manual deletions.
   */
  failed_stage: string | null;
}

/**
 * Response schema for GET /monitor/archive.
 *
 * Shape:
 * {
 *   "archived_items": [ ArchivedWatchlistItem, ... ],
 *   "metadata": { "count": number }
 * }
 */
export interface GetWatchlistArchiveResponse {
  /** List of archived watchlist items for the "Recently Archived" tab. */
  archived_items: ArchivedWatchlistItem[];

  /** Shared metadata object including item count. */
  metadata: WatchlistMetadata;
}

/**
 * Basic one-field message payload used by several endpoints.
 */
export interface ApiMessage {
  message: string;
}

/**
 * Response schema for PUT /monitorwatchlist{ticker}.
 */
export interface AddWatchlistItemResponse extends ApiMessage {
  item: WatchlistItem;
}

/**
 * Response schema for POST /monitorwatchlist{ticker}favourite.
 */
export interface WatchlistFavouriteResponse extends ApiMessage {}

/**
 * Response schema for POST /monitorwatchlistbatchremove.
 *
 * The *_tickers arrays may be omitted by older deployments and should
 * be treated as optional.
 */
export interface WatchlistBatchRemoveResponse extends ApiMessage {
  removed: number;
  not_found: number;
  removed_tickers?: string[];
  not_found_tickers?: string[];
}

/**
 * Response schema for DELETE /monitorarchive{ticker}.
 */
export interface DeleteArchiveResponse extends ApiMessage {}
