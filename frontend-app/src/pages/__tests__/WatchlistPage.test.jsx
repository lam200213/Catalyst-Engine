// frontend-app/src/pages/__tests__/WatchlistPage.test.jsx
// WatchlistPage integration tests.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import WatchlistPage from '../WatchlistPage';
import {
  baseWatchlistItem,
  baseArchivedWatchlistItem,
} from '../../testing/fixtures/watchlistFixtures';

// Import the hook modules so Vitest can transform the TS files.
import { useWatchlistQuery } from '../../hooks/useWatchlistQuery';
import { useWatchlistArchiveQuery } from '../../hooks/useWatchlistArchiveQuery';
import { useWatchlistRefreshJobMutation } from '../../hooks/useWatchlistRefreshJobMutation';
import { useScreeningJobMutations } from '../../hooks/useScreeningJobMutations';

// Explicitly mock the modules with factory functions that return vi.fn()
// This ensures the named exports are spies we can control.
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

const createWrapper = (client) => {
  const Wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return Wrapper;
};

describe('WatchlistPage', () => {
  let queryClient;

  beforeEach(() => {
    queryClient = new QueryClient();
    vi.clearAllMocks(); // clear mock history/implementations between tests
  });

  it('renders watchlist items from hook data (load flow)', () => {
    // Arrange
    // Set up default mocks for the other hooks to avoid "undefined" issues in destructuring
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    // Target mock
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: {
        items: [baseWatchlistItem],
        metadata: { count: 1 },
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // Assert
    expect(screen.getByText('NET')).toBeInTheDocument();
  });

  it('clicking Refresh Watchlist Health triggers refresh mutation and toast', async () => {
    // Arrange
    const user = userEvent.setup();

    // Defaults
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    // Target mock
    const mutateAsyncSpy = vi.fn().mockResolvedValue({ job_id: 'abc123' });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: mutateAsyncSpy,
      isLoading: false,
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    const button = screen.getByRole('button', {
      name: /refresh watchlist health/i,
    });

    await user.click(button);

    // Assert
    expect(mutateAsyncSpy).toHaveBeenCalledTimes(1);
  });

  it('switching to Recently Archived tab shows archive table', async () => {
    // Arrange
    const user = userEvent.setup();

    // Defaults
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
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
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    // Target mock
    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: {
        archived_items: [baseArchivedWatchlistItem], // contains ticker: 'CRM'
        metadata: { count: 1 },
      },
      isLoading: false,
      isError: false,
      error: null,
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    const tab = screen.getByRole('tab', {
      name: /recently archived/i,
    });

    await user.click(tab);

    // Assert
    expect(screen.getByText('CRM')).toBeInTheDocument();
  });

  it('shows loading state while watchlist is loading', () => {
    // Arrange
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // Assert
    expect(screen.getByText(/loading watchlist/i)).toBeInTheDocument();
  });

  it('shows error message when watchlist hook returns error', () => {
    // Arrange
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Boom'),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // Assert
    expect(
      screen.getByText(/failed to load watchlist/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Boom/i)).toBeInTheDocument();
  });

  it('shows error message when archive hook returns error', () => {
    // Arrange
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Archive Boom'),
    });

    vi.mocked(useWatchlistRefreshJobMutation).mockReturnValue({
      mutateAsync: vi.fn(),
      isLoading: false,
    });

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // Assert
    expect(
      screen.getByText(/failed to load archive/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Archive Boom/i)).toBeInTheDocument();
  });

  it('shows empty state in Active tab when no items', () => {
    // Arrange
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // Assert: empty state text from WatchlistTable
    expect(
      screen.getByText(/your watchlist is empty/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/add a ticker to start tracking/i),
    ).toBeInTheDocument();
  });

  it('shows empty state in Recently Archived tab when no archived items', async () => {
    // Arrange
    const user = userEvent.setup();

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    const tab = screen.getByRole('tab', {
      name: /recently archived/i,
    });

    await user.click(tab);

    // Assert: empty state text from ArchivedWatchlistTable
    expect(screen.getByText(/no archived items/i)).toBeInTheDocument();
  });

  it('selecting a row updates selection and enables Remove Selected button', async () => {
    // Arrange
    const user = userEvent.setup();

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [baseWatchlistItem], metadata: { count: 1 } },
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    // There are two "Remove Selected" buttons (page header + table).
    // Use the first one, which is the page-level action.
    const [removeButton] = screen.getAllByRole('button', {
      name: /remove selected/i,
    });

    expect(removeButton).toBeDisabled();

    const checkbox = screen.getByRole('checkbox', {
      name: /select NET/i,
    });

    await user.click(checkbox);

    // Assert
    expect(checkbox).toBeChecked();
    expect(removeButton).not.toBeDisabled();
  });

  it('clicking Remove Selected triggers batch remove mutation with selected tickers', async () => {
    // Arrange
    const user = userEvent.setup();

    const itemNet = { ...baseWatchlistItem, ticker: 'NET' };
    const itemCrm = { ...baseWatchlistItem, ticker: 'CRM' };

    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [itemNet, itemCrm], metadata: { count: 2 } },
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

    const mutateBatchSpy = vi.fn().mockResolvedValue({});

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({
        mutateAsync: mutateBatchSpy,
        isLoading: false,
      }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);

    // Act
    render(<WatchlistPage />, { wrapper });

    const checkboxNet = screen.getByRole('checkbox', {
      name: /select NET/i,
    });

    const checkboxCrm = screen.getByRole('checkbox', {
      name: /select CRM/i,
    });

    await user.click(checkboxNet);
    await user.click(checkboxCrm);

    // Use the page-level "Remove Selected" button (first in DOM)
    const [removeButton] = screen.getAllByRole('button', {
      name: /remove selected/i,
    });

    await user.click(removeButton);

    // Assert
    expect(mutateBatchSpy).toHaveBeenCalledTimes(1);
    expect(mutateBatchSpy).toHaveBeenCalledWith({
      tickers: ['NET', 'CRM'],
    });
  });

  it('shows ErrorBoundary UI when WatchlistTable throws', async () => {
    // Arrange
    vi.resetModules();

    vi.doMock('../../components/WatchlistTable', () => ({
      WatchlistTable: () => {
        throw new Error('Boom in watchlist table');
      },
    }));

    const { default: WatchlistPageWithMock } = await import('../WatchlistPage');

    // Standard hook mocks
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [baseWatchlistItem], metadata: { count: 1 } },
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

    vi.mocked(useScreeningJobMutations).mockReturnValue({
      useAddWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Act
    render(<WatchlistPageWithMock />, { wrapper });

    // Assert
    expect(
      screen.getByText(/something went wrong/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/boom in watchlist table/i),
    ).toBeInTheDocument();

    consoleSpy.mockRestore();
    vi.doUnmock('../../components/WatchlistTable');
  });

  it('shows ErrorBoundary UI when ArchivedWatchlistTable throws', async () => {
    // Arrange
    vi.resetModules();

    vi.doMock('../../components/ArchivedWatchlistTable', () => ({
      ArchivedWatchlistTable: () => {
        throw new Error('Boom in archive table');
      },
    }));

    const { default: WatchlistPageWithMock } = await import('../WatchlistPage');

    // Standard hook mocks
    vi.mocked(useWatchlistQuery).mockReturnValue({
      data: { items: [], metadata: { count: 0 } },
      isLoading: false,
      isError: false,
      error: null,
    });

    vi.mocked(useWatchlistArchiveQuery).mockReturnValue({
      data: {
        archived_items: [baseArchivedWatchlistItem],
        metadata: { count: 1 },
      },
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
      useRemoveWatchlistItem: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useToggleFavourite: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useRemoveWatchlistBatch: () => ({ mutateAsync: vi.fn(), isLoading: false }),
      useDeleteFromArchive: () => ({ mutateAsync: vi.fn(), isLoading: false }),
    });

    const wrapper = createWrapper(queryClient);
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Act
    render(<WatchlistPageWithMock />, { wrapper });

    const tab = screen.getByRole('tab', { name: /recently archived/i });
    await userEvent.click(tab);

    // Assert
    expect(
      screen.getByText(/something went wrong/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/boom in archive table/i),
    ).toBeInTheDocument();

    consoleSpy.mockRestore();
    vi.doUnmock('../../components/ArchivedWatchlistTable');
  });
});
