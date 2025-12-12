// frontend-app/src/hooks/__tests__/useWatchlistRefreshJobMutation.test.tsx
// watchlist refresh job mutation hook tests.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

import { useWatchlistRefreshJobMutation } from '../useWatchlistRefreshJobMutation';
import { runWatchlistRefreshJob } from '../../services/schedulerApi';

// Mock the service module
vi.mock('../../services/schedulerApi');

/**
 * Helper to wrap hooks with a QueryClientProvider, per frontend testing standard.
 */
const createWrapper = (client: QueryClient) => {
  const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

describe('useWatchlistRefreshJobMutation (Task A.3)', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.resetAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        mutations: {
          retry: false, // Disable retries for predictable test behavior
        },
      },
    });
  });

  it('initial state has no error and is not loading', () => {
    // Arrange
    const wrapper = createWrapper(queryClient);

    // Act
    const { result } = renderHook(() => useWatchlistRefreshJobMutation(), {
      wrapper,
    });

    // Assert
    expect(result.current.isPending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('returns job id when refresh job succeeds', async () => {
    // Arrange
    // Use vi.mocked() to get the type-safe mock handle
    vi.mocked(runWatchlistRefreshJob).mockResolvedValueOnce({
      data: { job_id: 'abc123' },
    });

    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useWatchlistRefreshJobMutation(), {
      wrapper,
    });

    // Act
    const data = await result.current.mutateAsync();

    // Assert
    expect(runWatchlistRefreshJob).toHaveBeenCalledTimes(1);
    // The hook should surface the response data so the caller can read job_id.
    expect(data.job_id).toBe('abc123');
  });

  it('exposes error state when refresh job fails', async () => {
    // Arrange
    vi.mocked(runWatchlistRefreshJob).mockRejectedValueOnce(
      new Error('fail'),
    );

    const wrapper = createWrapper(queryClient);

    const { result } = renderHook(() => useWatchlistRefreshJobMutation(), {
      wrapper,
    });

    // Act & Assert: the promise should reject with the error
    await expect(result.current.mutateAsync()).rejects.toThrow('fail');

    // After the mutation fails, the error should be captured in the mutation state
    await waitFor(() => {
      expect(result.current.error).toBeTruthy();
    });

    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe('fail');
  });
});
