// frontend-app/src/hooks/useMarketHealthQuery.js
import { useQuery } from '@tanstack/react-query';
import { getMarketHealth } from '../services/monitoringApi';

// Stable key so all pages/widgets share the same cache entry
export const MARKET_HEALTH_QUERY_KEY = ['monitoring', 'marketHealth'];

// Export the specific fetcher logic so App.jsx can use it too.
// This ensures App.jsx stores 'res.data' in the cache, not the full Axios object.
export const fetchMarketHealth = async () => {
  const res = await getMarketHealth();
  return res.data; 
};

export function useMarketHealthQuery(options = {}) {
  return useQuery({
    queryKey: MARKET_HEALTH_QUERY_KEY,
    queryFn: fetchMarketHealth, // Use the shared fetcher
    // Dashboard-friendly defaults; can be overridden per-call via options
    staleTime: 1000 * 60 * 5,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 2,
    ...options,
  });
}