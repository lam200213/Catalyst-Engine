// frontend-app/src/services/monitoringApi.js
// monitoring-service Axios wrappers for watchlist and archive.

import axios from 'axios';

/**
 * @typedef {import('../types/monitoring').GetWatchlistResponse} GetWatchlistResponse
 * @typedef {import('../types/monitoring').GetWatchlistArchiveResponse} GetWatchlistArchiveResponse
 * @typedef {import('../types/monitoring').AddWatchlistItemResponse} AddWatchlistItemResponse
 * @typedef {import('../types/monitoring').ApiMessage} ApiMessage
 * @typedef {import('../types/monitoring').WatchlistFavouriteResponse} WatchlistFavouriteResponse
 * @typedef {import('../types/monitoring').WatchlistBatchRemoveResponse} WatchlistBatchRemoveResponse
 * @typedef {import('../types/monitoring').DeleteArchiveResponse} DeleteArchiveResponse
 */

/**
 * Use the environment variable for the API base URL.
 * Fallback is the local dev gateway.
 */
const VITE_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

/** @type {import('axios').AxiosInstance} */
const apiClient = axios.create({
  baseURL: VITE_API_BASE_URL,
});

/**
 * Normalize a ticker for use in URLs:
 * - trim whitespace
 * - uppercase
 * - URL encode (for dots, hyphens, etc.)
 *
 * @param {string} rawTicker
 * @returns {string}
 */
const normalizeTicker = (rawTicker) =>
  encodeURIComponent(rawTicker.trim().toUpperCase());

/**
 * GET /monitormarket-health
 *
 * Market Health is not in the watchlist/archive Task A scope, so we leave
 * the response type as unknown for now.
 *
 * @returns {Promise<import('axios').AxiosResponse<unknown>>}
 */
export const getMarketHealth = () =>
  apiClient.get('/monitor/market-health');

/**
 * GET /monitor/watchlist/
 *
 * @returns {Promise<import('axios').AxiosResponse<GetWatchlistResponse>>}
 */
export const getWatchlist = () =>
  apiClient.get('/monitor/watchlist');

/**
 * PUT /monitor/watchlist/{TICKER}
 *
 * - Adds (or re-introduces) a ticker to the watchlist.
 * - Ticker is normalized to uppercase.
 * - No request body is sent; backend ignores any body.
 *
 * @param {string} ticker
 * @returns {Promise<import('axios').AxiosResponse<AddWatchlistItemResponse>>}
 */
export const addWatchlistItem = (ticker) => {
  const symbol = normalizeTicker(ticker);
  return apiClient.put(`/monitor/watchlist/${symbol}`);
};

/**
 * POST /monitor/watchlist/batch/add
 * - Public wrapper for batch add.
 * - Accepts a list of tickers strings.
 * @param {string[]} tickers
 * @returns {Promise<import('axios').AxiosResponse<any>>}
 */
export const addWatchlistBatch = (tickers) => {
    const uppercased = tickers.map((t) => t.trim().toUpperCase());
    return apiClient.post('/monitor/watchlist/batch/add', {
        tickers: uppercased
    });
};

/**
 * DELETE /monitor/watchlist/{TICKER}
 *
 * - Removes a ticker from the active watchlist and archives it
 * with reason MANUAL_DELETE.
 *
 * @param {string} ticker
 * @returns {Promise<import('axios').AxiosResponse<ApiMessage>>}
 */
export const removeWatchlistItem = (ticker) => {
  const symbol = normalizeTicker(ticker);
  return apiClient.delete(`/monitor/watchlist/${symbol}`);
};

/**
 * POST /monitor/watchlist/{TICKER}/favourite
 *
 * - Toggles the is_favourite flag on the watchlist item.
 * - Both the parameter and request body use snake_case `is_favourite` to match backend contract.
 *
 * @param {string} ticker
 * @param {boolean} is_favourite - The new favourite status to set
 * @returns {Promise<import('axios').AxiosResponse<WatchlistFavouriteResponse>>}
 */
export const setFavouriteStatus = (ticker, is_favourite) => {
  const symbol = normalizeTicker(ticker);
  return apiClient.post(`/monitor/watchlist/${symbol}/favourite`, {
    is_favourite,
  });
};

/**
 * POST /monitor/watchlist/batch/remove
 *
 * - Batch remove tickers from the watchlist, archiving them as MANUAL_DELETE.
 * - Tickers are normalized to uppercase before sending.
 *
 * @param {string[]} tickers
 * @returns {Promise<import('axios').AxiosResponse<WatchlistBatchRemoveResponse>>}
 */
export const removeWatchlistBatch = (tickers) => {
  const uppercased = tickers.map((t) => t.trim().toUpperCase());
  return apiClient.post('/monitor/watchlist/batch/remove', {
    tickers: uppercased,
  });
};

/**
 * GET /monitor/archive/
 *
 * @returns {Promise<import('axios').AxiosResponse<GetWatchlistArchiveResponse>>}
 */
export const getWatchlistArchive = () =>
  apiClient.get('/monitor/archive');

/**
 * DELETE /monitor/archive/{TICKER}
 *
 * - Permanently deletes an archived item from the graveyard.
 *
 * @param {string} ticker
 * @returns {Promise<import('axios').AxiosResponse<DeleteArchiveResponse>>}
 */
export const deleteFromArchive = (ticker) => {
  const symbol = normalizeTicker(ticker);
  return apiClient.delete(`/monitor/archive/${symbol}`);
};