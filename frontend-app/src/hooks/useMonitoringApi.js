// frontend-app/src/hooks/useMonitoringApi.js

import { useState, useCallback, useEffect, useRef } from 'react';

export const useMonitoringApi = (apiFunc, autoFetch = true, retryCount = 2) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(autoFetch);
  const [error, setError] = useState(null);
  const didRunRef = useRef(false); 

  const request = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    
    let attempts = 0;
    
    while (attempts <= retryCount) {
      try {
        const response = await apiFunc(...args);
        console.log('[DEBUG] Market health response:', JSON.stringify(response.data, null, 2));
        setData(response.data);
      // debug log (remove after verifying)
      // console.log('Market health payload:', response.data);
      
      // stop spinner on success
      setLoading(false);
      return response.data;
      } catch (err) {
        attempts++;
        
        if (attempts > retryCount) {
          const errorMessage =
            err?.response?.status === 503
              ? 'Service temporarily unavailable. Please try again later.'
              : err?.response?.data?.error || err?.message || 'An unexpected error occurred.';
          setError(errorMessage);
          setLoading(false);
          throw err;
        }
        
        // Exponential backoff for retries with an upper bound
        const delayMs = Math.min(1000 * 2 ** (attempts - 1), 5000);
        await new Promise((res) => setTimeout(res, delayMs));
      }
    }
  }, [apiFunc, retryCount]);

  useEffect(() => {
    if (!autoFetch || didRunRef.current) return;
    didRunRef.current = true;
    request();
  }, [autoFetch, request]);

  const retry = useCallback(() => request(), [request]);

  return { data, loading, error, retry, request };
};