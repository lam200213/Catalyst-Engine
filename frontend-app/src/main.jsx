import React from 'react';
import ReactDOM from 'react-dom/client';
import { ChakraProvider, ColorModeScript } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import theme from './theme'; // Import the custom theme
import App from './App.jsx';

// Keep data fresh-but-not-noisy for dashboards
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,      // 5 minutes
      gcTime: 1000 * 60 * 30,        // 30 minutes
      refetchOnWindowFocus: false,   // avoid surprise refetch on tab focus
      refetchOnReconnect: false,     // opt-in later if needed
      refetchOnMount: false,         // do not refetch when the page remounts
      retry: 2,                      // match your current retry policy
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')).render(
  <ChakraProvider theme={theme}>
    <ColorModeScript initialColorMode={theme.config.initialColorMode} />
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </ChakraProvider>
);