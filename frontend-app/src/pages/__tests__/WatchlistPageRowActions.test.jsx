// frontend-app/src/pages/__tests__/WatchlistPageRowActions.test.jsx
// Row Actions (favourites, archive deletes, active-row deletes) on WatchlistPage.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import WatchlistPage from '../WatchlistPage';

import {
  baseWatchlistItem,
  baseArchivedWatchlistItem,
} from '../../components/__tests__/fixtures/watchlistFixtures';

import { useWatchlistQuery } from '../../hooks/useWatchlistQuery';
import { useWatchlistArchiveQuery } from '../../hooks/useWatchlistArchiveQuery';
import { useWatchlistRefreshJobMutation } from '../../hooks/useWatchlistRefreshJobMutation';
import { useScreeningJobMutations } from '../../hooks/useScreeningJobMutations';

vi.mock('../../hooks/useWatchlistQuery', () => ({
  useWatchlistQuery: vi.fn(),
}));

vi.mock('../../hooks/useWatchlistArchiveQuery', () => ({
  useWatchlistArchiveQuery: vi.fn(),
}));

vi.mock('../../hooks/useWatchlistRefreshJobMutation', () => ({
  useWatchlistRefreshJobMutation: vi.fn(),
}));

vi.mock('../../hooks/useScreeningJobMutations', () => ({
  useScreeningJobMutations: vi.fn(),
}));

vi.mock('@chakra-ui/react', async (original) => {
  const actual = await original();
  return {
    ...actual,
    useToast: () => vi.fn(),
  };
});

// FIX: Mock Checkbox to avoid "Cannot set property focus" error in JSDOM
vi.mock('@chakra-ui/react', async (original) => {
  const actual = await original();
  return {
    ...actual,
    useToast: () => vi.fn(),
    // Simple mock for Checkbox that renders a native input
    Checkbox: ({ isChecked, onChange, 'aria-label': ariaLabel }) => (
      <input 
        type="checkbox" 
        checked={isChecked} 
        onChange={onChange} 
        aria-label={ariaLabel}
      />
    ),
  };
});

const createWrapper = (client) => {
  const Wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

describe('WatchlistPage Row Actions (Task C.2)', () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
    vi.clearAllMocks();
  });

  it('clicking Favourite on an unfavourited active row calls toggleFavourite with is_favourite: true', async () => {
    const user = userEvent.setup();

    const item = { ...baseWatchlistItem, ticker: 'NET', is_favourite: false };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [item], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: { archived_items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    const toggleSpy = vi.fn().mockResolvedValue({});

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({
        mutateAsync: toggleSpy,
        isLoading: false,
      }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    render(<WatchlistPage />, { wrapper });

    const favButton = screen.getByRole('button', {
      name: /favourite stock net/i,
    });

    await user.click(favButton);

    expect(toggleSpy).toHaveBeenCalledTimes(1);
    expect(toggleSpy).toHaveBeenCalledWith({
      ticker: 'NET',
      is_favourite: true,
    });
  });

  it('clicking Favourite on a favourited active row calls toggleFavourite with is_favourite: false', async () => {
    const user = userEvent.setup();

    const item = { ...baseWatchlistItem, ticker: 'NET', is_favourite: true };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [item], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: { archived_items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    const toggleSpy = vi.fn().mockResolvedValue({});

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({
        mutateAsync: toggleSpy,
        isLoading: false,
      }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    render(<WatchlistPage />, { wrapper });

    const favButton = screen.getByRole('button', {
      name: /favourite stock net/i,
    });

    await user.click(favButton);

    expect(toggleSpy).toHaveBeenCalledTimes(1);
    expect(toggleSpy).toHaveBeenCalledWith({
      ticker: 'NET',
      is_favourite: false,
    });
  });

  it('clicking Delete on an archived row calls deleteFromArchive with ticker', async () => {
    const user = userEvent.setup();

    const archived = {
      ...baseArchivedWatchlistItem,
      ticker: 'CRM',
      failed_stage: 'vcp',
    };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: { archived_items: [archived], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    const deleteSpy = vi.fn().mockResolvedValue({});

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({
        mutateAsync: deleteSpy,
        isLoading: false,
      }),
    });

    const wrapper = createWrapper(queryClient);

    render(<WatchlistPage />, { wrapper });

    const archiveTab = screen.getByRole('tab', {
      name: /recently archived/i,
    });
    await user.click(archiveTab);

    const deleteButton = screen.getByRole('button', {
      name: /delete crm/i,
    });

    await user.click(deleteButton);

    expect(deleteSpy).toHaveBeenCalledTimes(1);
    expect(deleteSpy).toHaveBeenCalledWith('CRM');
  });

  it('clicking Delete on an active row calls removeWatchlistItem mutation with ticker', async () => {
    const user = userEvent.setup();

    const item = { ...baseWatchlistItem, ticker: 'NET', is_favourite: false };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [item], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: { archived_items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    const removeSpy = vi.fn().mockResolvedValue({});

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({
        mutateAsync: removeSpy,
        isLoading: false,
      }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    render(<WatchlistPage />, { wrapper });

    const deleteButton = screen.getByRole('button', {
      name: /delete net/i,
    });

    await user.click(deleteButton);

    expect(removeSpy).toHaveBeenCalledTimes(1);
    expect(removeSpy).toHaveBeenCalledWith('NET');
  });

  it('disables favourite, active-row Delete, and archive Delete actions while their mutations are loading', async () => {
    const user = userEvent.setup();

    const item = { ...baseWatchlistItem, ticker: 'NET', is_favourite: false };
    const archived = {
      ...baseArchivedWatchlistItem,
      ticker: 'CRM',
      failed_stage: 'vcp',
    };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [item], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: { archived_items: [archived], metadata: { count: 1 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({
        mutateAsync: vi.fn(),
        isLoading: true,
      }),
      useToggleFavourite: () => ({
        mutateAsync: vi.fn(),
        isLoading: true,
      }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({
        mutateAsync: vi.fn(),
        isLoading: true,
      }),
    });

    const wrapper = createWrapper(queryClient);

    render(<WatchlistPage />, { wrapper });

    const favButton = screen.getByRole('button', {
      name: /favourite stock net/i,
    });
    expect(favButton).toBeDisabled();

    const activeDeleteButton = screen.getByRole('button', {
      name: /delete net/i,
    });
    expect(activeDeleteButton).toBeDisabled();

    const archiveTab = screen.getByRole('tab', {
      name: /recently archived/i,
    });
    await user.click(archiveTab);

    const archiveDeleteButton = screen.getByRole('button', {
      name: /delete crm/i,
    });
    expect(archiveDeleteButton).toBeDisabled();
  });
});
