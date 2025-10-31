// frontend-app/src/hooks/useMarketHealthQuery.js
import { useQuery } from '@tanstack/react-query';
import { getMarketHealth } from '../services/monitoringApi';

// Stable key so all pages/widgets share the same cache entry
const queryKey = ['monitoring', 'marketHealth'];

export function useMarketHealthQuery(options = {}) {
  return useQuery({
    queryKey,
    queryFn: async () => {
      const res = await getMarketHealth();
      return res.data; // normalize to the data payload
    },
    // Dashboard-friendly defaults; can be overridden per-call via options
    staleTime: 1000 * 60 * 5,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 2,
    ...options,
  });
}
