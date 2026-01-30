// frontend-app/src/hooks/__tests__/useWatchlistQuery.test.tsx
// useWatchlistQuery and useWatchlistArchiveQuery hook tests.

import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

import {
  useWatchlistQuery,
  useWatchlistArchiveQuery,
} from '../useWatchlistQuery';
import {
  getWatchlist,
  getWatchlistArchive,
} from '../../services/monitoringApi';

// Mock only the Axios service layer, not business logic.
vi.mock('../../services/monitoringApi');

const createWrapper = () => {
  const queryClient = new QueryClient();

  const Wrapper = ({ children }: { children?: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return Wrapper;
};

describe('useWatchlistQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('returns loading state initially for watchlist query', () => {
    // Arrange
    (getWatchlist as Mock).mockResolvedValueOnce({
      data: { items: [], metadata: { count: 0 } },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistQuery(), { wrapper });

    // Assert
    expect(result.current.isLoading).toBe(true);
  });

  it('returns data for watchlist query on success', async () => {
    // Arrange
    (getWatchlist as Mock).mockResolvedValueOnce({
      data: {
        items: [
          {
            ticker: 'NET',
            status: 'Buy Ready',
            date_added: '2025-09-20',
            is_favourite: false,
            last_refresh_status: 'PASS',
            last_refresh_at: '2025-09-21T10:00:00Z',
            failed_stage: null,
            current_price: 85.1,
            pivot_price: 86.0,
            pivot_proximity_percent: -1.05,
            is_at_pivot: true,
            has_pullback_setup: false,
            is_leader: true,
            vol_last: 12_000_000,
            vol_50d_avg: 10_000_000,
            vol_vs_50d_ratio: 1.2,
            day_change_pct: -0.5,
          },
        ],
        metadata: { count: 1 },
      },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistQuery(), { wrapper });

    // Assert
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].ticker).toBe('NET');
  });

  it('handles empty watchlist response as empty array', async () => {
    // Arrange
    (getWatchlist as Mock).mockResolvedValueOnce({
      data: { items: [], metadata: { count: 0 } },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistQuery(), { wrapper });

    // Assert
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toEqual([]);
  });

  it('exposes error state when watchlist API fails', async () => {
    // Arrange
    (getWatchlist as Mock).mockRejectedValueOnce(
      new Error('Network error'),
    );

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistQuery(), { wrapper });

    // Assert
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe('Network error');
  });
});

describe('useWatchlistArchiveQuery', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('returns loading state initially for archive query', () => {
    // Arrange
    (getWatchlistArchive as Mock).mockResolvedValueOnce({
      data: { archived_items: [], metadata: { count: 0 } },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistArchiveQuery(), {
      wrapper,
    });

    // Assert
    expect(result.current.isLoading).toBe(true);
  });

  it('returns data for archive query on success', async () => {
    // Arrange
    (getWatchlistArchive as Mock).mockResolvedValueOnce({
      data: {
        archived_items: [
          {
            ticker: 'CRM',
            archived_at: '2025-09-21T10:00:00Z',
            reason: 'FAILED_HEALTH_CHECK',
            failed_stage: 'vcp',
          },
        ],
        metadata: { count: 1 },
      },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistArchiveQuery(), {
      wrapper,
    });

    // Assert
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.archived_items).toHaveLength(1);
    expect(result.current.data?.archived_items?.[0].ticker).toBe('CRM');
  });

  it('handles empty archive response as empty array', async () => {
    // Arrange
    (getWatchlistArchive as Mock).mockResolvedValueOnce({
      data: { archived_items: [], metadata: { count: 0 } },
    });

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistArchiveQuery(), {
      wrapper,
    });

    // Assert
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.archived_items).toEqual([]);
  });

  it('exposes error state when archive API fails', async () => {
    // Arrange
    (getWatchlistArchive as Mock).mockRejectedValueOnce(
      new Error('Network error'),
    );

    const wrapper = createWrapper();

    // Act
    const { result } = renderHook(() => useWatchlistArchiveQuery(), {
      wrapper,
    });

    // Assert
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeInstanceOf(Error);
    expect((result.current.error as Error).message).toBe('Network error');
  });
});
