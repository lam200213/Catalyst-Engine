// frontend-app/src/App.jsx
// Set up the global layout with the sidebar and routing.

import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Box, Flex } from '@chakra-ui/react';
import { useQueryClient } from '@tanstack/react-query';

// Architecture: Layout & Components
import Sidebar from './components/Sidebar';
import ErrorBoundary from './components/ErrorBoundary';

// Architecture: Pages
import DashboardPage from './pages/DashboardPage';
import MarketPage from './pages/MarketPage';
import WatchlistPage from './pages/WatchlistPage';
import PortfolioPage from './pages/PortfolioPage';

// Architecture: Service Layer
// Import the UNWRAPPED fetcher, not the raw API call
import { fetchMarketHealth } from './hooks/useMarketHealthQuery';

function App() {
  const queryClient = useQueryClient();

  // Eager Fetching: Prefetch critical dashboard data
  useEffect(() => {
    const prefetchCriticalData = async () => {
      try {
        console.log('Initiating background prefetch...');
        // Architecture: Query Key Standard ['domain', 'entity']
        await queryClient.prefetchQuery({
          queryKey: ['monitoring', 'marketHealth'],
          queryFn: fetchMarketHealth, // uses the same logic as the hook
          staleTime: 1000 * 60 * 5, 
        });
        console.log('Background prefetch successful');
      } catch (error) {
        // Log warning but do not crash the app
        console.warn('Background prefetch failed (App will continue to load):', error);
      }
    };

    prefetchCriticalData();
  }, [queryClient]);

  return (
    <ErrorBoundary>
      <Router>
        <Flex minH="100vh" bg="gray.800" color="whiteAlpha.900">
          <Sidebar />
          <Box flex="1" p="6" overflowY="auto">
            <Routes>
              {/* Architecture: Route Definitions */}
              <Route path="/" element={<DashboardPage />} />
              <Route path="/market" element={<MarketPage />} />
              <Route path="/watchlist" element={<WatchlistPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
              
              {/* Fallback for unknown routes */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Box>
        </Flex>
      </Router>
    </ErrorBoundary>
  );
}

export default App;