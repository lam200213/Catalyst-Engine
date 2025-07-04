import React from 'react';
import {
  Box, Container, Heading, Text, VStack,
  Alert, SimpleGrid, AlertIcon
} from '@chakra-ui/react';
import { useStockData } from './hooks/useStockData';
import ScreeningPanel from './components/ScreeningPanel';
import ChartPanel from './components/ChartPanel';
import TickerForm from './components/TickerForm';

function App() {
  const { ticker, setTicker, data, loading, error, getData } = useStockData('AAPL');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (ticker) {
      getData(ticker);
    }
  };

  return (
    <Container maxW="container.xl" p={4}>
      <VStack spacing={8} align="stretch">
        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
          <Heading as="h1" size="xl" color="blue.300" textAlign="center">
            SEPA Stock Screener
          </Heading>
        </Box>

        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="xl">
          <TickerForm 
            ticker={ticker}
            setTicker={setTicker}
            handleSubmit={handleSubmit}
            loading={loading}
          />
        </Box>

        {error && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {error}
          </Alert>
        )}

        <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={8}>
          <ScreeningPanel result={data.screening} loading={loading && !data.screening} />
          <ChartPanel analysisData={data.analysis} loading={loading && !data.analysis} />
        </SimpleGrid>

        <Box as="footer" textAlign="center" py={4} color="gray.500">
          <Text>&copy; {new Date().getFullYear()} SEPA Stock Screener. All rights reserved.</Text>
        </Box>
      </VStack>
    </Container>
  );
}

export default App;