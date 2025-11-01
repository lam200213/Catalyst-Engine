// frontend-app/src/App.jsx
// Set up the global layout with the sidebar and routing.

import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Box, Flex } from '@chakra-ui/react';
import Sidebar from './components/Sidebar';
import DashboardPage from './pages/DashboardPage';
import MarketPage from './pages/MarketPage';
import WatchlistPage from './pages/WatchlistPage';
import PortfolioPage from './pages/PortfolioPage';
import ErrorBoundary from './components/ErrorBoundary'; 

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Flex minH="100vh" bg="gray.800" color="whiteAlpha.900">
          <Sidebar />
          <Box flex="1" p="6">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/market" element={<MarketPage />} />
              <Route path="/watchlist" element={<WatchlistPage />} />
              <Route path="/portfolio" element={<PortfolioPage />} />
            </Routes>
          </Box>
        </Flex>
      </Router>
    </ErrorBoundary>
  );
}

export default App;