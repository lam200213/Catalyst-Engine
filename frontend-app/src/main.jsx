// frontend-app/src/main.jsx
// to bridge the gap between the DOM (index.html) and React

import React from 'react';
import ReactDOM from 'react-dom/client';
import { ChakraProvider, ColorModeScript } from '@chakra-ui/react';
import { QueryClient } from '@tanstack/react-query';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
// Switched to Async Storage Persister (Standard for v5)
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister';

import theme from './theme';
import App from './App.jsx';

// 1. Create the QueryClient with cache settings optimized for persistence
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Set staleTime to 0 to enable "Stale-While-Revalidate".
      staleTime: 0, 
      
      // MODIFIED: Increased from 30m to 24h. 
      // Essential for persistence: ensures data loaded from localStorage remains available 
      // across browser sessions (e.g., next day) to provide that "instant load" feel.
      gcTime: 1000 * 60 * 60 * 24, 
      
      // MODIFIED: Reduced from 2 to 1. 
      // Fails faster to show UI feedback/error states to the user rather than hanging.
      retry: 1,
      
      // KEPT: False. Prevents dashboard data from shifting unexpectedly when clicking tabs.
      refetchOnWindowFocus: false, 
      
      // DELETED (Reverted to Default: true): refetchOnReconnect
      // If internet drops and comes back, we WANT to fetch fresh data automatically.

      // DELETED (Reverted to Default: true): refetchOnMount
      // Necessary because if data IS stale (older than 5 mins), we must fetch new data 
      // when the component mounts. 'staleTime' already prevents fetching if data is fresh.
    },
  },
});

// 2. Create the Async Storage Persister (uses localStorage)
const persister = createAsyncStoragePersister({
  storage: window.localStorage,
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ChakraProvider theme={theme}>
      <ColorModeScript initialColorMode={theme.config.initialColorMode} />
      {/* 3. Wrap App in PersistQueryClientProvider */}
      <PersistQueryClientProvider 
        client={queryClient} 
        persistOptions={{ 
          persister,
          maxAge: 1000 * 60 * 60 * 24, 
          // Bumped to v2 to clear the corrupted cache from the previous bug
          buster: 'v2',                
          dehydrateOptions: {
            shouldDehydrateQuery: (query) => query.state.status === 'success',
          },
        }}
      >
        <App />
      </PersistQueryClientProvider>
    </ChakraProvider>
  </React.StrictMode>
);