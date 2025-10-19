// frontend-app/src/services/monitoringApi.js
import axios from 'axios';

// Use the environment variable for the API base URL
const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000';

const apiClient = axios.create({
  baseURL: VITE_API_BASE_URL,
});

export const getMarketHealth = () => apiClient.get('/monitor/market-health');

// Future functions for watchlist and portfolio will go here
// export const getWatchlist = () => apiClient.get('/monitor/watchlist');
// export const addWatchlistItem = (ticker) => apiClient.post('/monitor/watchlist', { ticker });