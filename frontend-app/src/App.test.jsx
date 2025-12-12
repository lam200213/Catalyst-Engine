// frontend-app/src/App.test.jsx

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import App from './App';

// --- Mocks: keep App tests focused on routing + app glue (per architecture) ---
vi.mock('./components/Sidebar', () => ({
  default: () => <nav aria-label="Sidebar">Sidebar</nav>,
}));

vi.mock('./components/ErrorBoundary', () => ({
  default: ({ children }) => <>{children}</>,
}));

vi.mock('./pages/DashboardPage', () => ({
  default: () => <h1>DashboardPage</h1>,
}));

vi.mock('./pages/MarketPage', () => ({
  default: () => <h1>MarketPage</h1>,
}));

vi.mock('./pages/WatchlistPage', () => ({
  default: () => <h1>WatchlistPage</h1>,
}));

vi.mock('./pages/PortfolioPage', () => ({
  default: () => <h1>PortfolioPage</h1>,
}));

// App imports the unwrapped fetcher for prefetching
const fetchMarketHealthMock = vi.fn();
vi.mock('./hooks/useMarketHealthQuery', () => ({
  fetchMarketHealth: (...args) => fetchMarketHealthMock(...args),
}));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderAppAt(pathname = '/') {
  // App uses BrowserRouter, so we control location via history
  window.history.pushState({}, 'Test', pathname);

  const queryClient = createTestQueryClient();
  const prefetchSpy = vi.spyOn(queryClient, 'prefetchQuery');

  render(
    <QueryClientProvider client={queryClient}>
      <ChakraProvider>
        <App />
      </ChakraProvider>
    </QueryClientProvider>,
  );

  return { queryClient, prefetchSpy };
}

describe('App (routing + prefetch)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMarketHealthMock.mockResolvedValue({}); // default: successful background prefetch
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the global layout (Sidebar) and default route content', async () => {
    renderAppAt('/');

    expect(screen.getByLabelText('Sidebar')).toBeInTheDocument();
    // Default route should land on some page (typically dashboard)
    // We assert one of our mocked pages is present.
    await waitFor(() => {
      expect(screen.getByRole('heading')).toBeInTheDocument();
    });
  });

  it('routes to /watchlist', async () => {
    renderAppAt('/watchlist');

    await waitFor(() => {
      expect(screen.getByText('WatchlistPage')).toBeInTheDocument();
    });
  });

  it('routes to /market', async () => {
    renderAppAt('/market');

    await waitFor(() => {
      expect(screen.getByText('MarketPage')).toBeInTheDocument();
    });
  });

  it('routes to /portfolio', async () => {
    renderAppAt('/portfolio');

    await waitFor(() => {
      expect(screen.getByText('PortfolioPage')).toBeInTheDocument();
    });
  });

  it('kicks off background prefetch for market health on mount', async () => {
    const { prefetchSpy } = renderAppAt('/');

    await waitFor(() => {
      expect(prefetchSpy).toHaveBeenCalled();
    });

    const calls = prefetchSpy.mock.calls;
    const firstArg = calls[0]?.[0];

    // Assert the query key matches App.jsx behavior
    expect(firstArg?.queryKey).toEqual(['monitoring', 'marketHealth']);
    // And App uses the unwrapped fetcher as queryFn
    expect(typeof firstArg?.queryFn).toBe('function');
  });

  it('does not crash if background prefetch fails', async () => {
    fetchMarketHealthMock.mockRejectedValueOnce(new Error('network down'));

    renderAppAt('/');

    await waitFor(() => {
      // Ensure the effect actually ran and attempted the fetch
      expect(fetchMarketHealthMock).toHaveBeenCalled();
    });

    // App should still render normally
    expect(screen.getByLabelText('Sidebar')).toBeInTheDocument();
    expect(screen.getByText('DashboardPage')).toBeInTheDocument();
  });
});