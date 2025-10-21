// frontend-app/src/hooks/useMonitoringApi.js

import { useState, useCallback, useEffect } from 'react';

export const useMonitoringApi = (apiFunc, autoFetch = true, retryCount = 2) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(autoFetch);
  const [error, setError] = useState(null);

  const request = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    
    let attempts = 0;
    
    while (attempts <= retryCount) {
      try {
        const response = await apiFunc(...args);
        setData(response.data);
      // debug log (remove after verifying)
      // console.log('Market health payload:', response.data);
      return response.data;
      } catch (err) {
        attempts++;
        
        if (attempts > retryCount) {
          // Enhanced error categorization
          const errorMessage = err.response?.status === 503 
            ? 'Service temporarily unavailable. Please try again later.'
            : err.response?.data?.error || 'An unexpected error occurred.';
          
          setError(errorMessage);
          throw err;
        }
        
        // Exponential backoff for retries
        await new Promise(resolve => setTimeout(resolve, 1000 * Math.pow(2, attempts - 1)));
      } finally {
        // always clear loading
        setLoading(false);
      }
    }
  }, [apiFunc, retryCount]);

  useEffect(() => {
    if (autoFetch) {
      request();
    }
  }, [request, autoFetch]);

  return { data, loading, error, request, retry: () => request() };
};
