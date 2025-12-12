// frontend-app/src/hooks/__tests__/useStockData.test.js

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useStockData } from '../useStockData';
import { fetchStockData } from '../../services/screeningApi';

vi.mock('../../services/screeningApi', () => ({
  fetchStockData: vi.fn(),
}));

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // QueryClient default; hook overrides retry to 1, but we keep this for other tests
        retryDelay: 0, // IMPORTANT: make hook retry fast (hook sets retry: 1 but not retryDelay)
        gcTime: 0,
      },
      mutations: { retry: false },
    },
  });
}

function createQueryWrapper(queryClient) {
  return function Wrapper({ children }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('hooks/useStockData', () => {
  let queryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    queryClient = createQueryClient();
  });

  afterEach(() => {
    // Prevent cross-test cache bleed
    queryClient.clear();
  });

  it('should initialize with the provided ticker and start fetching immediately', async () => {
    fetchStockData.mockResolvedValueOnce({
      screening: { ticker: 'GOOG' },
      analysis: { message: 'ok' },
    });

    const wrapper = createQueryWrapper(queryClient);

    const { result } = renderHook(() => useStockData('GOOG'), { wrapper });

    expect(result.current.ticker).toBe('GOOG');

    await waitFor(() => {
      expect(fetchStockData).toHaveBeenCalledWith('GOOG');
    });
  });

  it('should handle the full data fetching lifecycle successfully', async () => {
    fetchStockData.mockResolvedValueOnce({
      screening: { ticker: 'TSLA' },
      analysis: { message: 'ok' },
    });

    const wrapper = createQueryWrapper(queryClient);

    // Start with disabled query to isolate getData() behavior
    const { result } = renderHook(() => useStockData(''), { wrapper });

    act(() => {
      result.current.getData('TSLA');
    });

    await waitFor(() => {
      expect(fetchStockData).toHaveBeenCalledWith('TSLA');
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBe(null);
      expect(result.current.ticker).toBe('TSLA');
      expect(result.current.data).toEqual({
        screening: { ticker: 'TSLA' },
        analysis: { message: 'ok' },
      });
    });
  });

  it('should handle errors from the API call', async () => {
    const errorMessage = 'API request failed';

    // Hook has retry: 1, so it will call fetchStockData twice on error.
    fetchStockData.mockImplementation(() => Promise.reject(new Error(errorMessage)));

    const wrapper = createQueryWrapper(queryClient);
    const { result } = renderHook(() => useStockData(''), { wrapper });

    act(() => {
      result.current.getData('FAIL');
    });

    await waitFor(
      () => {
        expect(fetchStockData).toHaveBeenCalledWith('FAIL');
        expect(result.current.loading).toBe(false);
        expect(result.current.error).toBe(errorMessage);
        expect(result.current.data).toEqual({ screening: null, analysis: null });
      },
      { timeout: 2000 },
    );
  });

  it('should update the ticker when setTicker is called', () => {
    const wrapper = createQueryWrapper(queryClient);
    const { result } = renderHook(() => useStockData(''), { wrapper });

    act(() => {
      result.current.setTicker('Updated');
    });

    expect(result.current.ticker).toBe('Updated');
  });
});