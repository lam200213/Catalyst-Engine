// frontend-app/src/services/schedulerApi.js
// Watchlist refresh job API wrapper – to be implemented in Week 10

import axios from 'axios';

/**
 * @typedef {import('./schedulerApi').WatchlistRefreshJobResponse} WatchlistRefreshJobResponse
 */

/**
 * Base URL for all scheduler-service requests.
 * Reuses the same gateway base URL as monitoringApi; backend routes to the
 * appropriate microservice behind the gateway.
 */
const VITE_API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

/** @type {import('axios').AxiosInstance} */
const schedulerClient = axios.create({
  baseURL: VITE_API_BASE_URL,
});

/**
 * POST /scheduler/watchlist/refresh
 *
 * Starts a background job that recomputes watchlist health.
 * Returns a response with shape: { data: { job_id: string } }.
 *
 * Week 10 will finalize the exact scheduler-service path and behavior, but
 * this wrapper provides the stable contract expected by the frontend hooks
 * and tests today.
 *
 * @returns {Promise<WatchlistRefreshJobResponse>}
 */
export const runWatchlistRefreshJob = () =>
  // schedulerClient.post('/scheduler/watchlist/refresh');
  // test purpose only
  schedulerClient.post('/monitor/internal/watchlist/refresh-status');
