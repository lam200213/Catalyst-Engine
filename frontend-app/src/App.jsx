// frontend-app/src/App.jsx
import React from 'react';
import {
  Box, Button, Container, Flex, Heading, Input, Text, VStack,
  Spinner, Alert, SimpleGrid, AlertIcon
} from '@chakra-ui/react';
import { useStockData } from './hooks/useStockData';
import ScreeningResult from './components/ScreeningResult';
import AnalysisChart from './components/AnalysisChart';

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

        <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
          <form onSubmit={handleSubmit}>
            <Flex direction={{ base: 'column', md: 'row' }} gap={4}>
              <Input
                placeholder="Enter Ticker (e.g., AAPL)"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                focusBorderColor="blue.300"
                size="lg"
                isDisabled={loading}
              />
              <Button
                type="submit"
                colorScheme="blue"
                size="lg"
                isLoading={loading}
                loadingText="Analyzing..."
                w={{ base: '100%', md: 'auto' }}
              >
                Analyze Stock
              </Button>
            </Flex>
          </form>
        </Box>

        {error && (
          <Alert status="error" borderRadius="md">
            <AlertIcon />
            {error}
          </Alert>
        )}

        <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={8}>
          <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
            <Heading as="h2" size="lg" mb={4} color="blue.400">Screening Results</Heading>
            <ScreeningResult result={data.screening} loading={loading && !data.screening} />
          </Box>
          <Box bg="gray.700" p={6} borderRadius="lg" boxShadow="lg">
            <Heading as="h2" size="lg" mb={4} color="blue.400">VCP Analysis</Heading>
            <AnalysisChart analysisData={data.analysis} />
          </Box>
        </SimpleGrid>

        <Box as="footer" textAlign="center" py={4} color="gray.500">
          <Text>&copy; {new Date().getFullYear()} SEPA Stock Screener. All rights reserved.</Text>
        </Box>
      </VStack>
    </Container>
  );
}

export default App;