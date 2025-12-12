// frontend-app/src/hooks/__tests__/useScreeningJobMutations.test.tsx
// screening job mutation hook tests.

import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';

import { WATCHLIST_QUERY_KEY, ARCHIVE_QUERY_KEY } from '../queryKeys';
import { useScreeningJobMutations } from '../useScreeningJobMutations';
import * as monitoringApi from '../../services/monitoringApi';

vi.mock('../../services/monitoringApi');

const createWrapperWithClient = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: { children?: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return Wrapper;
};

describe('useScreeningJobMutations', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.resetAllMocks();
    queryClient = new QueryClient();
  });

  it('useAddWatchlistItem invalidates watchlist and archive on success', async () => {
    // Arrange
    const spyInvalidate = vi.spyOn(queryClient, 'invalidateQueries');

    // Use type assertion for the mock
    vi.spyOn(monitoringApi, 'addWatchlistItem').mockResolvedValueOnce(
      // ts-expect-error partial response object is sufficient for this test
      { data: { message: 'ok' } },
    );

    const wrapper = createWrapperWithClient(queryClient);

    const { result } = renderHook(() => useScreeningJobMutations(), {
      wrapper,
    });

    // Act
    await result.current.useAddWatchlistItem().mutateAsync('net');

    // Assert
    expect(monitoringApi.addWatchlistItem).toHaveBeenCalledWith('net');

    expect(spyInvalidate).toHaveBeenCalledWith(WATCHLIST_QUERY_KEY);
    expect(spyInvalidate).toHaveBeenCalledWith(ARCHIVE_QUERY_KEY);
  });

  it('useToggleFavourite invalidates only watchlist', async () => {
    // Arrange
    const spyInvalidate = vi.spyOn(queryClient, 'invalidateQueries');

    vi.spyOn(monitoringApi, 'setFavouriteStatus').mockResolvedValueOnce(
      // ts-expect-error partial response object is sufficient for this test
      { data: { message: 'ok' } },
    );

    const wrapper = createWrapperWithClient(queryClient);

    const { result } = renderHook(() => useScreeningJobMutations(), {
      wrapper,
    });

    // Act
    await result.current
      .useToggleFavourite()
      .mutateAsync({ ticker: 'NET', is_favourite: true });

    // Assert
    expect(monitoringApi.setFavouriteStatus).toHaveBeenCalledWith(
      'NET',
      true,
    );

    expect(spyInvalidate).toHaveBeenCalledWith(WATCHLIST_QUERY_KEY);
    expect(spyInvalidate).not.toHaveBeenCalledWith(ARCHIVE_QUERY_KEY);
  });

  it('mutation hooks surface error state when API rejects', async () => {
    // Arrange
    vi.spyOn(monitoringApi, 'removeWatchlistItem').mockRejectedValueOnce(
      new Error('boom'),
    );

    const wrapper = createWrapperWithClient(queryClient);

    const { result } = renderHook(() => useScreeningJobMutations(), {
      wrapper,
    });

    // Act & Assert
    await expect(
      result.current.useRemoveWatchlistItem().mutateAsync('NET'),
    ).rejects.toThrow('boom');
  });
});
