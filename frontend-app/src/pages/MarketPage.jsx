// frontend-app/src/pages/MarketPage.jsx

import React from 'react';
import { Box, Heading, VStack, SimpleGrid, Button, Alert, AlertIcon, Spinner } from '@chakra-ui/react';
import MarketHealthCard from '../components/MarketHealthCard';
import LeadingIndustriesTable from '../components/LeadingIndustriesTable';
import { useMonitoringApi } from '../hooks/useMonitoringApi';
import { getMarketHealth } from '../services/monitoringApi';

const MarketPage = () => {
  const { data, loading, error, retry } = useMonitoringApi(getMarketHealth, true, 1);

  // Enhanced error handling with retry option
  if (error) {
    return (
      <Box p={6}>
        <VStack spacing={6}>
          <Heading size="xl" color="whiteAlpha.900">Market Health</Heading>
          <Alert status="error" borderRadius="lg">
            <AlertIcon />
            <Box flex="1">
              <Text>{error}</Text>
              <Button 
                mt={2} 
                size="sm" 
                colorScheme="red" 
                variant="outline"
                onClick={retry}
              >
                Try Again
              </Button>
            </Box>
          </Alert>
        </VStack>
      </Box>
    );
  }

  return (
    <VStack align="stretch" spacing={4} p={4}>
      <Heading size="lg">Market Health</Heading>

      {loading ? (
        <Box p={6} bg="gray.700" borderRadius="md">
          <Spinner />
        </Box>
      ) : (
        <MarketHealthCard overview={data?.market_overview || null} />
      )}

      {!loading && data?.leaders_by_industry && (
        <LeadingIndustriesTable rows={data?.leaders_by_industry?.leading_industries || []} />
      )}
    </VStack>
  );
};

export default MarketPage;