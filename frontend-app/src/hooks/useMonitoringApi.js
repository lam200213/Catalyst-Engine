// frontend-app/src/hooks/useMonitoringApi.js
import { useState, useCallback, useEffect } from 'react';

export const useMonitoringApi = (apiFunc, autoFetch = true) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(autoFetch); // Start loading if autoFetch is true
  const [error, setError] = useState(null);

  const request = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFunc(...args);
      setData(response.data);
      return response.data;
    } catch (err) {
      const errorMessage = err.response?.data?.error || 'An unexpected error occurred. Please try again later.';
      setError(errorMessage);
      throw err; // Re-throw for component-level handling if needed
    } finally {
      setLoading(false);
    }
  }, [apiFunc]);

  useEffect(() => {
    if (autoFetch) {
      request();
    }
  }, [request, autoFetch]);


  return { data, loading, error, request };
};